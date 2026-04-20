import os
import sys

import modal


APP_NAME = "voicebox-backend"
AUTH_SECRET_NAME = "voicebox-api-auth"
AUTH_ENV_VAR = "VOICEBOX_AUTH_TOKEN"
VOICEBOX_REPO_DIR = "/opt/voicebox"
VOICEBOX_DATA_DIR = "/voicebox-data"
VOICEBOX_MODELS_DIR = "/voicebox-models"
VOICEBOX_REPO_URL = "https://github.com/jamiepine/voicebox.git"


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "curl", "build-essential")
    .env(
        {
            "PYTHONUNBUFFERED": "1",
            "HF_HOME": VOICEBOX_MODELS_DIR,
            "HF_HUB_CACHE": VOICEBOX_MODELS_DIR,
            "VOICEBOX_MODELS_DIR": VOICEBOX_MODELS_DIR,
        }
    )
    .run_commands(
        f"git clone --depth 1 {VOICEBOX_REPO_URL} {VOICEBOX_REPO_DIR}",
        f"python -m pip install --upgrade pip && python -m pip install -r {VOICEBOX_REPO_DIR}/backend/requirements.txt",
        "python -m pip install --no-deps chatterbox-tts",
        "python -m pip install --no-deps hume-tada",
        "python -m pip install git+https://github.com/QwenLM/Qwen3-TTS.git",
    )
)


app = modal.App(APP_NAME)
voicebox_data = modal.Volume.from_name("voicebox-data", create_if_missing=True)
voicebox_models = modal.Volume.from_name("voicebox-models", create_if_missing=True)


@app.function(
    image=image,
    gpu="T4",
    cpu=4.0,
    memory=32768,
    timeout=1800,
    secrets=[modal.Secret.from_name(AUTH_SECRET_NAME)],
    volumes={
        VOICEBOX_DATA_DIR: voicebox_data,
        VOICEBOX_MODELS_DIR: voicebox_models,
    },
)
@modal.concurrent(max_inputs=5)
@modal.asgi_app()
def fastapi_app():
    import secrets

    os.environ.setdefault("VOICEBOX_MODELS_DIR", VOICEBOX_MODELS_DIR)
    os.environ.setdefault("HF_HOME", VOICEBOX_MODELS_DIR)
    os.environ.setdefault("HF_HUB_CACHE", VOICEBOX_MODELS_DIR)

    if VOICEBOX_REPO_DIR not in sys.path:
        sys.path.insert(0, VOICEBOX_REPO_DIR)

    from backend import config as voicebox_config

    voicebox_config.set_data_dir(VOICEBOX_DATA_DIR)

    from backend.app import create_app
    from fastapi import Request
    from fastapi.responses import JSONResponse

    application = create_app()
    auth_token = os.getenv(AUTH_ENV_VAR, "")

    @application.middleware("http")
    async def require_bearer_token(request: Request, call_next):
        if not auth_token:
            return await call_next(request)

        path = request.scope.get("path", "")
        token_prefix = "/token/"
        path_token = ""
        if path.startswith(token_prefix):
            remainder = path[len(token_prefix) :]
            parts = remainder.split("/", 1)
            path_token = parts[0]
            stripped_path = "/" + parts[1] if len(parts) > 1 else "/"
            request.scope["path"] = stripped_path
            request.scope["raw_path"] = stripped_path.encode("utf-8")

        header = request.headers.get("Authorization", "")
        prefix = "Bearer "
        query_token = request.query_params.get("token", "")
        provided = ""
        if header.startswith(prefix):
            provided = header[len(prefix):]
        elif path_token:
            provided = path_token
        elif query_token:
            provided = query_token
        else:
            return JSONResponse(status_code=401, content={"detail": "Missing auth token"})

        if not secrets.compare_digest(provided, auth_token):
            return JSONResponse(status_code=401, content={"detail": "Invalid auth token"})

        return await call_next(request)

    return application
