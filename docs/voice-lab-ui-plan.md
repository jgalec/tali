# Voice Lab UI Plan

This note describes the first implementation plan for a local experimentation UI on top of the current Tali voice workflow.

## Goal

Build a small local UI that helps with the most repetitive parts of testing voice cloning outputs:

- connect to the remote Voicebox backend
- create and inspect profiles
- upload reference samples
- generate new lines
- listen to outputs immediately

The first version is intentionally small.

It is not meant to replace the backend or the evaluation pipeline.

## Why this helps

The current repo already has strong backend and evaluation layers, but the experimentation loop is still script-heavy.

That makes these tasks slower than they need to be:

- switching profiles
- testing reference samples
- generating one line repeatedly
- comparing outputs interactively

The UI is meant to become a lightweight workbench for those steps.

## Chosen stack

Recommended first stack:

- `Gradio` for the local UI
- existing `Voicebox` backend on Modal for generation
- existing local repo structure for references and outputs

Reason:

- `Gradio` is fast to build
- audio inputs and outputs are first-class in the UI
- it works well for local experimentation on Windows

## First version scope

### Included

- backend settings panel
- health check
- list profiles from the Voicebox backend
- create a new profile
- upload a sample and reference text to a profile
- generate a line from an existing profile
- poll generation status until complete
- play the resulting WAV inside the UI
- evaluate the current clip with the existing identity and pronunciation services
- show raw JSON responses for debugging

### Not included yet

- full history browser
- story editing
- integrated evaluation report view
- multi-output batch generation
- direct comparison arena between multiple generated takes
- local waveform or spectrogram inspection

## Service location

The UI is implemented under:

- `services/voice_lab_ui/`

Expected files:

- `services/voice_lab_ui/app.py`
- `services/voice_lab_ui/requirements.txt`
- `services/voice_lab_ui/README.md`

## Python environment

Because this is a local Python UI, it should use its own virtual environment.

Planned environment location:

- `services/voice_lab_ui/.venv/`

This stays local and should not be committed.

## Configuration

The UI should support both:

- direct manual entry in the interface
- optional defaults loaded from root `.env`

Useful keys:

- `VOICEBOX_UI_BASE_URL`
- `VOICEBOX_AUTH_TOKEN`

If those are missing, the UI still works with manual input.

## API assumptions

The first version targets the current upstream Voicebox backend shape reviewed from the upstream repository.

Important endpoints used:

- `GET /health`
- `GET /profiles`
- `POST /profiles`
- `POST /profiles/{profile_id}/samples`
- `POST /generate`
- `GET /generate/{generation_id}/status`
- `GET /audio/{generation_id}`

## Interaction flow

### Profile setup

1. connect to backend
2. load profiles
3. create a profile if needed
4. add one or more reference samples

### Generation

1. choose a profile
2. enter target text
3. select engine and model size
4. submit generation
5. poll until completion
6. play the result in the UI

## Future phases

If the current version is useful, later phases could add:

- side-by-side listening comparison
- prompt-set runner
- automatic save into repo output structure
- support for additional backends beyond Voicebox

## Current recommendation

Build the smallest useful UI first.

That means:

- one Gradio app
- one backend target
- one profile-and-generate loop
- one simple per-clip evaluation loop

Only after that works well should the UI expand into richer comparison features.
