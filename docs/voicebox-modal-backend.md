# Voicebox Backend on Modal

This document explains how the Voicebox backend was built and deployed on Modal.

## Goal

- Run Voicebox as a backend-only service on Modal.
- Keep the web UI out of the deployment.
- Expose the original Voicebox FastAPI backend remotely.
- Persist downloaded model files and generated backend data.
- Protect the service with an auth token.

## What was reviewed

- Voicebox is already split into a FastAPI backend and a separate UI.
- The backend can run standalone with `python -m backend.main`.
- The backend is API-first and exposes routes like `/health`, `/profiles`, `/generate`, `/models`, and `/docs`.
- The upstream Dockerfile runs only the backend with `uvicorn backend.main:app`.

That makes it a reasonable candidate for a Modal deployment.

## Source File

- `services/voicebox/voicebox_modal_backend.py`

## Important constraints

- Voicebox is much heavier than the Whisper MVP.
- Its backend requirements include multiple TTS engines, audio tooling, SQLite, and Hugging Face downloads.
- The first request may be slow because models are downloaded on demand.
- Persistent storage is needed for both generated data and model cache.

## Main Design

What it does:

- builds a Debian-based Modal image with the system packages Voicebox expects
- clones the upstream `jamiepine/voicebox` repository into the image
- installs the backend dependencies plus the extra upstream installs used in the Voicebox Dockerfile
- mounts one Modal volume for backend data and one for model cache
- imports the upstream FastAPI backend and serves it through `@modal.asgi_app()`
- adds bearer-token protection in front of the backend routes

Instead of rewriting Voicebox, the wrapper loads the upstream backend directly.

## Runtime layout

- data volume: `/voicebox-data`
- model cache volume: `/voicebox-models`
- upstream repo in image: `/opt/voicebox`

The wrapper sets:

- `VOICEBOX_MODELS_DIR`
- `HF_HOME`
- `HF_HUB_CACHE`

and also forces the Voicebox backend data directory to `/voicebox-data`.

## Image Setup

The Modal image does the following:

- starts from `debian_slim` with Python `3.11`
- installs system tools:
  - `git`
  - `ffmpeg`
  - `curl`
  - `build-essential`
- clones `https://github.com/jamiepine/voicebox.git` into `/opt/voicebox`
- installs `backend/requirements.txt`
- installs extra engine packages used by the Voicebox backend:
  - `chatterbox-tts`
  - `hume-tada`
  - `Qwen3-TTS`

The goal was to stay close to the upstream backend expectations instead of maintaining a fork.

## Current resource choice

- GPU: `T4`
- CPU: `4`
- Memory: `32768` MiB
- Request timeout: `1800` seconds

This is a safe starting point for a first Modal deployment.

## Persistent Storage

Two Modal volumes are used:

- `voicebox-data`
- `voicebox-models`

Why both are needed:

- `voicebox-data` stores backend-managed artifacts such as profiles, samples, and generation metadata
- `voicebox-models` stores downloaded model weights and Hugging Face cache

Without these volumes, cold starts would redownload models and lose generated backend state.

## Authentication

The backend is protected by a token layer added in the Modal wrapper.

Implementation:

- Modal secret name: `voicebox-api-auth`
- env var inside the container: `VOICEBOX_AUTH_TOKEN`

Accepted auth styles:

- bearer header
- token in URL path prefix
- token in query string for manual requests

This was added because the Voicebox client and manual tooling do not always pass auth the same way.

## Deploy

```bash
modal deploy services/voicebox/voicebox_modal_backend.py
```

Auth secret used by the wrapper:

- Modal secret: `voicebox-api-auth`
- env var inside the container: `VOICEBOX_AUTH_TOKEN`

Current deployed URL:

- `https://rsch--voicebox-backend-fastapi-app.modal.run`

Authorized request example:

```bash
curl https://rsch--voicebox-backend-fastapi-app.modal.run/health \
  -H "Authorization: Bearer $VOICEBOX_AUTH_TOKEN"
```

If a client supports custom headers, use the bearer token header.

If a client only supports a plain server URL, the backend also accepts a token in the path prefix:

```text
https://rsch--voicebox-backend-fastapi-app.modal.run/token/YOUR_TOKEN
```

This is the preferred option for clients that later append routes like `/health` or `/generate` to the base URL.

The backend also accepts a token as a query parameter for direct manual requests:

```text
https://rsch--voicebox-backend-fastapi-app.modal.run?token=YOUR_TOKEN
```

## Local serve on Modal

```bash
modal serve services/voicebox/voicebox_modal_backend.py
```

## Expected API shape

Once deployed, the endpoint should expose the upstream Voicebox backend routes, including:

- `/`
- `/health`
- `/docs`
- `/profiles`
- `/generate`
- `/models`

Current health check result:

- `GET /health` returns a healthy backend on `CUDA (Tesla T4)` when the bearer token is provided

## Why Backend-Only Was Chosen

- The user only needed the Voicebox server, not the web UI.
- The backend is the piece that creates profiles and runs generation.
- Skipping the UI reduces deployment weight and maintenance surface.

## Current Notes

- Generation is asynchronous, so audio fetches can briefly return `404` before the file exists.
- The first request for a model or engine may be noticeably slower.
- Some engines behave differently with cloned profiles, so the backend setup matters less than the engine/profile combination chosen in the client.

## Likely next improvements

1. Limit the exposed engine set if only Qwen3-TTS is needed.
2. Add a small smoke-test script for `/health` and `/generate`.
3. Tune cold-start behavior if generation latency is too high.
