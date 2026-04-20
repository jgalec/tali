# Whisper Backend on Modal

This document explains how the Whisper backend was built and deployed on Modal.

## Goal

- Run Whisper as a standalone HTTP service on Modal.
- Keep the model loaded inside the container instead of loading it per request.
- Let the local client act as a thin caller only.
- Protect the endpoint with a bearer token.

## Source File

- `services/whisper/modal_whisper_app.py`

## Main Design

The service is a small FastAPI app wrapped by Modal:

- Modal builds the runtime image.
- FastAPI exposes the HTTP endpoints.
- `faster-whisper` performs the transcription.
- A Modal `Volume` caches downloaded model files.
- A Modal `Secret` injects the API token.

## Image Setup

The Modal image uses:

- base image: `nvidia/cuda:12.4.1-devel-ubuntu22.04`
- Python: `3.11`
- system package: `ffmpeg`
- Python packages:
  - `fastapi[standard]`
  - `faster-whisper`
  - `python-multipart`

CUDA was chosen because the deployed version uses a GPU-backed Whisper model.

## Runtime Resources

Current Modal settings:

- GPU: `T4`
- CPU: `4`
- Memory: `16384` MiB
- Timeout: `900` seconds
- Max concurrent inputs per container: `1`

This was chosen to run `large-v3` on GPU while staying relatively simple.

## Model Loading Strategy

The service keeps one global model instance per container.

How it works:

- `get_model()` lazily creates the `WhisperModel`
- the FastAPI lifespan hook calls `get_model()` during startup
- later requests reuse the already-loaded model

Current default model settings:

- model: `large-v3`
- device: `cuda`
- compute type: `float16`

These values are still configurable through environment variables:

- `WHISPER_MODEL_NAME`
- `WHISPER_DEVICE`
- `WHISPER_COMPUTE_TYPE`

## Persistent Model Cache

The service mounts this Modal volume:

- volume name: `whisper-model-cache`
- mount path: `/models`

The model download root is set to `/models`, so later cold starts reuse cached weights instead of downloading again.

## Authentication

The backend is protected with a bearer token.

Implementation:

- Modal secret name: `whisper-api-auth`
- env var inside the container: `WHISPER_AUTH_TOKEN`
- requests must send `Authorization: Bearer <token>`

If the secret is missing or empty, auth is effectively disabled. If present, both `/health` and `/v1/audio/transcriptions` require it.

## Endpoints

The service exposes two main routes:

- `GET /health`
- `POST /v1/audio/transcriptions`

### `GET /health`

Returns basic status information:

- service status
- loaded model
- device
- compute type
- whether auth is enabled

### `POST /v1/audio/transcriptions`

Expected form fields:

- `file`
- optional `model`
- optional `language`
- optional `prompt`

Flow:

1. Validate auth.
2. Read multipart form data.
3. Save the uploaded audio to a temp file.
4. Run `WhisperModel.transcribe(...)`.
5. Join all segments into a single text string.
6. Delete the temp file.
7. Return the transcript and some metadata.

## Deploy

```bash
modal deploy services/whisper/modal_whisper_app.py
```

## Local Serve on Modal

```bash
modal serve services/whisper/modal_whisper_app.py
```

## How the Client Uses It

The local client lives in:

- `services/whisper/whisper_mcp.py`

That client:

- checks `/health`
- uploads audio to `/v1/audio/transcriptions`
- writes grouped transcription output locally

This keeps the architecture split cleanly:

- Modal handles inference
- the local client handles orchestration and file output

## Why This Approach Was Chosen

- It avoids loading Whisper inside the local MCP process.
- It keeps the HTTP interface simple and stable.
- It lets the model stay warm in GPU memory per container.
- It makes it easy to reuse the same backend for batch transcription.

## Current Notes

- The service is tuned for the current `large-v3` setup.
- The first request after cold start can still take longer.
- The endpoint is backend-only; no UI is involved.
