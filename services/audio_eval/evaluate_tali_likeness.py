from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import os
import re
import string
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from uuid import uuid4


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_DIR = WORKSPACE_ROOT / "voices" / "me2_voice_reference_candidates"


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

DEFAULT_BASE_SCORES = Path(__file__).resolve().parent / "output" / "generated_clip_scores.csv"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output_tali_likeness"
DEFAULT_SPEAKER_URL = os.getenv("AUDIO_EVAL_EMBED_URL", "")
DEFAULT_SPEAKER_TOKEN = os.getenv("AUDIO_EVAL_AUTH_TOKEN", "")
DEFAULT_PYANNOTE_TOKEN = os.getenv("AUDIO_EVAL_PYANNOTE_HF_TOKEN", "")
DEFAULT_SPEAKER_TIMEOUT = int(os.getenv("AUDIO_EVAL_SPEAKER_TIMEOUT", "300"))
DEFAULT_ASR_URL = os.getenv("AUDIO_EVAL_ASR_URL", "")
DEFAULT_ASR_TOKEN = os.getenv("AUDIO_EVAL_ASR_TOKEN", "")
DEFAULT_ASR_MODEL = os.getenv("AUDIO_EVAL_ASR_MODEL", "large-v3")
DEFAULT_ASR_TIMEOUT = int(os.getenv("AUDIO_EVAL_ASR_TIMEOUT", "300"))
DEFAULT_LANGUAGE = os.getenv("AUDIO_EVAL_ASR_LANGUAGE", "en")
DEFAULT_MAX_WORKERS = int(os.getenv("AUDIO_EVAL_ASR_MAX_WORKERS", "2"))
IDENTITY_WEIGHT = 0.7
PRONUNCIATION_WEIGHT = 0.3
PRIMARY_SPEAKER_BACKENDS = ("speechbrain_ecapa", "wavlm_sv", "pyannote_embedding")

PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation)
SPACE_RE = re.compile(r"\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Tali-likeness with speaker identity and pronunciation scores.")
    parser.add_argument("--base-scores", default=str(DEFAULT_BASE_SCORES), help="CSV from evaluate_generated_audio.py")
    parser.add_argument("--reference-dir", default=str(DEFAULT_REFERENCE_DIR), help="Directory with reference WAV files")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Where to write Tali-likeness reports")
    parser.add_argument("--speaker-url", default=DEFAULT_SPEAKER_URL, help="Speaker ensemble service URL")
    parser.add_argument("--speaker-token", default=DEFAULT_SPEAKER_TOKEN, help="Bearer token for the speaker service")
    parser.add_argument(
        "--pyannote-hf-token",
        default=DEFAULT_PYANNOTE_TOKEN,
        help="Optional Hugging Face token with accepted access to pyannote/embedding",
    )
    parser.add_argument("--speaker-timeout", type=int, default=DEFAULT_SPEAKER_TIMEOUT, help="Speaker request timeout")
    parser.add_argument("--asr-url", default=DEFAULT_ASR_URL, help="Whisper transcription service URL")
    parser.add_argument("--asr-token", default=DEFAULT_ASR_TOKEN, help="Bearer token for the ASR service")
    parser.add_argument("--asr-model", default=DEFAULT_ASR_MODEL, help="Requested Whisper model name")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="ASR language")
    parser.add_argument("--timeout", type=int, default=DEFAULT_ASR_TIMEOUT, help="Per-request timeout in seconds")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS, help="Concurrent workers")
    return parser.parse_args()


def normalize_text(value: str) -> str:
    lowered = value.lower().replace("'", "")
    no_punct = lowered.translate(PUNCT_TRANSLATION)
    return SPACE_RE.sub(" ", no_punct).strip()


