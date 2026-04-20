import base64
import math
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import cast

import modal


APP_NAME = "audio-eval-speaker-embeddings"
AUTH_SECRET_NAME = "audio-eval-api-auth"
AUTH_ENV_VAR = "AUDIO_EVAL_AUTH_TOKEN"
MODEL_CACHE_DIR = "/audio-eval-model-cache"
DEFAULT_MODEL_NAME = os.getenv("SPEAKER_EMBED_MODEL", "speechbrain/spkrec-ecapa-voxceleb")
DEFAULT_MAX_INPUTS = int(os.getenv("AUDIO_EVAL_MAX_INPUTS", "4"))
DEFAULT_SAMPLE_RATE = 16000

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .env(
        {
            "PYTHONUNBUFFERED": "1",
            "HF_HOME": MODEL_CACHE_DIR,
            "HF_HUB_CACHE": MODEL_CACHE_DIR,
        }
    )
    .run_commands(
        "python -m pip install --upgrade pip",
        "python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 torchaudio==2.6.0",
        "python -m pip install 'fastapi[standard]>=0.115,<1.0' 'speechbrain>=1.0,<2.0'",
    )
)

app = modal.App(APP_NAME)
model_cache = modal.Volume.from_name("audio-eval-model-cache", create_if_missing=True)


@app.function(
    image=image,
    cpu=4.0,
    memory=8192,
    timeout=900,
    secrets=[modal.Secret.from_name(AUTH_SECRET_NAME)],
    volumes={MODEL_CACHE_DIR: model_cache},
)
@modal.concurrent(max_inputs=DEFAULT_MAX_INPUTS)
@modal.asgi_app()
def fastapi_app():
    from contextlib import asynccontextmanager

    import torchaudio
    from fastapi import FastAPI, HTTPException, Request
    from pydantic import BaseModel
    from speechbrain.inference.speaker import EncoderClassifier

    classifier: EncoderClassifier | None = None
    auth_token = os.getenv(AUTH_ENV_VAR, "")

    class EmbedRequest(BaseModel):
        audio_base64: str
        filename: str = "audio.wav"

    class CompareRequest(BaseModel):
        source_audio_base64: str
        target_audio_base64: str
        source_filename: str = "source.wav"
        target_filename: str = "target.wav"

    def require_auth(request: Request) -> None:
        if not auth_token:
            return

        header = request.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            raise HTTPException(status_code=401, detail="Missing bearer token")

        provided_token = header[len(prefix) :]
        if not secrets.compare_digest(provided_token, auth_token):
            raise HTTPException(status_code=401, detail="Invalid bearer token")

    def get_classifier() -> EncoderClassifier:
        nonlocal classifier
        if classifier is None:
            classifier = EncoderClassifier.from_hparams(
                source=DEFAULT_MODEL_NAME,
                savedir=str(Path(MODEL_CACHE_DIR) / "ecapa"),
                run_opts={"device": "cpu"},
            )
        return classifier

    def decode_and_standardize_audio(audio_bytes: bytes, filename: str) -> tuple[Path, float]:
        input_suffix = Path(filename).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=input_suffix) as input_file:
            input_path = Path(input_file.name)
            input_file.write(audio_bytes)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as output_file:
            output_path = Path(output_file.name)

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            str(DEFAULT_SAMPLE_RATE),
            str(output_path),
        ]

        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            waveform, sample_rate = torchaudio.load(str(output_path))
            duration_seconds = float(waveform.shape[-1]) / float(sample_rate) if waveform.shape[-1] else 0.0
            return output_path, duration_seconds
        except subprocess.CalledProcessError as exc:
            raise HTTPException(status_code=400, detail=exc.stderr.strip() or "Could not decode audio") from exc
        finally:
            input_path.unlink(missing_ok=True)

    def build_embedding(audio_bytes: bytes, filename: str) -> dict[str, object]:
        wav_path, duration_seconds = decode_and_standardize_audio(audio_bytes, filename)
        try:
            waveform, _sample_rate = torchaudio.load(str(wav_path))
            signal = waveform.mean(dim=0)
            embedding_tensor = get_classifier().encode_batch(signal.unsqueeze(0)).squeeze().cpu()
            embedding = [float(value) for value in embedding_tensor.tolist()]
            embedding_norm = math.sqrt(sum(value * value for value in embedding))
            return {
                "embedding": embedding,
                "embedding_norm": embedding_norm,
                "duration_seconds": round(duration_seconds, 6),
                "sample_rate": DEFAULT_SAMPLE_RATE,
                "model": DEFAULT_MODEL_NAME,
            }
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            wav_path.unlink(missing_ok=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        get_classifier()
        yield

    web_app = FastAPI(title="Audio Eval Speaker Embeddings", version="0.1.0", lifespan=lifespan)

    @web_app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        require_auth(request)
        get_classifier()
        return {
            "status": "ok",
            "model": DEFAULT_MODEL_NAME,
            "sample_rate": DEFAULT_SAMPLE_RATE,
            "auth_enabled": bool(auth_token),
        }

    @web_app.post("/v1/audio/embed")
    async def embed_audio(request: Request, payload: EmbedRequest) -> dict[str, object]:
        require_auth(request)
        try:
            audio_bytes = base64.b64decode(payload.audio_base64.encode("ascii"), validate=True)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid base64 audio payload") from exc
        return build_embedding(audio_bytes, payload.filename)

    @web_app.post("/v1/audio/compare")
    async def compare_audio(request: Request, payload: CompareRequest) -> dict[str, object]:
        require_auth(request)
        try:
            source_bytes = base64.b64decode(payload.source_audio_base64.encode("ascii"), validate=True)
            target_bytes = base64.b64decode(payload.target_audio_base64.encode("ascii"), validate=True)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid base64 audio payload") from exc

        source = build_embedding(source_bytes, payload.source_filename)
        target = build_embedding(target_bytes, payload.target_filename)
        source_embedding = cast(list[float], source["embedding"])
        target_embedding = cast(list[float], target["embedding"])
        cosine = sum(a * b for a, b in zip(source_embedding, target_embedding, strict=False))

        return {
            "cosine_similarity": max(-1.0, min(1.0, float(cosine))),
            "source": {key: value for key, value in source.items() if key != "embedding"},
            "target": {key: value for key, value in target.items() if key != "embedding"},
            "model": DEFAULT_MODEL_NAME,
        }

    return web_app
