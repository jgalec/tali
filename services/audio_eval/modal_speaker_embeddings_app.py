import base64
import math
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

import modal


APP_NAME = "audio-eval-speaker-embeddings"
AUTH_SECRET_NAME = "audio-eval-api-auth"
AUTH_ENV_VAR = "AUDIO_EVAL_AUTH_TOKEN"
MODEL_CACHE_DIR = "/audio-eval-model-cache"
DEFAULT_MAX_INPUTS = int(os.getenv("AUDIO_EVAL_MAX_INPUTS", "2"))
DEFAULT_SAMPLE_RATE = 16000

SPEECHBRAIN_BACKEND = "speechbrain_ecapa"
WAVLM_BACKEND = "wavlm_sv"
PYANNOTE_BACKEND = "pyannote_embedding"
PRIMARY_BACKEND = SPEECHBRAIN_BACKEND

MODEL_NAMES = {
    SPEECHBRAIN_BACKEND: "speechbrain/spkrec-ecapa-voxceleb",
    WAVLM_BACKEND: "microsoft/wavlm-base-plus-sv",
    PYANNOTE_BACKEND: "pyannote/embedding",
}

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .env(
        {
            "PYTHONUNBUFFERED": "1",
            "HF_HOME": MODEL_CACHE_DIR,
            "HF_HUB_CACHE": MODEL_CACHE_DIR,
            "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1",
        }
    )
    .run_commands(
        "python -m pip install --upgrade pip",
        "python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 torchaudio==2.6.0",
        "python -m pip install 'fastapi[standard]>=0.115,<1.0' 'speechbrain>=1.0,<2.0' 'transformers>=4.46,<5.0' 'sentencepiece>=0.2,<1.0' 'pyannote.audio>=3.3,<4.0'",
    )
)

app = modal.App(APP_NAME)
model_cache = modal.Volume.from_name("audio-eval-model-cache", create_if_missing=True)