def levenshtein_distance(left: list[str] | str, right: list[str] | str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, left_value in enumerate(left, start=1):
        current = [i]
        for j, right_value in enumerate(right, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if left_value == right_value else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def word_error_rate(expected: str, actual: str) -> float:
    expected_tokens = normalize_text(expected).split()
    actual_tokens = normalize_text(actual).split()
    if not expected_tokens:
        return 0.0 if not actual_tokens else 1.0
    return levenshtein_distance(expected_tokens, actual_tokens) / len(expected_tokens)


def char_error_rate(expected: str, actual: str) -> float:
    expected_chars = list(normalize_text(expected).replace(" ", ""))
    actual_chars = list(normalize_text(actual).replace(" ", ""))
    if not expected_chars:
        return 0.0 if not actual_chars else 1.0
    return levenshtein_distance(expected_chars, actual_chars) / len(expected_chars)


def pronunciation_score(expected: str, actual: str) -> float:
    wer = min(1.5, word_error_rate(expected, actual))
    cer = min(1.5, char_error_rate(expected, actual))
    penalty = 0.75 * min(1.0, wer) + 0.25 * min(1.0, cer)
    return round(max(0.0, 100.0 * (1.0 - penalty)), 3)


def normalize_embedding(values: list[float]) -> list[float]:
    norm = sum(value * value for value in values) ** 0.5
    if norm == 0.0:
        return [0.0 for _ in values]
    return [value / norm for value in values]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=False))))


