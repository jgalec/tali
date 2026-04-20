from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import os
import re
import statistics
import subprocess
import urllib.error
import urllib.request
from array import array
from collections import defaultdict
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


load_dotenv_file(WORKSPACE_ROOT / ".env")

DEFAULT_REFERENCE_DIR = WORKSPACE_ROOT / "voices" / "me2_voice_reference_candidates"
DEFAULT_GENERATED_ROOT = WORKSPACE_ROOT / "output"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_SPEAKER_EMBED_URL = os.getenv("AUDIO_EVAL_EMBED_URL", "")
DEFAULT_SPEAKER_EMBED_TOKEN = os.getenv("AUDIO_EVAL_AUTH_TOKEN", "")

FFMPEG_SAMPLE_RATE = 16000
FRAME_LENGTH_MS = 30
HOP_LENGTH_MS = 15
SILENCE_RMS_DB = -42.0
REMOTE_TIMEOUT_SECONDS = 120

SPECTRAL_KEYS = (
    "centroid",
    "spread",
    "entropy",
    "flatness",
    "flux",
    "rolloff",
)

SIMILARITY_FEATURES = {
    "zero_crossings_rate": 0.8,
    "rms_db": 0.4,
    "spectral_centroid_mean": 1.4,
    "spectral_spread_mean": 1.0,
    "spectral_entropy_mean": 1.0,
    "spectral_flatness_mean": 0.9,
    "spectral_flux_mean": 0.7,
    "spectral_rolloff_mean": 1.2,
}

FALLBACK_SCALES = {
    "zero_crossings_rate": 0.01,
    "rms_db": 2.0,
    "spectral_centroid_mean": 250.0,
    "spectral_spread_mean": 250.0,
    "spectral_entropy_mean": 0.05,
    "spectral_flatness_mean": 0.05,
    "spectral_flux_mean": 0.02,
    "spectral_rolloff_mean": 400.0,
}

PROMPT_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")

SPEAKER_SIMILARITY_WEIGHT = 0.65
ACOUSTIC_SIMILARITY_WEIGHT = 0.35


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate generated Tali audio against the local reference bank.")
    parser.add_argument("--reference-dir", default=str(DEFAULT_REFERENCE_DIR), help="Directory with original reference WAVs.")
    parser.add_argument("--generated-root", default=str(DEFAULT_GENERATED_ROOT), help="Root directory containing generated WAVs.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory where reports will be written.")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit for generated files, for quick checks.")
    parser.add_argument(
        "--speaker-embed-url",
        default=DEFAULT_SPEAKER_EMBED_URL,
        help="Optional base URL for the speaker-embedding service.",
    )
    parser.add_argument(
        "--speaker-embed-token",
        default=DEFAULT_SPEAKER_EMBED_TOKEN,
        help="Optional bearer token for the speaker-embedding service.",
    )
    parser.add_argument(
        "--speaker-timeout",
        type=int,
        default=REMOTE_TIMEOUT_SECONDS,
        help="Timeout in seconds for speaker-embedding service requests.",
    )
    return parser.parse_args()


def run_command(command: list[str], *, text: bool) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)


def db_from_linear(value: float) -> float:
    if value <= 0:
        return -120.0
    return 20.0 * math.log10(value)