@app.function(
    image=image,
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

    import numpy as np
    import torch
    import torchaudio
    from fastapi import FastAPI, HTTPException, Request
    from pydantic import BaseModel
    from pyannote.audio import Inference
    from pyannote.audio import Model as PyannoteModel
    from speechbrain.inference.speaker import EncoderClassifier
    from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector

    ecapa_classifier: EncoderClassifier | None = None
    wavlm_feature_extractor: Wav2Vec2FeatureExtractor | None = None
    wavlm_model: WavLMForXVector | None = None
    pyannote_inference: Inference | None = None
    pyannote_token_loaded: str | None = None
    pyannote_status_message = "HF token required and user conditions must be accepted for pyannote/embedding."
    auth_token = os.getenv(AUTH_ENV_VAR, "")

    class EmbedRequest(BaseModel):
        audio_base64: str
        filename: str = "audio.wav"
        huggingface_token: str | None = None

    class CompareRequest(BaseModel):
        source_audio_base64: str
        target_audio_base64: str
        source_filename: str = "source.wav"
        target_filename: str = "target.wav"
        huggingface_token: str | None = None

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

    def normalize_embedding(values: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0.0:
            return [0.0 for _ in values]
        return [value / norm for value in values]

    def vector_to_payload(values: list[float]) -> dict[str, object]:
        norm = math.sqrt(sum(value * value for value in values))
        return {
            "embedding": values,
            "embedding_norm": norm,
        }

    def get_ecapa() -> EncoderClassifier:
        nonlocal ecapa_classifier
        if ecapa_classifier is None:
            ecapa_classifier = EncoderClassifier.from_hparams(
                source=MODEL_NAMES[SPEECHBRAIN_BACKEND],
                savedir=str(Path(MODEL_CACHE_DIR) / "ecapa"),
                run_opts={"device": "cpu"},
            )
        return ecapa_classifier

    def get_wavlm() -> tuple[Wav2Vec2FeatureExtractor, WavLMForXVector]:
        nonlocal wavlm_feature_extractor, wavlm_model
        if wavlm_feature_extractor is None:
            wavlm_feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(
                MODEL_NAMES[WAVLM_BACKEND],
                cache_dir=MODEL_CACHE_DIR,
            )
        if wavlm_model is None:
            wavlm_model = WavLMForXVector.from_pretrained(
                MODEL_NAMES[WAVLM_BACKEND],
                cache_dir=MODEL_CACHE_DIR,
            )
            cast(WavLMForXVector, wavlm_model).eval()
        assert wavlm_feature_extractor is not None
        assert wavlm_model is not None
        return wavlm_feature_extractor, wavlm_model

    def get_pyannote(huggingface_token: str | None) -> Inference | None:
        nonlocal pyannote_inference, pyannote_token_loaded, pyannote_status_message
        if not huggingface_token:
            return None
        if pyannote_inference is not None and pyannote_token_loaded == huggingface_token:
            return pyannote_inference

        try:
            pyannote_model = PyannoteModel.from_pretrained(
                MODEL_NAMES[PYANNOTE_BACKEND],
                use_auth_token=huggingface_token,
                cache_dir=MODEL_CACHE_DIR,
            )
            pyannote_inference = Inference(pyannote_model, window="whole")
            pyannote_token_loaded = huggingface_token
            pyannote_status_message = "ready"
            return pyannote_inference
        except Exception as exc:  # noqa: BLE001
            pyannote_status_message = str(exc)
            raise HTTPException(
                status_code=400,
                detail=(
                    "Could not load pyannote/embedding. Accept the model conditions on Hugging Face and pass a valid token. "
                    f"Underlying error: {exc}"
                ),
            ) from exc

    def decode_and_standardize_audio(audio_bytes: bytes, filename: str) -> tuple[Path, Any, int, float]:
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
            waveform = waveform.mean(dim=0)
            duration_seconds = float(waveform.shape[-1]) / float(sample_rate) if waveform.shape[-1] else 0.0
            return output_path, waveform, sample_rate, duration_seconds
        except subprocess.CalledProcessError as exc:
            raise HTTPException(status_code=400, detail=exc.stderr.strip() or "Could not decode audio") from exc
        finally:
            input_path.unlink(missing_ok=True)

    def compute_embeddings(audio_bytes: bytes, filename: str, huggingface_token: str | None) -> dict[str, object]:
        wav_path, waveform, sample_rate, duration_seconds = decode_and_standardize_audio(audio_bytes, filename)
        enabled_models: list[str] = []
        models_payload: dict[str, dict[str, object]] = {}

        try:
            with torch.inference_mode():
                ecapa_tensor = get_ecapa().encode_batch(waveform.unsqueeze(0)).squeeze().cpu()
                ecapa_embedding = [float(value) for value in ecapa_tensor.tolist()]
                models_payload[SPEECHBRAIN_BACKEND] = {
                    "model_name": MODEL_NAMES[SPEECHBRAIN_BACKEND],
                    **vector_to_payload(ecapa_embedding),
                }
                enabled_models.append(SPEECHBRAIN_BACKEND)

                wavlm_extractor, wavlm_encoder = get_wavlm()
                wavlm_inputs = wavlm_extractor(
                    [cast(np.ndarray, waveform.cpu().numpy())],
                    sampling_rate=sample_rate,
                    return_tensors="pt",
                    padding=True,
                )
                wavlm_outputs = wavlm_encoder(**wavlm_inputs)
                wavlm_embedding = [float(value) for value in wavlm_outputs.embeddings.squeeze().cpu().tolist()]
                models_payload[WAVLM_BACKEND] = {
                    "model_name": MODEL_NAMES[WAVLM_BACKEND],
                    **vector_to_payload(wavlm_embedding),
                }
                enabled_models.append(WAVLM_BACKEND)

            if huggingface_token:
                pyannote_runner = get_pyannote(huggingface_token)
                if pyannote_runner is not None:
                    pyannote_array = pyannote_runner(str(wav_path))
                    pyannote_embedding = [float(value) for value in np.asarray(pyannote_array).reshape(-1).tolist()]
                    models_payload[PYANNOTE_BACKEND] = {
                        "model_name": MODEL_NAMES[PYANNOTE_BACKEND],
                        **vector_to_payload(pyannote_embedding),
                    }
                    enabled_models.append(PYANNOTE_BACKEND)

            primary = models_payload[PRIMARY_BACKEND]
            return {
                "embedding": primary["embedding"],
                "embedding_norm": primary["embedding_norm"],
                "model": MODEL_NAMES[PRIMARY_BACKEND],
                "primary_backend": PRIMARY_BACKEND,
                "enabled_models": enabled_models,
                "models": models_payload,
                "duration_seconds": round(duration_seconds, 6),
                "sample_rate": DEFAULT_SAMPLE_RATE,
                "pyannote_requested": bool(huggingface_token),
                "pyannote_status": pyannote_status_message,
            }
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            wav_path.unlink(missing_ok=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        get_ecapa()
        get_wavlm()
        yield

    web_app = FastAPI(title="Audio Eval Speaker Embeddings", version="0.2.0", lifespan=lifespan)

    @web_app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        require_auth(request)
        get_ecapa()
        get_wavlm()
        return {
            "status": "ok",
            "sample_rate": DEFAULT_SAMPLE_RATE,
            "auth_enabled": bool(auth_token),
            "primary_backend": PRIMARY_BACKEND,
            "models": {
                SPEECHBRAIN_BACKEND: MODEL_NAMES[SPEECHBRAIN_BACKEND],
                WAVLM_BACKEND: MODEL_NAMES[WAVLM_BACKEND],
                PYANNOTE_BACKEND: MODEL_NAMES[PYANNOTE_BACKEND],
            },
            "pyannote_status": pyannote_status_message,
        }

    @web_app.post("/v1/audio/embed")
    async def embed_audio(request: Request, payload: EmbedRequest) -> dict[str, object]:
        require_auth(request)
        try:
            audio_bytes = base64.b64decode(payload.audio_base64.encode("ascii"), validate=True)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid base64 audio payload") from exc
        return compute_embeddings(audio_bytes, payload.filename, payload.huggingface_token)

    @web_app.post("/v1/audio/compare")
    async def compare_audio(request: Request, payload: CompareRequest) -> dict[str, object]:
        require_auth(request)
        try:
            source_bytes = base64.b64decode(payload.source_audio_base64.encode("ascii"), validate=True)
            target_bytes = base64.b64decode(payload.target_audio_base64.encode("ascii"), validate=True)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid base64 audio payload") from exc

        source = compute_embeddings(source_bytes, payload.source_filename, payload.huggingface_token)
        target = compute_embeddings(target_bytes, payload.target_filename, payload.huggingface_token)
        source_models = cast(dict[str, dict[str, object]], source["models"])
        target_models = cast(dict[str, dict[str, object]], target["models"])
        per_model_cosine: dict[str, float] = {}

        for backend in sorted(set(source_models) & set(target_models)):
            source_embedding = normalize_embedding(cast(list[float], source_models[backend]["embedding"]))
            target_embedding = normalize_embedding(cast(list[float], target_models[backend]["embedding"]))
            cosine = sum(a * b for a, b in zip(source_embedding, target_embedding, strict=False))
            per_model_cosine[backend] = max(-1.0, min(1.0, float(cosine)))

        ensemble_cosine = sum(per_model_cosine.values()) / len(per_model_cosine) if per_model_cosine else 0.0

        return {
            "cosine_similarity": per_model_cosine.get(PRIMARY_BACKEND, 0.0),
            "ensemble_cosine_similarity": ensemble_cosine,
            "per_model_cosine_similarity": per_model_cosine,
            "source": {key: value for key, value in source.items() if key != "models"},
            "target": {key: value for key, value in target.items() if key != "models"},
            "models": {
                backend: {
                    "source_norm": source_models[backend]["embedding_norm"],
                    "target_norm": target_models[backend]["embedding_norm"],
                }
                for backend in per_model_cosine
            },
        }

    return web_app