def cosine_to_score(value: float) -> float:
    return round((value + 1.0) * 50.0, 3)


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def build_headers(token: str, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(extra_headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_json(url: str, token: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=build_headers(token, {"Accept": "application/json"}), method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any], token: str, timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers=build_headers(token, {"Content-Type": "application/json", "Accept": "application/json"}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Remote service error {exc.code}: {detail}") from exc


def build_multipart_body(boundary: str, fields: dict[str, str], file_path: Path, mime_type: str) -> bytes:
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks)


def transcribe_audio(audio_path: Path, asr_url: str, asr_token: str, model: str, language: str, timeout: int) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    boundary = f"----OpenCodeAudioEval{uuid4().hex}"
    body = build_multipart_body(
        boundary=boundary,
        fields={"model": model, "language": language},
        file_path=audio_path,
        mime_type=mime_type,
    )
    request = urllib.request.Request(
        join_url(asr_url, "/v1/audio/transcriptions"),
        data=body,
        headers=build_headers(asr_token, {"Content-Type": f"multipart/form-data; boundary={boundary}"}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ASR service error {exc.code}: {detail}") from exc


def fetch_speaker_models(
    audio_path: Path,
    speaker_url: str,
    speaker_token: str,
    pyannote_hf_token: str,
    timeout: int,
) -> dict[str, list[float]]:
    payload: dict[str, Any] = {
        "filename": audio_path.name,
        "audio_base64": base64.b64encode(audio_path.read_bytes()).decode("ascii"),
    }
    if pyannote_hf_token:
        payload["huggingface_token"] = pyannote_hf_token

    response = post_json(join_url(speaker_url, "/v1/audio/embed"), payload, speaker_token, timeout)
    models = response.get("models", {})
    if not isinstance(models, dict):
        if "embedding" in response:
            return {"speechbrain_ecapa": normalize_embedding([float(value) for value in response["embedding"]])}
        return {}

    embeddings: dict[str, list[float]] = {}
    for backend, backend_payload in models.items():
        if not isinstance(backend_payload, dict):
            continue
        values = backend_payload.get("embedding")
        if isinstance(values, list):
            embeddings[str(backend)] = normalize_embedding([float(value) for value in values])
    return embeddings


def mean_embedding(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    size = len(vectors[0])
    totals = [0.0] * size
    for vector in vectors:
        for index, value in enumerate(vector):
            totals[index] += value
    return normalize_embedding([value / len(vectors) for value in totals])


def read_base_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, summary: dict[str, Any], versus_rows: list[dict[str, Any]]) -> None:
    model_rows = summary["model_summary"]
    lines = [
        "# Tali-Likeness Report",
        "",
        "- Focus: identity and pronunciation only.",
        f"- Blend: {int(IDENTITY_WEIGHT * 100)}% identity and {int(PRONUNCIATION_WEIGHT * 100)}% pronunciation.",
        "- Identity stack: SpeechBrain ECAPA, Microsoft WavLM speaker verification, and optional pyannote embeddings.",
        "- Emotion is intentionally excluded in this pass.",
        "",
        "## Model Summary",
        "",
        "| model | clips | ensemble identity | ecapa | wavlm | pyannote | pronunciation | tali-likeness |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in model_rows:
        lines.append(
            f"| {row['model']} | {row['clips']} | {row['avg_identity_score']} | {row['avg_ecapa_identity_score']} | {row['avg_wavlm_identity_score']} | {row['avg_pyannote_identity_score']} | {row['avg_pronunciation_score']} | {row['avg_tali_likeness_score']} |"
        )

    lines.extend(
        [
            "",
            "## Pairwise Versus",
            "",
            "| prompt set | clip | 0.6b identity | 0.6b final | 1.7b identity | 1.7b final | winner |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in versus_rows:
        lines.append(
            f"| {row['prompt_set']} | {row['clip_index']} | {row['qwen_0_6b_identity_score']} | {row['qwen_0_6b_tali_likeness_score']} | {row['qwen_1_7b_identity_score']} | {row['qwen_1_7b_tali_likeness_score']} | {row['winner']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    base_scores_path = Path(args.base_scores)
    reference_dir = Path(args.reference_dir)
    output_dir = Path(args.output_dir)
    speaker_url = args.speaker_url.rstrip("/")
    asr_url = args.asr_url.rstrip("/")

    if not speaker_url:
        raise RuntimeError("Missing speaker URL. Set AUDIO_EVAL_EMBED_URL in .env or pass --speaker-url.")
    if not asr_url:
        raise RuntimeError("Missing ASR URL. Set AUDIO_EVAL_ASR_URL in .env or pass --asr-url.")

    base_rows = read_base_rows(base_scores_path)
    speaker_health = get_json(join_url(speaker_url, "/health"), args.speaker_token, min(30, args.speaker_timeout))
    asr_health = get_json(join_url(asr_url, "/health"), args.asr_token, min(30, args.timeout))

    reference_embeddings: dict[str, dict[str, list[float]]] = {}
    for reference_path in sorted(reference_dir.glob("*.wav")):
        reference_embeddings[reference_path.name] = fetch_speaker_models(
            reference_path,
            speaker_url,
            args.speaker_token,
            args.pyannote_hf_token,
            args.speaker_timeout,
        )

    backend_reference_means: dict[str, list[float]] = {}
    available_backends = []
    for backend in PRIMARY_SPEAKER_BACKENDS:
        vectors = [embeddings[backend] for embeddings in reference_embeddings.values() if backend in embeddings]
        if vectors:
            backend_reference_means[backend] = mean_embedding(vectors)
            available_backends.append(backend)

    jobs: list[tuple[int, dict[str, str]]] = list(enumerate(base_rows))
    enriched_rows: list[dict[str, Any]] = [None] * len(jobs)  # type: ignore[list-item]

    def worker(job: tuple[int, dict[str, str]]) -> tuple[int, dict[str, Any]]:
        index, row = job
        audio_path = WORKSPACE_ROOT / row["generated_rel_path"]
        transcript_payload = transcribe_audio(audio_path, asr_url, args.asr_token, args.asr_model, args.language, args.timeout)
        transcript = str(transcript_payload.get("text", "")).strip()
        clip_embeddings = fetch_speaker_models(
            audio_path,
            speaker_url,
            args.speaker_token,
            args.pyannote_hf_token,
            args.speaker_timeout,
        )

        backend_scores: dict[str, float] = {}
        for backend, mean_vector in backend_reference_means.items():
            vector = clip_embeddings.get(backend)
            if vector is None:
                continue
            backend_scores[backend] = cosine_to_score(cosine_similarity(vector, mean_vector))

        identity_score = mean(list(backend_scores.values()))
        pron_score = pronunciation_score(row["expected_text"], transcript)
        final_score = round(IDENTITY_WEIGHT * identity_score + PRONUNCIATION_WEIGHT * pron_score, 3)

        return index, {
            "experiment": row["experiment"],
            "model": row["model"],
            "prompt_set": row["prompt_set"],
            "clip_index": int(row["clip_index"]),
            "generated_rel_path": row["generated_rel_path"],
            "expected_text": row["expected_text"],
            "transcribed_text": transcript,
            "identity_score": identity_score,
            "ecapa_identity_score": backend_scores.get("speechbrain_ecapa", ""),
            "wavlm_identity_score": backend_scores.get("wavlm_sv", ""),
            "pyannote_identity_score": backend_scores.get("pyannote_embedding", ""),
            "pronunciation_score": pron_score,
            "tali_likeness_score": final_score,
            "word_error_rate": round(word_error_rate(row["expected_text"], transcript), 4),
            "char_error_rate": round(char_error_rate(row["expected_text"], transcript), 4),
        }

    max_workers = max(1, args.max_workers)
    if max_workers == 1:
        for job in jobs:
            index, result = worker(job)
            enriched_rows[index] = result
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(worker, job): job[0] for job in jobs}
            for future in as_completed(future_map):
                index, result = future.result()
                enriched_rows[index] = result

    rows = [row for row in enriched_rows if row is not None]
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_model.setdefault(row["model"], []).append(row)

    model_summary: list[dict[str, Any]] = []
    for model, model_rows in sorted(by_model.items()):
        model_summary.append(
            {
                "model": model,
                "clips": len(model_rows),
                "avg_identity_score": mean([float(row["identity_score"]) for row in model_rows]),
                "avg_ecapa_identity_score": mean([float(row["ecapa_identity_score"] or 0.0) for row in model_rows]),
                "avg_wavlm_identity_score": mean([float(row["wavlm_identity_score"] or 0.0) for row in model_rows]),
                "avg_pyannote_identity_score": mean(
                    [float(row["pyannote_identity_score"] or 0.0) for row in model_rows if row["pyannote_identity_score"] != ""]
                ),
                "avg_pronunciation_score": mean([float(row["pronunciation_score"]) for row in model_rows]),
                "avg_tali_likeness_score": mean([float(row["tali_likeness_score"]) for row in model_rows]),
            }
        )

    pair_map: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for row in rows:
        pair_map.setdefault((row["prompt_set"], row["clip_index"]), {})[row["model"]] = row

    versus_rows: list[dict[str, Any]] = []
    for (prompt_set, clip_index), pair in sorted(pair_map.items()):
        left = pair.get("qwen-0.6b")
        right = pair.get("qwen-1.7b")
        if not left or not right:
            continue
        if left["tali_likeness_score"] > right["tali_likeness_score"]:
            winner = "qwen-0.6b"
        elif right["tali_likeness_score"] > left["tali_likeness_score"]:
            winner = "qwen-1.7b"
        else:
            winner = "tie"
        versus_rows.append(
            {
                "prompt_set": prompt_set,
                "clip_index": clip_index,
                "qwen_0_6b_identity_score": left["identity_score"],
                "qwen_0_6b_pronunciation_score": left["pronunciation_score"],
                "qwen_0_6b_tali_likeness_score": left["tali_likeness_score"],
                "qwen_1_7b_identity_score": right["identity_score"],
                "qwen_1_7b_pronunciation_score": right["pronunciation_score"],
                "qwen_1_7b_tali_likeness_score": right["tali_likeness_score"],
                "winner": winner,
                "winning_margin": round(abs(float(right["tali_likeness_score"]) - float(left["tali_likeness_score"])), 3),
            }
        )

    summary = {
        "speaker_service_url": speaker_url,
        "speaker_service_health": speaker_health,
        "asr_service_url": asr_url,
        "asr_service_health": asr_health,
        "speaker_backends_used": available_backends,
        "pyannote_requested": bool(args.pyannote_hf_token),
        "identity_weight": IDENTITY_WEIGHT,
        "pronunciation_weight": PRONUNCIATION_WEIGHT,
        "emotion_evaluated": False,
        "model_summary": model_summary,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "clip_scores.csv", rows)
    write_csv(output_dir / "model_summary.csv", model_summary)
    write_csv(output_dir / "versus.csv", versus_rows)
    write_markdown(output_dir / "report.md", summary, versus_rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    best_model = max(model_summary, key=lambda row: row["avg_tali_likeness_score"])
    print(
        json.dumps(
            {
                "clips": len(rows),
                "best_model": best_model["model"],
                "best_tali_likeness_score": best_model["avg_tali_likeness_score"],
                "speaker_backends_used": available_backends,
                "output_dir": str(output_dir),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