def safe_mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def safe_std(values: list[float]) -> float:
    return statistics.pstdev(values) if len(values) > 1 else 0.0


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = ratio * (len(values) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[lower]
    lower_value = values[lower]
    upper_value = values[upper]
    return lower_value + (upper_value - lower_value) * (index - lower)


def available_float_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def join_url(base_url: str, path: str) -> str:
    return f"{normalize_base_url(base_url)}{path}"


def post_json(url: str, payload: dict[str, Any], token: str, timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Speaker embedding service error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach speaker embedding service: {exc}") from exc


def get_json(url: str, token: str, timeout: int) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Speaker embedding service error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach speaker embedding service: {exc}") from exc


def decode_audio_samples(path: Path, sample_rate: int = FFMPEG_SAMPLE_RATE) -> tuple[array[int], int]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    result = run_command(command, text=False)
    samples = array("h")
    samples.frombytes(result.stdout)
    return samples, sample_rate


def compute_temporal_profile(samples: array[int], sample_rate: int) -> dict[str, float]:
    if not samples:
        return {
            "duration_seconds": 0.0,
            "peak_db": -120.0,
            "rms_db": -120.0,
            "zero_crossings_rate": 0.0,
            "silence_ratio": 1.0,
            "clipping_ratio": 0.0,
            "frame_dynamic_range_db": 0.0,
        }

    duration_seconds = len(samples) / sample_rate
    peak = max(abs(value) for value in samples)
    peak_db = db_from_linear(peak / 32768.0)

    sum_squares = 0.0
    zero_crossings = 0
    clipping_count = 0
    previous_sign = 0
    for value in samples:
        if abs(value) >= 32760:
            clipping_count += 1
        sum_squares += float(value) * float(value)
        sign = 1 if value > 0 else -1 if value < 0 else 0
        if previous_sign and sign and sign != previous_sign:
            zero_crossings += 1
        if sign:
            previous_sign = sign

    rms = math.sqrt(sum_squares / len(samples)) / 32768.0
    rms_db = db_from_linear(rms)
    zero_crossings_rate = zero_crossings / max(1, len(samples) - 1)
    clipping_ratio = clipping_count / len(samples)

    frame_length = max(1, int(sample_rate * FRAME_LENGTH_MS / 1000.0))
    hop_length = max(1, int(sample_rate * HOP_LENGTH_MS / 1000.0))
    frame_rms_db_values: list[float] = []
    silence_frames = 0

    for start in range(0, max(1, len(samples) - frame_length + 1), hop_length):
        frame = samples[start : start + frame_length]
        if not frame:
            continue
        frame_sum = 0.0
        for value in frame:
            frame_sum += float(value) * float(value)
        frame_rms_db = db_from_linear(math.sqrt(frame_sum / len(frame)) / 32768.0)
        frame_rms_db_values.append(frame_rms_db)
        if frame_rms_db < SILENCE_RMS_DB:
            silence_frames += 1

    sorted_rms = sorted(frame_rms_db_values)
    frame_dynamic_range_db = percentile(sorted_rms, 0.9) - percentile(sorted_rms, 0.1)
    silence_ratio = silence_frames / len(frame_rms_db_values) if frame_rms_db_values else 1.0

    return {
        "duration_seconds": round(duration_seconds, 6),
        "peak_db": round(peak_db, 6),
        "rms_db": round(rms_db, 6),
        "zero_crossings_rate": round(zero_crossings_rate, 8),
        "silence_ratio": round(silence_ratio, 6),
        "clipping_ratio": round(clipping_ratio, 8),
        "frame_dynamic_range_db": round(frame_dynamic_range_db, 6),
    }


def compute_spectral_profile(path: Path, sample_rate: int = FFMPEG_SAMPLE_RATE) -> dict[str, float]:
    filtergraph = (
        f"aresample={sample_rate},"
        "aformat=channel_layouts=mono,"
        "aspectralstats=measure=all:win_size=1024:overlap=0.5,"
        "ametadata=mode=print:file=-"
    )
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-af",
        filtergraph,
        "-f",
        "null",
        "-",
    ]
    result = run_command(command, text=True)

    frames: list[dict[str, float]] = []
    current_frame: dict[str, float] = {}
    prefix = "lavfi.aspectralstats.1."

    def flush_current() -> None:
        nonlocal current_frame
        if current_frame:
            frames.append(current_frame)
            current_frame = {}

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("frame:"):
            flush_current()
            continue
        if not line.startswith(prefix):
            continue
        key, value = line.split("=", 1)
        metric = key[len(prefix) :]
        if metric not in SPECTRAL_KEYS:
            continue
        try:
            parsed_value = float(value)
        except ValueError:
            continue
        if math.isfinite(parsed_value):
            current_frame[metric] = parsed_value

    flush_current()

    active_frames = [frame for frame in frames if frame.get("rolloff", 0.0) > 0.0 or frame.get("flux", 0.0) > 0.0]
    source_frames = active_frames or frames

    profile: dict[str, float] = {"spectral_active_frames": float(len(active_frames))}
    for key in SPECTRAL_KEYS:
        values = [frame[key] for frame in source_frames if key in frame]
        profile[f"spectral_{key}_mean"] = round(safe_mean(values), 6)
        profile[f"spectral_{key}_std"] = round(safe_std(values), 6)
    return profile


def build_audio_profile(path: Path) -> dict[str, float]:
    samples, sample_rate = decode_audio_samples(path)
    profile = compute_temporal_profile(samples, sample_rate)
    profile.update(compute_spectral_profile(path, sample_rate))
    return profile


def parse_prompt_sets(reference_dir: Path) -> dict[str, dict[int, str]]:
    prompt_sets: dict[str, dict[int, str]] = {}
    for path in sorted(reference_dir.glob("tali_test_dialogues*.txt")):
        entries: dict[int, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            match = PROMPT_LINE_RE.match(raw_line)
            if match:
                entries[int(match.group(1))] = match.group(2).strip()
        prompt_sets[path.stem] = entries
    return prompt_sets


def load_reference_index(reference_dir: Path) -> dict[str, dict[str, Any]]:
    index_path = reference_dir / "references.json"
    if not index_path.exists():
        return {}
    rows = json.loads(index_path.read_text(encoding="utf-8"))
    return {row["output_file"]: row for row in rows}


def feature_scales(reference_profiles: list[dict[str, Any]]) -> dict[str, float]:
    scales: dict[str, float] = {}
    for feature, fallback in FALLBACK_SCALES.items():
        values = [float(profile[feature]) for profile in reference_profiles if feature in profile]
        stdev = safe_std(values)
        scales[feature] = max(stdev, fallback)
    return scales


def weighted_distance(profile: dict[str, Any], target: dict[str, Any], scales: dict[str, float]) -> float:
    total = 0.0
    total_weight = 0.0
    for feature, weight in SIMILARITY_FEATURES.items():
        if feature not in profile or feature not in target:
            continue
        scale = scales.get(feature, 1.0)
        distance = abs(float(profile[feature]) - float(target[feature])) / scale
        total += weight * distance
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return total / total_weight


def distance_to_score(distance: float) -> float:
    return round(100.0 * math.exp(-distance / 1.8), 3)


def technical_score(profile: dict[str, Any]) -> float:
    score = 100.0

    peak_db = float(profile.get("peak_db", -120.0))
    rms_db = float(profile.get("rms_db", -120.0))
    silence_ratio = float(profile.get("silence_ratio", 1.0))
    clipping_ratio = float(profile.get("clipping_ratio", 0.0))
    active_frames = float(profile.get("spectral_active_frames", 0.0))

    if peak_db > -1.0:
        score -= min(25.0, (peak_db + 1.0) * 18.0)
    if clipping_ratio > 0.0005:
        score -= min(30.0, clipping_ratio * 12000.0)
    if rms_db < -28.0:
        score -= min(20.0, (-28.0 - rms_db) * 2.0)
    if rms_db > -8.0:
        score -= min(20.0, (rms_db + 8.0) * 2.0)
    if silence_ratio > 0.5:
        score -= min(20.0, (silence_ratio - 0.5) * 80.0)
    if active_frames < 10:
        score -= 35.0

    return round(max(0.0, min(100.0, score)), 3)


def normalize_embedding(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        return [0.0 for _ in values]
    return [value / norm for value in values]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=False))))


