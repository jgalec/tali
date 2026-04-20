# tali

Tali voice-cloning and transcription workspace.

This repository tracks the project code, documentation, manifests, and generated evaluation outputs used to explore a Tali'Zorah voice pipeline.

## What is included

- `docs/`: workflow notes and deployment writeups for Whisper and Voicebox
- `services/voicebox/`: Modal wrapper and reference-building scripts for Voicebox
- `services/whisper/`: Whisper MCP client, Modal backend, and transcription outputs
- `output/`: generated cloned voice samples kept for comparison
- `scripts/`: small helper scripts for asset discovery
- `me2_game_files_durations.txt`: duration manifest for the curated Tali subset
- `tali-pcc-results.txt`: discovered PCC file list from a local Mass Effect 2 install

## What is not included

- `voices/` is intentionally ignored in `.gitignore`
- extracted game assets are not published in this repository
- local virtual environments, caches, and secrets are ignored

## Repository layout

```text
tali/
|- docs/
|- notebooks/
|- output/
|- scripts/
|- services/
|  |- voicebox/
|  \- whisper/
|- me2_game_files_durations.txt
\- tali-pcc-results.txt
```

## Main workflows

### Whisper transcription

The Whisper side is split into two parts:

1. `services/whisper/modal_whisper_app.py` exposes a small FastAPI transcription service on Modal.
2. `services/whisper/whisper_mcp.py` acts as a thin local MCP client that sends audio to that service and writes grouped outputs locally.

See `services/whisper/README.md` and `docs/whisper-modal-backend.md` for details.

### Voicebox backend and references

The Voicebox side includes:

- `services/voicebox/voicebox_modal_backend.py` for the Modal backend wrapper
- `services/voicebox/export_me2_voice_candidates.py` to export candidate clips
- `services/voicebox/build_voicebox_references.py` to build concatenated reference samples

See `docs/voicebox-modal-backend.md` for the deployment notes.

## Notes

- This repo stores generated research outputs, so some committed files are derived artifacts by design.
- Audio extracted from the game is kept out of version control.
- The notebook in `notebooks/` is an experiment artifact and not the main entry point for the project.
