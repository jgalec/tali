from __future__ import annotations

import base64
import json
import mimetypes
import os
import tempfile
import time
import string
from pathlib import Path
from typing import Any
from urllib import error, parse, request
from uuid import uuid4

import gradio as gr


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

DEFAULT_BASE_URL = os.getenv("VOICEBOX_UI_BASE_URL", "")
DEFAULT_AUTH_TOKEN = os.getenv("VOICEBOX_AUTH_TOKEN", "")
DEFAULT_TIMEOUT = int(os.getenv("VOICEBOX_UI_TIMEOUT", "300"))
DEFAULT_EVAL_SPEAKER_URL = os.getenv("AUDIO_EVAL_EMBED_URL", "")
DEFAULT_EVAL_SPEAKER_TOKEN = os.getenv("AUDIO_EVAL_AUTH_TOKEN", "")
DEFAULT_EVAL_ASR_URL = os.getenv("AUDIO_EVAL_ASR_URL", "")
DEFAULT_EVAL_ASR_TOKEN = os.getenv("AUDIO_EVAL_ASR_TOKEN", "")
DEFAULT_EVAL_PYANNOTE_TOKEN = os.getenv("AUDIO_EVAL_PYANNOTE_HF_TOKEN", "")
DEFAULT_EVAL_ASR_MODEL = os.getenv("AUDIO_EVAL_ASR_MODEL", "large-v3")
DEFAULT_EVAL_LANGUAGE = os.getenv("AUDIO_EVAL_ASR_LANGUAGE", "en")
REFERENCE_DIR = WORKSPACE_ROOT / "voices" / "me2_voice_reference_candidates"
IDENTITY_WEIGHT = 0.7
PRONUNCIATION_WEIGHT = 0.3
DOC_NOTE_PATHS = {
    "Voice Lab Plan": WORKSPACE_ROOT / "docs" / "voice-lab-ui-plan.md",
    "Audio Evaluation": WORKSPACE_ROOT / "docs" / "audio-evaluation.md",
    "Cloning vs Fine-Tuning": WORKSPACE_ROOT / "docs" / "voice-cloning-vs-fine-tuning.md",
}

SUPPORTED_ENGINES = ["qwen", "qwen_custom_voice", "luxtts", "chatterbox", "chatterbox_turbo", "tada", "kokoro"]
SUPPORTED_MODEL_SIZES = ["1.7B", "0.6B", "1B", "3B"]
SUPPORTED_LANGUAGES = ["en", "zh", "ja", "ko", "de", "fr", "ru", "pt", "es", "it", "he", "ar", "da", "el", "fi", "hi", "ms", "nl", "no", "pl", "sv", "sw", "tr"]
PRIMARY_SPEAKER_BACKENDS = ("speechbrain_ecapa", "wavlm_sv", "pyannote_embedding")
PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation)
REFERENCE_BANK_CACHE: dict[str, Any] | None = None