def cosine_to_score(value: float) -> float:
    return round((value + 1.0) * 50.0, 3)


def mean_embedding(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    size = len(vectors[0])
    totals = [0.0] * size
    for vector in vectors:
        for index, value in enumerate(vector):
            totals[index] += value
    return normalize_embedding([value / len(vectors) for value in totals])


def fetch_remote_embedding(path: Path, base_url: str, token: str, timeout: int) -> dict[str, Any]:
    payload = {
        "filename": path.name,
        "audio_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
    }
    return post_json(join_url(base_url, "/v1/audio/embed"), payload, token, timeout)


def summarize_rows(rows: list[dict[str, Any]], keys: tuple[str, ...], speaker_enabled: bool) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(str(row.get(key, "")) for key in keys)].append(row)

    summaries: list[dict[str, Any]] = []
    for group_key, group_rows in sorted(grouped.items()):
        summary: dict[str, Any] = {key: value for key, value in zip(keys, group_key, strict=False)}
        summary["clips"] = len(group_rows)
        summary["avg_acoustic_reference_similarity_score"] = round(
            safe_mean([float(row["acoustic_reference_similarity_score"]) for row in group_rows]), 3
        )
        summary["avg_acoustic_nearest_reference_score"] = round(
            safe_mean([float(row["acoustic_nearest_reference_score"]) for row in group_rows]), 3
        )
        if speaker_enabled:
            summary["avg_speaker_reference_similarity_score"] = round(
                safe_mean([float(row["speaker_reference_similarity_score"]) for row in group_rows]), 3
            )
            summary["avg_speaker_nearest_reference_score"] = round(
                safe_mean([float(row["speaker_nearest_reference_score"]) for row in group_rows]), 3
            )
        summary["avg_reference_similarity_score"] = round(
            safe_mean([float(row["reference_similarity_score"]) for row in group_rows]), 3
        )
        summary["avg_nearest_reference_score"] = round(
            safe_mean([float(row["nearest_reference_score"]) for row in group_rows]), 3
        )
        summary["avg_technical_score"] = round(safe_mean([float(row["technical_score"]) for row in group_rows]), 3)
        summary["avg_overall_score"] = round(safe_mean([float(row["overall_score"]) for row in group_rows]), 3)
        summaries.append(summary)
    return summaries


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_report(
    path: Path,
    reference_rows: list[dict[str, Any]],
    clip_rows: list[dict[str, Any]],
    model_summary: list[dict[str, Any]],
    prompt_summary: list[dict[str, Any]],
    speaker_enabled: bool,
    speaker_embed_url: str,
) -> None:
    top_clips = sorted(clip_rows, key=lambda row: float(row["overall_score"]), reverse=True)[:10]
    bottom_clips = sorted(clip_rows, key=lambda row: float(row["overall_score"]))[:10]

    lines = [
        "# Audio Evaluation Report",
        "",
        f"- Reference clips: {len(reference_rows)}",
        f"- Generated clips: {len(clip_rows)}",
        "- Acoustic method: FFmpeg-driven profile comparison against the local Tali reference bank.",
    ]
    if speaker_enabled:
        lines.append(f"- Speaker method: remote speaker embeddings from `{speaker_embed_url}`.")
        lines.append(
            f"- Blend: {int(SPEAKER_SIMILARITY_WEIGHT * 100)}% speaker similarity and {int(ACOUSTIC_SIMILARITY_WEIGHT * 100)}% acoustic similarity."
        )
    else:
        lines.append("- Speaker method: disabled.")
    lines.append("- Note: this is a heuristic similarity report, not a substitute for human listening tests.")
    lines.extend(
        [
            "",
            "## Model Summary",
            "",
            "| model | clips | acoustic | speaker | technical | overall |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in model_summary:
        speaker_value = row.get("avg_speaker_reference_similarity_score", "n/a") if speaker_enabled else "n/a"
        lines.append(
            f"| {row['model']} | {row['clips']} | {row['avg_acoustic_reference_similarity_score']} | {speaker_value} | {row['avg_technical_score']} | {row['avg_overall_score']} |"
        )

    lines.extend(
        [
            "",
            "## Prompt Set Summary",
            "",
            "| model | prompt set | clips | overall |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for row in prompt_summary:
        lines.append(f"| {row['model']} | {row['prompt_set']} | {row['clips']} | {row['avg_overall_score']} |")

    lines.extend(
        [
            "",
            "## Top Clips",
            "",
            "| clip | nearest reference | acoustic | speaker | overall |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in top_clips:
        speaker_value = row.get("speaker_reference_similarity_score", "n/a") if speaker_enabled else "n/a"
        lines.append(
            f"| {row['generated_rel_path']} | {row['nearest_reference_name']} | {row['acoustic_reference_similarity_score']} | {speaker_value} | {row['overall_score']} |"
        )

    lines.extend(
        [
            "",
            "## Lowest Scoring Clips",
            "",
            "| clip | nearest reference | acoustic | speaker | overall |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in bottom_clips:
        speaker_value = row.get("speaker_reference_similarity_score", "n/a") if speaker_enabled else "n/a"
        lines.append(
            f"| {row['generated_rel_path']} | {row['nearest_reference_name']} | {row['acoustic_reference_similarity_score']} | {speaker_value} | {row['overall_score']} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    reference_dir = Path(args.reference_dir)
    generated_root = Path(args.generated_root)
    output_dir = Path(args.output_dir)
    speaker_embed_url = normalize_base_url(args.speaker_embed_url) if args.speaker_embed_url else ""
    speaker_enabled = bool(speaker_embed_url)

    reference_index = load_reference_index(reference_dir)
    prompt_sets = parse_prompt_sets(reference_dir)

    reference_files = sorted(reference_dir.glob("*.wav"))
    if not reference_files:
        raise FileNotFoundError(f"No reference WAV files found in {reference_dir}")

    generated_files = sorted(generated_root.glob("**/*.wav"))
    if args.limit > 0:
        generated_files = generated_files[: args.limit]
    if not generated_files:
        raise FileNotFoundError(f"No generated WAV files found in {generated_root}")

    speaker_service_health: dict[str, Any] | None = None
    if speaker_enabled:
        speaker_service_health = get_json(join_url(speaker_embed_url, "/health"), args.speaker_embed_token, args.speaker_timeout)

    reference_rows: list[dict[str, Any]] = []
    reference_embeddings: dict[str, list[float]] = {}
    for path in reference_files:
        profile = build_audio_profile(path)
        metadata = reference_index.get(path.name, {})
        row: dict[str, Any] = {
            "reference_name": metadata.get("name", path.stem),
            "reference_file": path.name,
            "reference_rel_path": str(path.relative_to(WORKSPACE_ROOT)),
            "reference_description": metadata.get("description", ""),
            "reference_transcript": metadata.get("transcript", ""),
            **profile,
        }
        if speaker_enabled:
            remote = fetch_remote_embedding(path, speaker_embed_url, args.speaker_embed_token, args.speaker_timeout)
            embedding = normalize_embedding([float(value) for value in remote.get("embedding", [])])
            reference_embeddings[path.name] = embedding
            row["speaker_embedding_norm"] = round(float(remote.get("embedding_norm", 0.0)), 6)
        reference_rows.append(row)

    reference_means: dict[str, float] = {}
    for feature in SIMILARITY_FEATURES:
        values = [float(row[feature]) for row in reference_rows]
        reference_means[feature] = safe_mean(values)
    scales = feature_scales(reference_rows)
    mean_reference_embedding = mean_embedding(list(reference_embeddings.values())) if speaker_enabled else []

    clip_rows: list[dict[str, Any]] = []
    for path in generated_files:
        profile = build_audio_profile(path)
        relative_path = path.relative_to(generated_root)
        parts = relative_path.parts
        experiment = parts[0] if len(parts) >= 3 else ""
        model = parts[1] if len(parts) >= 3 else ""
        prompt_set = parts[2] if len(parts) >= 3 else path.parent.name
        clip_index = int(path.stem) if path.stem.isdigit() else 0
        expected_text = prompt_sets.get(prompt_set, {}).get(clip_index, "")

        acoustic_mean_distance = weighted_distance(profile, reference_means, scales)
        acoustic_reference_similarity_score = distance_to_score(acoustic_mean_distance)

        acoustic_reference_scores: dict[str, float] = {}
        for reference_row in reference_rows:
            acoustic_reference_scores[reference_row["reference_file"]] = distance_to_score(
                weighted_distance(profile, reference_row, scales)
            )

        speaker_reference_similarity_score: float | None = None
        speaker_nearest_reference_score: float | None = None
        speaker_embedding_norm: float | None = None
        speaker_reference_scores: dict[str, float] = {}

        if speaker_enabled:
            remote = fetch_remote_embedding(path, speaker_embed_url, args.speaker_embed_token, args.speaker_timeout)
            embedding = normalize_embedding([float(value) for value in remote.get("embedding", [])])
            speaker_embedding_norm = round(float(remote.get("embedding_norm", 0.0)), 6)
            speaker_reference_similarity_score = cosine_to_score(cosine_similarity(embedding, mean_reference_embedding))
            for reference_file, reference_embedding in reference_embeddings.items():
                speaker_reference_scores[reference_file] = cosine_to_score(cosine_similarity(embedding, reference_embedding))
            speaker_nearest_reference_score = max(speaker_reference_scores.values()) if speaker_reference_scores else 0.0

        best_reference_row: dict[str, Any] | None = None
        best_reference_score = -1.0
        for reference_row in reference_rows:
            acoustic_score = acoustic_reference_scores[reference_row["reference_file"]]
            if speaker_enabled:
                speaker_score = speaker_reference_scores.get(reference_row["reference_file"], 0.0)
                combined_score = (
                    SPEAKER_SIMILARITY_WEIGHT * speaker_score + ACOUSTIC_SIMILARITY_WEIGHT * acoustic_score
                )
            else:
                combined_score = acoustic_score
            if combined_score > best_reference_score:
                best_reference_score = combined_score
                best_reference_row = reference_row

        if best_reference_row is None:
            raise RuntimeError(f"Could not determine nearest reference for {path}")

        if speaker_enabled and speaker_reference_similarity_score is not None:
            reference_similarity_score = round(
                SPEAKER_SIMILARITY_WEIGHT * speaker_reference_similarity_score
                + ACOUSTIC_SIMILARITY_WEIGHT * acoustic_reference_similarity_score,
                3,
            )
        else:
            reference_similarity_score = acoustic_reference_similarity_score

        nearest_reference_score = round(best_reference_score, 3)
        acoustic_nearest_reference_score = acoustic_reference_scores[best_reference_row["reference_file"]]
        tech_score = technical_score(profile)
        overall_score = round(reference_similarity_score * 0.8 + tech_score * 0.2, 3)

        row = {
            "experiment": experiment,
            "model": model,
            "prompt_set": prompt_set,
            "clip_index": clip_index,
            "generated_rel_path": str(path.relative_to(WORKSPACE_ROOT)),
            "expected_text": expected_text,
            "nearest_reference_name": best_reference_row["reference_name"],
            "nearest_reference_file": best_reference_row["reference_file"],
            "acoustic_reference_similarity_score": acoustic_reference_similarity_score,
            "acoustic_nearest_reference_score": acoustic_nearest_reference_score,
            "reference_similarity_score": reference_similarity_score,
            "nearest_reference_score": nearest_reference_score,
            "technical_score": tech_score,
            "overall_score": overall_score,
            **profile,
        }
        if speaker_enabled:
            row["speaker_reference_similarity_score"] = speaker_reference_similarity_score
            row["speaker_nearest_reference_score"] = speaker_nearest_reference_score
            row["speaker_embedding_norm"] = speaker_embedding_norm
        clip_rows.append(row)

    model_summary = summarize_rows(clip_rows, ("model",), speaker_enabled)
    prompt_summary = summarize_rows(clip_rows, ("model", "prompt_set"), speaker_enabled)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "reference_profiles.csv", reference_rows)
    write_csv(output_dir / "generated_clip_scores.csv", clip_rows)
    write_csv(output_dir / "model_summary.csv", model_summary)
    write_csv(output_dir / "prompt_summary.csv", prompt_summary)

    json_report = {
        "reference_dir": str(reference_dir),
        "generated_root": str(generated_root),
        "reference_count": len(reference_rows),
        "generated_count": len(clip_rows),
        "similarity_features": list(SIMILARITY_FEATURES.keys()),
        "speaker_embedding_enabled": speaker_enabled,
        "speaker_embedding_service_url": speaker_embed_url or None,
        "speaker_embedding_service_health": speaker_service_health,
        "model_summary": model_summary,
        "prompt_summary": prompt_summary,
    }
    (output_dir / "summary.json").write_text(json.dumps(json_report, indent=2), encoding="utf-8")
    write_markdown_report(
        output_dir / "report.md",
        reference_rows,
        clip_rows,
        model_summary,
        prompt_summary,
        speaker_enabled,
        speaker_embed_url,
    )

    best_model = max(model_summary, key=lambda row: float(row["avg_overall_score"]))
    print(
        json.dumps(
            {
                "reference_count": len(reference_rows),
                "generated_count": len(clip_rows),
                "speaker_embedding_enabled": speaker_enabled,
                "best_model": best_model["model"],
                "best_model_overall_score": best_model["avg_overall_score"],
                "output_dir": str(output_dir),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
