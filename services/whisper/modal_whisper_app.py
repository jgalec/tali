import os

import modal

APP_NAME = "whisper-mvp"
AUTH_SECRET_NAME = "whisper-api-auth"
AUTH_ENV_VAR = "WHISPER_AUTH_TOKEN"
MODEL_CACHE_DIR = "/models"
DEFAULT_MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "large-v3")
DEFAULT_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
DEFAULT_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
DEFAULT_MAX_INPUTS = int(os.getenv("WHISPER_MAX_INPUTS", "1"))

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-devel-ubuntu22.04", add_python="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "fastapi[standard]>=0.115,<1.0",
        "faster-whisper>=1.1.0,<2.0",
        "python-multipart>=0.0.9,<1.0",
    )
)

app = modal.App(APP_NAME)
model_cache = modal.Volume.from_name("whisper-model-cache", create_if_missing=True)


@app.function(
    image=image,
    gpu="T4",
    cpu=4.0,
    memory=16384,
    timeout=900,
    secrets=[modal.Secret.from_name(AUTH_SECRET_NAME)],
    volumes={MODEL_CACHE_DIR: model_cache},
)
@modal.concurrent(max_inputs=DEFAULT_MAX_INPUTS)
@modal.asgi_app()
def fastapi_app():
    from contextlib import asynccontextmanager
    import tempfile
    from pathlib import Path
    import secrets

    from fastapi import FastAPI, HTTPException, Request
    from faster_whisper import WhisperModel

    model: WhisperModel | None = None
    auth_token = os.getenv(AUTH_ENV_VAR, "")

    def get_model() -> WhisperModel:
        nonlocal model
        if model is None:
            model = WhisperModel(
                DEFAULT_MODEL_NAME,
                device=DEFAULT_DEVICE,
                compute_type=DEFAULT_COMPUTE_TYPE,
                download_root=MODEL_CACHE_DIR,
            )
        return model

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        get_model()
        yield

    web_app = FastAPI(title="Whisper MVP", version="0.1.0", lifespan=lifespan)

    def require_auth(request: Request) -> None:
        if not auth_token:
            return

        header = request.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            raise HTTPException(status_code=401, detail="Missing bearer token")

        provided_token = header[len(prefix):]
        if not secrets.compare_digest(provided_token, auth_token):
            raise HTTPException(status_code=401, detail="Invalid bearer token")

    @web_app.get("/health")
    async def health(request: Request) -> dict[str, str | bool]:
        require_auth(request)
        get_model()
        return {
            "status": "ok",
            "loaded_model": DEFAULT_MODEL_NAME,
            "device": DEFAULT_DEVICE,
            "compute_type": DEFAULT_COMPUTE_TYPE,
            "auth_enabled": bool(auth_token),
        }

    @web_app.post("/v1/audio/transcriptions")
    async def transcribe_audio(request: Request) -> dict[str, object]:
        require_auth(request)
        form = await request.form()
        file = form.get("file")
        if file is None:
            raise HTTPException(status_code=400, detail="Missing file upload")
        if not hasattr(file, "filename") or not hasattr(file, "read"):
            raise HTTPException(status_code=400, detail="Invalid file upload")

        model_name = str(form.get("model") or DEFAULT_MODEL_NAME)
        language = form.get("language")
        prompt = form.get("prompt")
        filename = file.filename or "audio"
        suffix = Path(filename).suffix or ".bin"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(await file.read())

        try:
            whisper_model = get_model()
            segments, info = whisper_model.transcribe(
                str(temp_path),
                language=language or None,
                initial_prompt=prompt or None,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            temp_path.unlink(missing_ok=True)

        return {
            "text": text,
            "language": getattr(info, "language", language),
            "duration": getattr(info, "duration", None),
            "requested_model": model_name,
            "loaded_model": DEFAULT_MODEL_NAME,
        }

    return web_app