def build_headers(token: str, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(extra_headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def join_url(base_url: str, endpoint: str) -> str:
    return f"{base_url.rstrip('/')}{endpoint}"


def request_json(url: str, token: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    body = None
    headers = build_headers(token, {"Accept": "application/json"})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach backend: {exc}") from exc


def request_text(url: str, token: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    req = request.Request(url, headers=build_headers(token), method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach backend: {exc}") from exc


def build_multipart_body(boundary: str, fields: dict[str, str], file_field: str, file_path: Path, mime_type: str) -> bytes:
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
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks)


def upload_file(url: str, token: str, file_path: Path, field_name: str, fields: dict[str, str], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    boundary = f"----VoiceLab{uuid4().hex}"
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body = build_multipart_body(boundary, fields, field_name, file_path, mime_type)
    headers = build_headers(token, {"Accept": "application/json", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed with HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach backend: {exc}") from exc


def fetch_binary(url: str, token: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    req = request.Request(url, headers=build_headers(token), method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {detail}") from exc


def post_json(url: str, token: str, payload: dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    return request_json(url, token, method="POST", payload=payload, timeout=timeout)


def audio_bytes_to_temp_file(audio_bytes: bytes, suffix: str = ".wav") -> str:
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.write(audio_bytes)
    temp_file.flush()
    temp_file.close()
    return temp_file.name


def profiles_choices(profiles_payload: list[dict[str, Any]]) -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = []
    for profile in profiles_payload:
        label = f"{profile.get('name', 'Unnamed')} ({profile.get('id', '')})"
        choices.append((label, str(profile.get("id", ""))))
    return choices


def format_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def read_markdown(path: Path) -> str:
    if not path.exists():
        return f"Missing file: `{path}`"
    return path.read_text(encoding="utf-8")


def load_doc_note(label: str) -> str:
    path = DOC_NOTE_PATHS.get(label)
    if path is None:
        raise gr.Error(f"Unknown note: {label}")
    return read_markdown(path)


def normalize_text(value: str) -> str:
    lowered = value.lower().replace("'", "")
    return " ".join(lowered.translate(PUNCT_TRANSLATION).split())


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


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


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


def fetch_speaker_models(audio_path: Path, speaker_url: str, speaker_token: str, pyannote_token: str) -> dict[str, list[float]]:
    payload: dict[str, Any] = {
        "filename": audio_path.name,
        "audio_base64": base64.b64encode(audio_path.read_bytes()).decode("ascii"),
    }
    if pyannote_token:
        payload["huggingface_token"] = pyannote_token
    response = post_json(join_url(speaker_url, "/v1/audio/embed"), speaker_token, payload)
    models = response.get("models", {})
    embeddings: dict[str, list[float]] = {}
    if isinstance(models, dict):
        for backend, backend_payload in models.items():
            if isinstance(backend_payload, dict) and isinstance(backend_payload.get("embedding"), list):
                embeddings[str(backend)] = normalize_embedding([float(value) for value in backend_payload["embedding"]])
    elif isinstance(response.get("embedding"), list):
        embeddings["speechbrain_ecapa"] = normalize_embedding([float(value) for value in response["embedding"]])
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


def load_reference_bank(speaker_url: str, speaker_token: str, pyannote_token: str) -> dict[str, Any]:
    global REFERENCE_BANK_CACHE
    cache_key = json.dumps({"speaker_url": speaker_url, "pyannote": bool(pyannote_token)}, sort_keys=True)
    if REFERENCE_BANK_CACHE and REFERENCE_BANK_CACHE.get("cache_key") == cache_key:
        return REFERENCE_BANK_CACHE

    references_path = REFERENCE_DIR / "references.json"
    references = json.loads(references_path.read_text(encoding="utf-8"))
    reference_rows: list[dict[str, Any]] = []
    for row in references:
        wav_path = REFERENCE_DIR / row["output_file"]
        embeddings = fetch_speaker_models(wav_path, speaker_url, speaker_token, pyannote_token)
        reference_rows.append(
            {
                "name": row["name"],
                "file": row["output_file"],
                "transcript": row.get("transcript", ""),
                "embeddings": embeddings,
            }
        )

    backend_means: dict[str, list[float]] = {}
    for backend in PRIMARY_SPEAKER_BACKENDS:
        vectors = [row["embeddings"][backend] for row in reference_rows if backend in row["embeddings"]]
        if vectors:
            backend_means[backend] = mean_embedding(vectors)

    REFERENCE_BANK_CACHE = {
        "cache_key": cache_key,
        "references": reference_rows,
        "backend_means": backend_means,
    }
    return REFERENCE_BANK_CACHE


def transcribe_audio_for_eval(audio_path: Path, asr_url: str, asr_token: str, model: str, language: str) -> dict[str, Any]:
    boundary = f"----VoiceLabEval{uuid4().hex}"
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    body = build_multipart_body(boundary, {"model": model, "language": language}, "file", audio_path, mime_type)
    headers = build_headers(asr_token, {"Accept": "application/json", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    req = request.Request(join_url(asr_url, "/v1/audio/transcriptions"), data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ASR request failed with HTTP {exc.code}: {detail}") from exc


def evaluate_audio_clip(audio_file: str | None, expected_text: str) -> tuple[str, str, str]:
    if not audio_file:
        raise gr.Error("Provide an audio file to evaluate.")
    if not DEFAULT_EVAL_SPEAKER_URL or not DEFAULT_EVAL_SPEAKER_TOKEN:
        raise gr.Error("Audio evaluation speaker service is not configured in .env.")
    if not DEFAULT_EVAL_ASR_URL or not DEFAULT_EVAL_ASR_TOKEN:
        raise gr.Error("Audio evaluation ASR service is not configured in .env.")

    audio_path = Path(audio_file)
    reference_bank = load_reference_bank(DEFAULT_EVAL_SPEAKER_URL, DEFAULT_EVAL_SPEAKER_TOKEN, DEFAULT_EVAL_PYANNOTE_TOKEN)
    clip_embeddings = fetch_speaker_models(audio_path, DEFAULT_EVAL_SPEAKER_URL, DEFAULT_EVAL_SPEAKER_TOKEN, DEFAULT_EVAL_PYANNOTE_TOKEN)

    backend_scores: dict[str, float] = {}
    for backend, mean_vector in reference_bank["backend_means"].items():
        vector = clip_embeddings.get(backend)
        if vector is None:
            continue
        backend_scores[backend] = cosine_to_score(cosine_similarity(vector, mean_vector))

    identity_score = mean(list(backend_scores.values()))
    nearest_reference_name = ""
    nearest_reference_score = 0.0
    for reference in reference_bank["references"]:
        per_reference_scores: list[float] = []
        for backend, vector in clip_embeddings.items():
            reference_vector = reference["embeddings"].get(backend)
            if reference_vector is None:
                continue
            per_reference_scores.append(cosine_to_score(cosine_similarity(vector, reference_vector)))
        combined = mean(per_reference_scores)
        if combined > nearest_reference_score:
            nearest_reference_score = combined
            nearest_reference_name = reference["name"]

    transcript_payload = transcribe_audio_for_eval(audio_path, DEFAULT_EVAL_ASR_URL, DEFAULT_EVAL_ASR_TOKEN, DEFAULT_EVAL_ASR_MODEL, DEFAULT_EVAL_LANGUAGE)
    transcript = str(transcript_payload.get("text", "")).strip()
    pron_score = pronunciation_score(expected_text, transcript) if expected_text.strip() else 0.0
    final_score = round(IDENTITY_WEIGHT * identity_score + PRONUNCIATION_WEIGHT * pron_score, 3) if expected_text.strip() else identity_score

    summary_text = (
        f"Best reference: {nearest_reference_name or 'n/a'}\n"
        f"Identity score: {identity_score}\n"
        f"Pronunciation score: {pron_score}\n"
        f"Final Tali-likeness: {final_score}"
    )
    summary_json = {
        "best_reference": nearest_reference_name,
        "nearest_reference_score": nearest_reference_score,
        "identity_score": identity_score,
        "backend_identity_scores": backend_scores,
        "pronunciation_score": pron_score,
        "final_tali_likeness_score": final_score,
        "expected_text": expected_text,
        "transcribed_text": transcript,
        "word_error_rate": round(word_error_rate(expected_text, transcript), 4) if expected_text.strip() else None,
        "char_error_rate": round(char_error_rate(expected_text, transcript), 4) if expected_text.strip() else None,
    }
    return transcript, summary_text, format_json(summary_json)


def check_health(base_url: str, token: str) -> tuple[str, str]:
    if not base_url.strip():
        raise gr.Error("Enter a backend URL first.")
    payload = request_json(join_url(base_url, "/health"), token)
    return "Connected", format_json(payload)


def load_profiles(base_url: str, token: str) -> tuple[gr.Dropdown, str]:
    if not base_url.strip():
        raise gr.Error("Enter a backend URL first.")
    payload = request_json(join_url(base_url, "/profiles"), token)
    if not isinstance(payload, list):
        raise gr.Error("Unexpected /profiles response.")
    choices = profiles_choices(payload)
    selected = choices[0][1] if choices else None
    return gr.Dropdown(choices=choices, value=selected), format_json(payload)


def create_profile(base_url: str, token: str, name: str, description: str, language: str, default_engine: str) -> tuple[str, str]:
    if not name.strip():
        raise gr.Error("Profile name is required.")
    payload = {
        "name": name.strip(),
        "description": description.strip() or None,
        "language": language,
        "voice_type": "cloned",
        "default_engine": default_engine,
    }
    response = request_json(join_url(base_url, "/profiles"), token, method="POST", payload=payload)
    return str(response.get("id", "")), format_json(response)


def upload_profile_sample(base_url: str, token: str, profile_id: str, sample_file: str | None, reference_text: str) -> str:
    if not profile_id:
        raise gr.Error("Choose or create a profile first.")
    if not sample_file:
        raise gr.Error("Upload a sample audio file first.")
    if not reference_text.strip():
        raise gr.Error("Reference text is required.")
    response = upload_file(
        join_url(base_url, f"/profiles/{parse.quote(profile_id)}/samples"),
        token,
        Path(sample_file),
        "file",
        {"reference_text": reference_text.strip()},
    )
    return format_json(response)


def wait_for_generation(base_url: str, token: str, generation_id: str, poll_seconds: float = 1.0, timeout_seconds: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_payload: dict[str, Any] = {}
    while time.time() < deadline:
        raw = request_text(join_url(base_url, f"/generate/{parse.quote(generation_id)}/status"), token, timeout=timeout_seconds)
        payload = {}
        for line in raw.splitlines():
            if not line.startswith("data:"):
                continue
            candidate = line[len("data:") :].strip()
            if not candidate:
                continue
            payload = json.loads(candidate)
        if not payload:
            raise RuntimeError(f"Could not parse generation status response for {generation_id}.")
        last_payload = payload
        status = str(payload.get("status", ""))
        if status in {"completed", "failed", "not_found"}:
            return payload
        time.sleep(poll_seconds)
    raise RuntimeError(f"Generation {generation_id} did not finish before timeout.")


def generate_line(
    base_url: str,
    token: str,
    profile_id: str,
    text: str,
    language: str,
    engine: str,
    model_size: str,
    instruct: str,
    seed: float | None,
    normalize: bool,
    max_chunk_chars: int,
    crossfade_ms: int,
) -> tuple[str, str, str | None, str]:
    if not profile_id:
        raise gr.Error("Choose a profile first.")
    if not text.strip():
        raise gr.Error("Enter text to generate.")

    payload: dict[str, Any] = {
        "profile_id": profile_id,
        "text": text.strip(),
        "language": language,
        "engine": engine,
        "model_size": model_size,
        "normalize": normalize,
        "max_chunk_chars": int(max_chunk_chars),
        "crossfade_ms": int(crossfade_ms),
    }
    if instruct.strip():
        payload["instruct"] = instruct.strip()
    if seed is not None:
        payload["seed"] = int(seed)

    response = request_json(join_url(base_url, "/generate"), token, method="POST", payload=payload)
    generation_id = str(response.get("id", ""))
    if not generation_id:
        raise gr.Error("Backend did not return a generation id.")

    status_payload = wait_for_generation(base_url, token, generation_id)
    final_status = str(status_payload.get("status", ""))
    if final_status != "completed":
        raise gr.Error(f"Generation ended with status '{final_status}': {format_json(status_payload)}")

    audio_bytes = fetch_binary(join_url(base_url, f"/audio/{parse.quote(generation_id)}"), token)
    audio_path = audio_bytes_to_temp_file(audio_bytes)
    return generation_id, format_json(response), audio_path, format_json(status_payload)


with gr.Blocks(title="Tali Voice Lab") as demo:
    gr.Markdown("# Tali Voice Lab")
    gr.Markdown(
        "Local workbench for the current Tali cloning workflow. Move left to right: connect to the backend, prepare a profile, generate a line, then evaluate the result."
    )

    with gr.Tabs():
        with gr.Tab("1. Connect"):
            gr.Markdown("## Backend Connection")
            gr.Markdown("Start here. This section tells the UI where your remote Voicebox backend lives, whether the token works, and which profiles are currently available on the backend.")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 1. Voicebox base URL")
                    gr.Markdown("Paste the base URL of the Voicebox backend here. The UI sends all health, profile, upload, and generation requests to this server.")
                    base_url = gr.Textbox(label="Voicebox base URL", value=DEFAULT_BASE_URL, placeholder="https://...modal.run")

                    gr.Markdown("### 2. Auth token")
                    gr.Markdown("Use the bearer token that protects the Voicebox backend. If the token is wrong, health checks and all later actions will fail.")
                    auth_token = gr.Textbox(label="Auth token", value=DEFAULT_AUTH_TOKEN, type="password")

                    gr.Markdown("### 3. Connect actions")
                    gr.Markdown("Use `Check health` first to verify the backend is reachable. Use `Load profiles` after that to fetch the list of clone profiles stored on the server.")
                    with gr.Row():
                        health_button = gr.Button("Check health", variant="primary")
                        refresh_profiles_button = gr.Button("Load profiles")

                    gr.Markdown("### 4. Connection status")
                    gr.Markdown("This field gives you a quick human-readable result for the last connectivity check.")
                    health_status = gr.Textbox(label="Connection status", interactive=False)

                    gr.Markdown("### 5. Existing profile")
                    gr.Markdown("This dropdown is filled from the backend. Pick an existing profile here before uploading a sample or generating a new line.")
                    profile_selector = gr.Dropdown(label="Existing profile", choices=[], value=None)
                with gr.Column(scale=1):
                    gr.Markdown("### 6. Health JSON")
                    gr.Markdown("Raw `/health` response from the backend. Useful for checking GPU, backend type, model load state, and other low-level details.")
                    health_json = gr.Code(label="Health JSON", language="json")

                    gr.Markdown("### 7. Profiles JSON")
                    gr.Markdown("Raw `/profiles` response from the backend. Use this when you want to inspect profile metadata or debug what the server is returning.")
                    profiles_json = gr.Code(label="Profiles JSON", language="json")

            with gr.Accordion("Section notes", open=False):
                gr.Markdown(read_markdown(DOC_NOTE_PATHS["Voice Lab Plan"]))

        with gr.Tab("2. Profile Lab"):
            gr.Markdown("## Profile Setup")
            gr.Markdown("Use this section to create a fresh clone profile or to improve an existing one by uploading a new reference sample and its transcript.")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Create Profile")
                    gr.Markdown("Create a new empty cloned profile on the backend. After creation, reload profiles and select the new profile before adding samples.")

                    gr.Markdown("#### Profile name")
                    gr.Markdown("Short human-readable name for the profile. This is what you will recognize later in the profile list.")
                    profile_name = gr.Textbox(label="Profile name")

                    gr.Markdown("#### Description")
                    gr.Markdown("Optional note describing the intended voice quality, mood, or reference bundle for this profile.")
                    profile_description = gr.Textbox(label="Description", lines=3)

                    gr.Markdown("#### Language")
                    gr.Markdown("Primary language for the profile metadata. For this repo, `en` is usually the correct value.")
                    profile_language = gr.Dropdown(label="Language", choices=SUPPORTED_LANGUAGES, value="en")

                    gr.Markdown("#### Default engine")
                    gr.Markdown("Default TTS engine the backend should prefer for this profile. `qwen` is the current default path for Tali experiments.")
                    default_engine = gr.Dropdown(label="Default engine", choices=SUPPORTED_ENGINES, value="qwen")

                    gr.Markdown("#### Create action")
                    gr.Markdown("Sends the profile creation request to the backend.")
                    create_profile_button = gr.Button("Create profile", variant="primary")

                    gr.Markdown("#### Created profile id")
                    gr.Markdown("Backend-generated identifier for the profile you just created.")
                    created_profile_id = gr.Textbox(label="Created profile id", interactive=False)

                    gr.Markdown("#### Create profile response")
                    gr.Markdown("Raw JSON response returned after profile creation.")
                    create_profile_json = gr.Code(label="Create profile response", language="json")
                with gr.Column(scale=1):
                    gr.Markdown("### Add Reference Sample")
                    gr.Markdown("Attach a real audio clip to the currently selected profile. This is the core reference material that the backend uses for short-reference cloning.")

                    gr.Markdown("#### Reference sample")
                    gr.Markdown("Upload the audio clip that should teach the backend how this profile sounds.")
                    sample_file = gr.Audio(label="Reference sample", type="filepath")

                    gr.Markdown("#### Reference text")
                    gr.Markdown("Transcript that exactly matches the uploaded sample. Good alignment here matters a lot for clone quality.")
                    reference_text = gr.Textbox(label="Reference text", lines=6)

                    gr.Markdown("#### Upload action")
                    gr.Markdown("Uploads the sample to the profile selected in the Connect tab.")
                    add_sample_button = gr.Button("Upload sample to selected profile", variant="primary")

                    gr.Markdown("#### Add sample response")
                    gr.Markdown("Raw JSON response returned after the sample is stored on the backend.")
                    add_sample_json = gr.Code(label="Add sample response", language="json")

            with gr.Accordion("Why references matter", open=False):
                gr.Markdown(read_markdown(DOC_NOTE_PATHS["Cloning vs Fine-Tuning"]))

        with gr.Tab("3. Generate"):
            gr.Markdown("## Generation")
            gr.Markdown("Once a profile is ready, use this section to synthesize a new line and inspect both the returned metadata and the final audio file.")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 1. Target text")
                    gr.Markdown("The exact new line you want the backend to speak using the selected profile.")
                    generation_text = gr.Textbox(label="Target text", lines=8)

                    gr.Markdown("### 2. Optional instruct")
                    gr.Markdown("Optional style hint passed to the engine. Leave empty if you want the cleanest baseline test.")
                    generation_instruct = gr.Textbox(label="Optional instruct", lines=3)

                    gr.Markdown("### 3. Seed")
                    gr.Markdown("Optional random seed. Use this when you want more repeatable runs while comparing prompts or models.")
                    generation_seed = gr.Number(label="Seed", precision=0, value=None)

                    gr.Markdown("### 4. Normalize output")
                    gr.Markdown("If enabled, the backend normalizes output loudness before returning the WAV.")
                    generation_normalize = gr.Checkbox(label="Normalize output", value=True)
                with gr.Column(scale=1):
                    gr.Markdown("### 5. Generation language")
                    gr.Markdown("Language code passed to the backend for the generated line.")
                    generation_language = gr.Dropdown(label="Generation language", choices=SUPPORTED_LANGUAGES, value="en")

                    gr.Markdown("### 6. Engine")
                    gr.Markdown("TTS engine to use on the backend. `qwen` is the current main path for Tali tests.")
                    generation_engine = gr.Dropdown(label="Engine", choices=SUPPORTED_ENGINES, value="qwen")

                    gr.Markdown("### 7. Model size")
                    gr.Markdown("Model size for engines that support it. This is where you can compare `0.6B` vs `1.7B` style runs.")
                    generation_model_size = gr.Dropdown(label="Model size", choices=SUPPORTED_MODEL_SIZES, value="1.7B")

                    gr.Markdown("### 8. Max chunk chars")
                    gr.Markdown("Upper limit for chunk splitting when the text is long. Larger values keep more of the line together, smaller values are safer for long prompts.")
                    generation_max_chunk_chars = gr.Slider(label="Max chunk chars", minimum=100, maximum=5000, step=50, value=800)

                    gr.Markdown("### 9. Crossfade ms")
                    gr.Markdown("Crossfade between chunks when the backend has to split the line. Keep it low for short tests.")
                    generation_crossfade = gr.Slider(label="Crossfade ms", minimum=0, maximum=500, step=10, value=50)

                    gr.Markdown("### 10. Generate action")
                    gr.Markdown("Submits the generation request, waits for completion, and downloads the final WAV back into the UI.")
                    generate_button = gr.Button("Generate", variant="primary")

            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 11. Generated audio")
                    gr.Markdown("The final WAV returned by the backend after the generation finishes.")
                    generated_audio = gr.Audio(label="Generated audio", type="filepath", interactive=False)

                    gr.Markdown("### 12. Generation id")
                    gr.Markdown("Unique backend identifier for this generation. Useful if you later want to inspect the same generation directly on the backend.")
                    generation_id = gr.Textbox(label="Generation id", interactive=False)
                with gr.Column(scale=1):
                    gr.Markdown("### 13. Generate response")
                    gr.Markdown("Raw JSON returned immediately after the generation request is accepted.")
                    generation_response_json = gr.Code(label="Generate response", language="json")

                    gr.Markdown("### 14. Final status")
                    gr.Markdown("Parsed final status payload from the backend's status stream. This is where you confirm the generation actually completed.")
                    generation_status_json = gr.Code(label="Final status", language="json")

            with gr.Accordion("Generation workflow notes", open=False):
                gr.Markdown(read_markdown(DOC_NOTE_PATHS["Voice Lab Plan"]))

        with gr.Tab("4. Evaluate"):
            gr.Markdown("## Tali-Likeness Evaluation")
            gr.Markdown("This section scores the current audio with the same identity and pronunciation stack used elsewhere in the repo. It is a technical ranking aid, not a substitute for listening.")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 1. Expected text")
                    gr.Markdown("Paste the exact line that the audio is supposed to say. This is used to measure pronunciation through ASR alignment.")
                    evaluation_expected_text = gr.Textbox(label="Expected text", lines=6)

                    gr.Markdown("### 2. Evaluate action")
                    gr.Markdown("Runs the speaker ensemble plus Whisper transcription against the current audio loaded in the Generate tab.")
                    evaluate_button = gr.Button("Evaluate current audio", variant="primary")

                    gr.Markdown("### 3. ASR transcript")
                    gr.Markdown("Transcript detected by the Whisper evaluation service. Compare this with the expected text to spot pronunciation drift.")
                    evaluation_transcript = gr.Textbox(label="ASR transcript", lines=5, interactive=False)

                    gr.Markdown("### 4. Evaluation summary")
                    gr.Markdown("Short human-readable summary showing best matching reference, identity score, pronunciation score, and final Tali-likeness score.")
                    evaluation_summary = gr.Textbox(label="Evaluation summary", lines=7, interactive=False)
                with gr.Column(scale=1):
                    gr.Markdown("### 5. Evaluation JSON")
                    gr.Markdown("Detailed machine-readable evaluation output, including backend-specific identity subscores and error rates.")
                    evaluation_json = gr.Code(label="Evaluation JSON", language="json")

            with gr.Accordion("Evaluation notes", open=False):
                gr.Markdown(read_markdown(DOC_NOTE_PATHS["Audio Evaluation"]))

    health_button.click(check_health, inputs=[base_url, auth_token], outputs=[health_status, health_json])
    refresh_profiles_button.click(load_profiles, inputs=[base_url, auth_token], outputs=[profile_selector, profiles_json])
    create_profile_button.click(
        create_profile,
        inputs=[base_url, auth_token, profile_name, profile_description, profile_language, default_engine],
        outputs=[created_profile_id, create_profile_json],
    )
    add_sample_button.click(
        upload_profile_sample,
        inputs=[base_url, auth_token, profile_selector, sample_file, reference_text],
        outputs=[add_sample_json],
    )
    generate_button.click(
        generate_line,
        inputs=[
            base_url,
            auth_token,
            profile_selector,
            generation_text,
            generation_language,
            generation_engine,
            generation_model_size,
            generation_instruct,
            generation_seed,
            generation_normalize,
            generation_max_chunk_chars,
            generation_crossfade,
        ],
        outputs=[generation_id, generation_response_json, generated_audio, generation_status_json],
    )
    evaluate_button.click(
        evaluate_audio_clip,
        inputs=[generated_audio, evaluation_expected_text],
        outputs=[evaluation_transcript, evaluation_summary, evaluation_json],
    )


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
