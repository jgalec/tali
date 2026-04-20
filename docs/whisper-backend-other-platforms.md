# Whisper Backend on Other Platforms

This document explains how to reproduce the Whisper backend architecture outside Modal, especially on platforms such as Google Colab, Kaggle, or similar notebook/GPU environments.

## Goal

Keep the same backend idea used on Modal:

- one HTTP service
- one loaded Whisper model per runtime
- a thin local client that only sends requests
- optional auth in front of the endpoint

The source implementation this is based on is:

- `services/whisper/modal_whisper_app.py`

## Core Architecture

The important part is not Modal itself. The important part is the split:

- backend runtime loads `faster-whisper`
- FastAPI exposes `/health` and `/v1/audio/transcriptions`
- the local client uploads files and receives transcripts

That same architecture can be recreated almost anywhere that gives you Python, `ffmpeg`, and enough CPU or GPU memory.

## What You Need on Any Platform

- Python `3.10+`
- `ffmpeg`
- `fastapi`
- `uvicorn`
- `python-multipart`
- `faster-whisper`

If GPU is available:

- CUDA-compatible environment
- drivers/libraries that match `ctranslate2` expectations

## Minimal App Shape

The backend should still look like this:

1. Create a FastAPI app.
2. Load a global `WhisperModel` once.
3. Expose `GET /health`.
4. Expose `POST /v1/audio/transcriptions`.
5. Save incoming audio temporarily.
6. Run transcription.
7. Return text + metadata.

## Running on Google Colab

Colab is useful for testing, not for a stable always-on backend.

### Good fit

- quick experiments
- backend validation
- trying different Whisper models
- one-user temporary testing

### Limitations

- runtime shuts down
- URLs are temporary unless you tunnel them
- storage is not persistent unless you mount Drive
- background server use is fragile

### Practical setup

1. Install dependencies in the notebook.
2. Write or paste the FastAPI backend code.
3. Start `uvicorn` inside the notebook.
4. Expose the port through a tunnel such as `cloudflared` or `ngrok`.
5. Point the local client to the tunneled URL.

### Persistence strategy

- mount Google Drive for model cache if needed
- store the cache directory outside ephemeral `/content`

### When to use Colab

Use Colab when you want to validate the backend shape quickly before moving to a more stable host.

## Running on Kaggle

Kaggle is even more notebook-oriented than Colab.

### Good fit

- experiments
- batch tests
- isolated runs with free GPU access

### Limitations

- less convenient for exposing a public backend
- sessions are not meant to be permanent services
- external networking is more limited depending on the setup

### Practical setup

1. Install the same Python dependencies.
2. Start the FastAPI server.
3. If external access is required, use a supported tunnel approach.
4. Use Kaggle datasets or working directories for intermediate artifacts.

### Recommendation

Kaggle is better for offline experimentation than for a reusable HTTP backend.

## Running on a VM or GPU Server

Examples:

- RunPod
- Vast.ai
- Paperspace
- a self-managed cloud VM
- a local workstation

This is the best non-Modal option if you want a persistent backend.

### Good fit

- stable server URL
- persistent storage
- easier reverse proxy setup
- more control over auth and deployment

### Recommended layout

- FastAPI app
- `uvicorn` or `gunicorn` + `uvicorn` workers
- reverse proxy like Caddy or Nginx
- HTTPS termination
- bearer token auth or proxy auth
- persistent directory for model cache

## Storage Recommendations

Whatever platform you use, separate these concerns:

- temp uploads
- model cache
- logs/output

For Whisper specifically, the most important persistent path is the model cache directory.

## Auth Recommendations

Notebook platforms often expose temporary URLs, but auth is still useful.

Recommended options:

- bearer token in FastAPI middleware
- reverse proxy auth
- tunnel provider auth if supported

Avoid leaving an unrestricted transcription endpoint public.

## Resource Guidance

### CPU-only

- good for `base` or smaller models
- cheaper
- slower

### GPU-backed

- better for `large-v3`
- lower latency
- more useful for repeated requests

Rough practical rule:

- experimentation: Colab/Kaggle GPU is fine
- reusable backend: a persistent GPU server is better

## Suggested Platform Choice

If the goal is just to test:

1. Colab
2. Kaggle

If the goal is to keep a backend running and call it from your local tools:

1. Modal
2. a persistent GPU VM

## Recommended Migration Order

If you ever rebuild this elsewhere, the safest order is:

1. Reuse the same FastAPI route structure.
2. Keep a single global Whisper model.
3. Add persistent model cache.
4. Add auth.
5. Only then point the local client to the new URL.
