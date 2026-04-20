# Repo Use Cases

This repository is a working space for Tali voice experiments, not a single packaged application.

Its main value is the end-to-end workflow around:

- extracting and curating Tali audio
- transcribing the curated set
- building reference clips for voice cloning
- running remote TTS backends
- evaluating generated clips against the Tali reference bank

## Primary Use Cases

### 1. Curate a Tali-only audio subset from extracted game files

Use this repo when you need to reduce a larger Mass Effect 2 audio dump into a smaller working set focused on Tali.

Typical tasks:

- keep only files relevant to Tali
- preserve the matching duration manifest
- keep raw extracted files outside the published repo
- prepare the subset for transcription and later TTS work

Relevant files:

- `docs/tali-audio-filtering-workflow.md`
- `me2_game_files_durations.txt`
- `services/voicebox/export_me2_voice_candidates.py`

### 2. Transcribe the curated audio set with a remote Whisper backend

Use this repo when you want a lightweight local client that sends audio to a running Whisper HTTP service instead of loading the ASR model locally.

Typical tasks:

- run batch transcription from the duration manifest
- point the client to a local or Modal-hosted Whisper server
- save structured and readable transcription outputs
- clean up the resulting text for later reference work

Relevant files:

- `services/whisper/whisper_mcp.py`
- `services/whisper/README.md`
- `docs/whisper-modal-backend.md`
- `docs/tali-audio-filtering-workflow.md`

### 3. Build reusable reference clips for voice cloning

Use this repo when you want to turn many short Tali lines into a smaller bank of stronger clone references for TTS backends.

Typical tasks:

- select good source lines from the candidate pool
- concatenate clips with fixed silence between them
- write manifests describing each reference mix
- keep a preferred order for testing clone quality

Relevant files:

- `services/voicebox/build_voicebox_references.py`
- `voices/me2_voice_reference_candidates/references.json`
- `voices/me2_voice_reference_candidates/recommended_order.txt`

### 4. Host a remote TTS backend for profile-based generation

Use this repo when you want to run the Voicebox backend remotely on GPU infrastructure and keep the local machine focused on orchestration and evaluation.

Typical tasks:

- deploy a backend-only Voicebox service on Modal
- keep profile storage and model cache persistent
- protect the service with a token
- test one engine at a time, such as Qwen-based generation

Relevant files:

- `services/voicebox/voicebox_modal_backend.py`
- `docs/voicebox-modal-backend.md`
- `docs/voicebox-backend-other-platforms.md`

### 5. Score generated clips for Tali similarity

Use this repo when you need a repeatable way to rank generated outputs instead of relying only on subjective listening.

Typical tasks:

- compare generated WAV files in `output/` against the local reference bank
- measure technical and acoustic similarity locally with FFmpeg-based features
- optionally add remote speaker embeddings for stronger identity checks
- write CSV, JSON, and Markdown reports for model comparison

Relevant files:

- `services/audio_eval/evaluate_generated_audio.py`
- `services/audio_eval/evaluate_tali_likeness.py`
- `services/audio_eval/modal_speaker_embeddings_app.py`
- `services/audio_eval/modal_pronunciation_whisper_app.py`
- `docs/audio-evaluation.md`

### 6. Compare prompt sets, model sizes, and reference strategies

Use this repo when you want to answer practical questions such as:

- which prompt set produces the most Tali-like output
- whether one model variant beats another on identity or pronunciation
- which reference bundle should be preferred for future runs

This is an evaluation and experimentation repo as much as an infrastructure repo.

Relevant files:

- `services/audio_eval/output_tali_likeness/report.md`
- `voices/me2_voice_reference_candidates/tali_test_dialogues.txt`
- `voices/me2_voice_reference_candidates/tali_test_dialogues_v2.txt`
- `voices/me2_voice_reference_candidates/tali_test_dialogues_v3_romance.txt`

## Secondary Use Cases

- reproduce the Whisper backend outside Modal on another GPU host
- reproduce the Voicebox backend outside Modal on Colab, Kaggle, or a persistent VM
- keep a documented record of the current Tali dataset, reference bank, and evaluation method

## What This Repo Is Not

This repository is currently not optimized for:

- production-grade public TTS serving
- generic speech research unrelated to Tali
- full TTS training from scratch with the current dataset size
- a polished end-user application

The current dataset is useful for curation, prompting, backend testing, and output evaluation, but it is still small for strong standalone TTS fine-tuning.
