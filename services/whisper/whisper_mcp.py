from __future__ import annotations

import json
import importlib
import mimetypes
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib import error, request
from uuid import uuid4

try:
    FastMCP = importlib.import_module("mcp.server.fastmcp").FastMCP
except ModuleNotFoundError as exc:
    _MISSING_MCP_EXCEPTION = exc

    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self._missing_exc = _MISSING_MCP_EXCEPTION

        def tool(self) -> Any:
            def decorator(func: Any) -> Any:
                return func

            return decorator

        def run(self) -> None:
            raise RuntimeError("Install the 'mcp' package to run this server.") from self._missing_exc


MCP_NAME = "whisper-client"
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIO_ROOT = WORKSPACE_ROOT / "me2_game_files"
DEFAULT_MANIFEST = WORKSPACE_ROOT / "me2_game_files_durations.txt"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_SERVER_URL = os.getenv("WHISPER_SERVER_URL", "http://localhost:8000")
DEFAULT_MODEL = os.getenv("WHISPER_MODEL", "large-v3")
DEFAULT_AUTH_TOKEN = os.getenv("WHISPER_AUTH_TOKEN")
DEFAULT_TIMEOUT = int(os.getenv("WHISPER_TIMEOUT", "300"))
DEFAULT_STATUS_TIMEOUT = int(os.getenv("WHISPER_STATUS_TIMEOUT", "30"))
AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".wma", ".aac", ".opus", ".xma", ".bik")

mcp = FastMCP(MCP_NAME)


def resolve_path(path_str: str | None, fallback: Path) -> Path:
    if not path_str:
        return fallback
    path = Path(path_str)
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def build_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(extra_headers or {})
    if DEFAULT_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {DEFAULT_AUTH_TOKEN}"
    return headers


def parse_manifest(manifest_path: Path) -> list[dict[str, str]]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    entries: list[dict[str, str]] = []
    current_folder: str | None = None

    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith("- "):
            current_folder = line
            continue
        if current_folder is None:
            raise ValueError(f"Audio entry without folder in manifest: {line}")
        stem, duration = line[2:].rsplit(": ", 1)
        entries.append({"folder": current_folder, "stem": stem, "duration": duration})

    return entries


def resolve_audio_file(audio_root: Path, folder: str, stem: str) -> Path:
    folder_path = audio_root / folder
    for extension in AUDIO_EXTENSIONS:
        candidate = folder_path / f"{stem}{extension}"
        if candidate.exists():
            return candidate

    matches = [candidate for candidate in folder_path.glob(f"{stem}.*") if candidate.suffix.lower() in AUDIO_EXTENSIONS]
    if matches:
        return matches[0]

    raise FileNotFoundError(f"Audio file not found for {folder}/{stem}")


def check_server(server_url: str, timeout: int = 5) -> dict[str, Any]:
    base_url = server_url.rstrip("/")
    endpoints = ("/health", "/v1/models", "/docs")
    errors: list[str] = []
    last_status_code: int | None = None
    last_url = base_url

    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        try:
            req = request.Request(url, headers=build_headers())
            with request.urlopen(req, timeout=timeout) as response:
                last_status_code = response.status
                last_url = url
                return {
                    "ok": True,
                    "status_code": response.status,
                    "url": url,
                }
        except error.HTTPError as exc:
            last_status_code = exc.code
            last_url = url
            errors.append(f"{endpoint}: HTTP {exc.code}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{endpoint}: {exc}")

    return {
        "ok": False,
        "status_code": last_status_code,
        "url": last_url,
        "errors": errors,
    }


def transcribe_with_server(
    audio_path: Path,
    server_url: str,
    model: str,
    language: str | None,
    prompt: str | None,
    timeout: int,
) -> dict[str, Any]:
    url = f"{server_url.rstrip('/')}/v1/audio/transcriptions"
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    data = {"model": model}
    if language:
        data["language"] = language
    if prompt:
        data["prompt"] = prompt

    boundary = f"----OpenCodeWhisper{uuid4().hex}"
    body = build_multipart_body(boundary=boundary, fields=data, file_path=audio_path, mime_type=mime_type)
    req = request.Request(
        url,
        data=body,
        headers=build_headers({"Content-Type": f"multipart/form-data; boundary={boundary}"}),
        method="POST",
    )

    with request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    return {
        "text": payload.get("text", "").strip(),
        "raw_response": payload,
    }


def build_multipart_body(boundary: str, fields: dict[str, str], file_path: Path, mime_type: str) -> bytes:
    chunks: list[bytes] = []

    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
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


def load_existing_results(jsonl_path: Path) -> dict[str, dict[str, Any]]:
    if not jsonl_path.exists():
        return {}

    results: dict[str, dict[str, Any]] = {}
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        results[entry["audio_rel_path"]] = entry
    return results


