# Voicebox Backend on Other Platforms

This document explains how to reproduce the backend-only Voicebox deployment on platforms other than Modal, such as Google Colab, Kaggle, or other GPU environments.

The source implementation this is based on is:

- `services/voicebox/voicebox_modal_backend.py`

## Goal

Keep the same backend-only setup:

- no Voicebox UI
- only the FastAPI backend
- remote profile creation and generation
- persistent model cache and backend data
- token protection in front of the backend

## Core Idea

The Modal version works because it wraps the upstream Voicebox backend rather than rewriting it.

The important pattern is:

1. clone or vendor the Voicebox repository
2. install backend dependencies
3. expose `backend.app:create_app()` or equivalent
4. mount persistent storage for profiles/models
5. add auth in front of the routes

That pattern can be reused on any platform that can run Python and a GPU-capable inference stack.

## Minimum Requirements

- Python `3.11`
- `git`
- `ffmpeg`
- `curl`
- build tooling such as `build-essential`
- the Voicebox backend requirements
- extra engines you actually want to support

In the current setup, the backend also installs:

- `chatterbox-tts`
- `hume-tada`
- `Qwen3-TTS`

## Important Constraint

Voicebox is much heavier than the Whisper backend.

You are not just hosting one model:

- backend code
- profile storage
- generation history
- one or more TTS engines
- Hugging Face model downloads

That means notebook services are usable for experiments, but not ideal for stable backend hosting.

## Running on Google Colab

### Good fit

- quick backend experiments
- testing one engine at a time
- checking whether profile upload and generation work

### Limitations

- temporary runtime
- unstable external URL unless tunneled
- storage is ephemeral unless backed by Drive
- not ideal for long-lived profile management

### Practical approach

1. Install system packages in the notebook.
2. Clone Voicebox.
3. Install the backend requirements.
4. Install only the engine you want to test first.
5. Start the backend with `uvicorn`.
6. Expose it with a tunnel.
7. Use a simple auth layer if the tunnel is public.

### Best practice on Colab

Do not enable every engine at once. Start with only `qwen` if that is your immediate goal.

## Running on Kaggle

### Good fit

- isolated experiments
- trying profile creation or one-off generation

### Limitations

- less convenient for public backend access
- session lifecycle is not service-oriented
- persistence is weaker for a backend workflow

### Recommendation

Treat Kaggle as a sandbox for experiments, not as the final Voicebox host.

## Running on a Persistent GPU Server

Examples:

- RunPod
- Vast.ai
- Paperspace
- self-managed VM
- on-prem GPU machine

This is the strongest alternative to Modal for Voicebox.

### Why it fits better

- persistent profile storage
- persistent model cache
- easier HTTPS and reverse proxy setup
- easier debugging
- stable URL for the Voicebox client

## Storage Requirements

Unlike Whisper, Voicebox needs persistence for more than just model cache.

At minimum, keep these directories persistent:

- profile/sample storage
- generation output/history
- model cache

If these are ephemeral, the backend will lose state between restarts.

## Auth Recommendations

The current backend supports multiple auth styles because the client behavior may vary.

On another platform, any of these are reasonable:

- bearer token middleware in FastAPI
- path-prefixed token for clients that only accept a base URL
- reverse proxy auth

If you expose the server publicly, do not skip auth.

## Engine Strategy

A practical lesson from the current setup is that not every engine/profile combination behaves the same.

Recommended approach:

1. deploy backend with only the engine you actually need first
2. test cloned profiles on that engine
3. add more engines later if needed

This reduces build time, image weight, and debugging complexity.

## Suggested Resource Direction

For Voicebox with Qwen-based generation, a GPU-backed environment is strongly preferred.

Notebook environments may work for tests, but a persistent GPU host is a better long-term fit.

General priority:

1. Modal
2. persistent GPU VM
3. Colab for temporary experiments
4. Kaggle for temporary experiments

## Recommended Migration Plan

If you rebuild the backend outside Modal, use this order:

1. Get the upstream Voicebox backend running locally.
2. Enable only one engine.
3. Add persistent data storage.
4. Add persistent model cache.
5. Add auth.
6. Verify `/health`, `/profiles`, and `/generate`.
7. Only then connect the Voicebox desktop client.

## Practical Advice

- For quick experiments, Colab is acceptable.
- For a real reusable backend, use a persistent GPU host.
- If cloning quality matters, spend time on profile/reference quality before spending more time on infrastructure.
