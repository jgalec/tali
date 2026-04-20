from __future__ import annotations

import argparse
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
DEFAULT_ASR_URL = os.getenv("AUDIO_EVAL_ASR_URL", "")
DEFAULT_ASR_TOKEN = os.getenv("AUDIO_EVAL_ASR_TOKEN", "")
DEFAULT_ASR_MODEL = os.getenv("AUDIO_EVAL_ASR_MODEL", "large-v3")
DEFAULT_ASR_TIMEOUT = int(os.getenv("AUDIO_EVAL_ASR_TIMEOUT", "300"))
DEFAULT_LANGUAGE = os.getenv("AUDIO_EVAL_ASR_LANGUAGE", "en")
DEFAULT_MAX_WORKERS = int(os.getenv("AUDIO_EVAL_ASR_MAX_WORKERS", "2"))
IDENTITY_WEIGHT = 0.7
PRONUNCIATION_WEIGHT = 0.3

PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation)
SPACE_RE = re.compile(r"\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Tali-likeness with identity and pronunciation scores.")
    parser.add_argument("--base-scores", default=str(DEFAULT_BASE_SCORES), help="CSV from evaluate_generated_audio.py")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Where to write Tali-likeness reports")
    parser.add_argument("--asr-url", default=DEFAULT_ASR_URL, help="Whisper transcription service URL")
    parser.add_argument("--asr-token", default=DEFAULT_ASR_TOKEN, help="Bearer token for the ASR service")
    parser.add_argument("--asr-model", default=DEFAULT_ASR_MODEL, help="Requested Whisper model name")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="ASR language")
    parser.add_argument("--timeout", type=int, default=DEFAULT_ASR_TIMEOUT, help="Per-request timeout in seconds")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS, help="Concurrent transcription workers")
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


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def build_headers(token: str, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(extra_headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


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
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach ASR service: {exc}") from exc


def get_health(asr_url: str, asr_token: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(join_url(asr_url, "/health"), headers=build_headers(asr_token), method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


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


def write_markdown(path: Path, model_rows: list[dict[str, Any]], versus_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Tali-Likeness Report",
        "",
        "- Focus: identity and pronunciation only.",
        f"- Blend: {int(IDENTITY_WEIGHT * 100)}% identity and {int(PRONUNCIATION_WEIGHT * 100)}% pronunciation.",
        "- Emotion is intentionally excluded in this pass.",
        "",
        "## Model Summary",
        "",
        "| model | clips | identity | pronunciation | tali-likeness |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in model_rows:
        lines.append(
            f"| {row['model']} | {row['clips']} | {row['avg_identity_score']} | {row['avg_pronunciation_score']} | {row['avg_tali_likeness_score']} |"
        )

    lines.extend(
        [
            "",
            "## Pairwise Versus",
            "",
            "| prompt set | clip | 0.6b identity | 0.6b pron. | 0.6b final | 1.7b identity | 1.7b pron. | 1.7b final | winner |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in versus_rows:
        lines.append(
            f"| {row['prompt_set']} | {row['clip_index']} | {row['qwen_0_6b_identity_score']} | {row['qwen_0_6b_pronunciation_score']} | {row['qwen_0_6b_tali_likeness_score']} | {row['qwen_1_7b_identity_score']} | {row['qwen_1_7b_pronunciation_score']} | {row['qwen_1_7b_tali_likeness_score']} | {row['winner']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    base_scores_path = Path(args.base_scores)
    output_dir = Path(args.output_dir)
    asr_url = args.asr_url.rstrip("/")
    if not asr_url:
        raise RuntimeError("Missing ASR URL. Set AUDIO_EVAL_ASR_URL in .env or pass --asr-url.")

    base_rows = read_base_rows(base_scores_path)
    health = get_health(asr_url, args.asr_token, min(30, args.timeout))

    jobs: list[tuple[int, dict[str, str]]] = list(enumerate(base_rows))
    enriched_rows: list[dict[str, Any]] = [None] * len(jobs)  # type: ignore[list-item]

    def worker(job: tuple[int, dict[str, str]]) -> tuple[int, dict[str, Any]]:
        index, row = job
        audio_path = WORKSPACE_ROOT / row["generated_rel_path"]
        payload = transcribe_audio(audio_path, asr_url, args.asr_token, args.asr_model, args.language, args.timeout)
        transcript = str(payload.get("text", "")).strip()
        if row.get("speaker_reference_similarity_score"):
            identity_score = round(float(row["speaker_reference_similarity_score"]), 3)
        else:
            identity_score = round(float(row["reference_similarity_score"]), 3)
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
                "avg_identity_score": mean([row["identity_score"] for row in model_rows]),
                "avg_pronunciation_score": mean([row["pronunciation_score"] for row in model_rows]),
                "avg_tali_likeness_score": mean([row["tali_likeness_score"] for row in model_rows]),
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
                "winning_margin": round(abs(right["tali_likeness_score"] - left["tali_likeness_score"]), 3),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "clip_scores.csv", rows)
    write_csv(output_dir / "model_summary.csv", model_summary)
    write_csv(output_dir / "versus.csv", versus_rows)
    write_markdown(output_dir / "report.md", model_summary, versus_rows)

    summary = {
        "asr_service_url": asr_url,
        "asr_service_health": health,
        "identity_weight": IDENTITY_WEIGHT,
        "pronunciation_weight": PRONUNCIATION_WEIGHT,
        "emotion_evaluated": False,
        "model_summary": model_summary,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    best_model = max(model_summary, key=lambda row: row["avg_tali_likeness_score"])
    print(
        json.dumps(
            {
                "clips": len(rows),
                "best_model": best_model["model"],
                "best_tali_likeness_score": best_model["avg_tali_likeness_score"],
                "output_dir": str(output_dir),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
