# Voice Lab UI

Small local Gradio workbench for the Tali voice workflow.

## What it does

- connects to a Voicebox-compatible backend
- checks backend health
- lists and creates profiles
- uploads profile samples
- generates speech from an existing profile
- plays the resulting audio locally in the browser
- evaluates the current clip against the Tali reference bank

## Setup

Create and use the local virtual environment in this folder, then install requirements.

## Run

```bash
python app.py
```

The app reads optional defaults from the repository root `.env` if present.