def write_outputs(results: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "transcriptions.jsonl"
    txt_path = output_dir / "transcriptions.txt"

    ordered_results = sorted(results, key=lambda item: (item["folder"], item["stem"]))
    jsonl_lines = [json.dumps(item, ensure_ascii=True) for item in ordered_results]
    jsonl_path.write_text("\n".join(jsonl_lines) + ("\n" if jsonl_lines else ""), encoding="utf-8")

    grouped_text: dict[str, list[str]] = {}
    for item in ordered_results:
        grouped_text.setdefault(item["folder"], [])
        if item["status"] == "ok":
            text = item["text"] or "[empty transcription]"
            grouped_text[item["folder"]].append(f"- {item['stem']} ({item['duration']}): {text}")
        else:
            grouped_text[item["folder"]].append(f"- {item['stem']} ({item['duration']}): [ERROR] {item['error']}")

    lines: list[str] = []
    for folder, items in grouped_text.items():
        lines.append(folder)
        lines.extend(items)
        lines.append("")
    txt_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    return {
        "jsonl_path": str(jsonl_path),
        "txt_path": str(txt_path),
    }


def make_result_entry(entry: dict[str, str], audio_path: Path, response: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
    result = {
        "folder": entry["folder"],
        "stem": entry["stem"],
        "duration": entry["duration"],
        "audio_rel_path": str(audio_path.relative_to(WORKSPACE_ROOT)),
        "status": "ok" if error is None else "error",
        "text": "",
        "error": error,
    }
    if response is not None:
        result["text"] = response["text"]
        result["raw_response"] = response["raw_response"]
    return result


@mcp.tool()
def whisper_server_status(server_url: str = DEFAULT_SERVER_URL, timeout: int = DEFAULT_STATUS_TIMEOUT) -> dict[str, Any]:
    return check_server(server_url=server_url, timeout=timeout)


@mcp.tool()
def transcribe_audio(
    file_path: str,
    server_url: str = DEFAULT_SERVER_URL,
    model: str = DEFAULT_MODEL,
    language: str | None = "en",
    prompt: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    audio_path = resolve_path(file_path, DEFAULT_AUDIO_ROOT)
    response = transcribe_with_server(
        audio_path=audio_path,
        server_url=server_url,
        model=model,
        language=language,
        prompt=prompt,
        timeout=timeout,
    )
    return {
        "audio_path": str(audio_path),
        "text": response["text"],
    }


@mcp.tool()
def transcribe_manifest(
    manifest_path: str = str(DEFAULT_MANIFEST.relative_to(WORKSPACE_ROOT)),
    audio_root: str = str(DEFAULT_AUDIO_ROOT.relative_to(WORKSPACE_ROOT)),
    output_dir: str = str(DEFAULT_OUTPUT_DIR.relative_to(WORKSPACE_ROOT)),
    server_url: str = DEFAULT_SERVER_URL,
    model: str = DEFAULT_MODEL,
    language: str | None = "en",
    prompt: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_workers: int = 1,
    limit: int = 0,
    resume: bool = True,
) -> dict[str, Any]:
    manifest = resolve_path(manifest_path, DEFAULT_MANIFEST)
    resolved_audio_root = resolve_path(audio_root, DEFAULT_AUDIO_ROOT)
    resolved_output_dir = resolve_path(output_dir, DEFAULT_OUTPUT_DIR)

    status_timeout = min(timeout, DEFAULT_STATUS_TIMEOUT)
    status = check_server(server_url=server_url, timeout=status_timeout)
    if not status.get("ok"):
        raise RuntimeError(f"Whisper server unavailable: {status}")

    entries = parse_manifest(manifest)
    if limit > 0:
        entries = entries[:limit]

    existing_results = load_existing_results(resolved_output_dir / "transcriptions.jsonl") if resume else {}
    results: list[dict[str, Any]] = []
    pending_jobs: list[tuple[int, dict[str, str], Path]] = []
    skipped = 0

    for index, entry in enumerate(entries):
        audio_path = resolve_audio_file(resolved_audio_root, entry["folder"], entry["stem"])
        audio_rel_path = str(audio_path.relative_to(WORKSPACE_ROOT))
        if resume and audio_rel_path in existing_results:
            results.append(existing_results[audio_rel_path])
            skipped += 1
            continue
        pending_jobs.append((index, entry, audio_path))

    def worker(job: tuple[int, dict[str, str], Path]) -> tuple[int, dict[str, Any]]:
        index, entry, audio_path = job
        try:
            response = transcribe_with_server(
                audio_path=audio_path,
                server_url=server_url,
                model=model,
                language=language,
                prompt=prompt,
                timeout=timeout,
            )
            return index, make_result_entry(entry, audio_path, response=response)
        except Exception as exc:  # noqa: BLE001
            return index, make_result_entry(entry, audio_path, error=str(exc))

    max_workers = max(1, max_workers)
    if max_workers == 1:
        for job in pending_jobs:
            _, result = worker(job)
            results.append(result)
    else:
        buffered_results: list[tuple[int, dict[str, Any]]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(worker, job): job[0] for job in pending_jobs}
            for future in as_completed(future_map):
                buffered_results.append(future.result())
        for _, result in sorted(buffered_results, key=lambda item: item[0]):
            results.append(result)

    paths = write_outputs(results, resolved_output_dir)
    success_count = sum(1 for item in results if item["status"] == "ok")
    error_count = sum(1 for item in results if item["status"] == "error")

    return {
        "manifest_path": str(manifest),
        "audio_root": str(resolved_audio_root),
        "processed": len(entries),
        "transcribed_now": len(pending_jobs),
        "resumed": skipped,
        "success_count": success_count,
        "error_count": error_count,
        "server_url": server_url,
        "model": model,
        "output": paths,
    }


if __name__ == "__main__":
    mcp.run()
