# Audio Evaluation

This project includes a local evaluator for generated Tali voice clips.

Source file:

- `services/audio_eval/evaluate_generated_audio.py`
- `services/audio_eval/modal_speaker_embeddings_app.py`
- `services/audio_eval/evaluate_tali_likeness.py`
- `services/audio_eval/modal_pronunciation_whisper_app.py`

Related note:

- `docs/audio-evaluation-process.md`

## What it does

The evaluator compares generated WAV files in `output/` against the local Tali reference bank in `voices/me2_voice_reference_candidates/`.

It builds a heuristic acoustic profile for each clip using FFmpeg-based measurements such as:

- loudness
- clipping risk
- silence ratio
- zero crossing rate
- spectral centroid
- spectral spread
- spectral entropy
- spectral flatness
- spectral flux
- spectral rolloff

It then scores each generated clip against the reference bank and writes summary reports.

## Tali-likeness pass

There is also a second evaluator focused on what matters more for this project:

- voice identity
- pronunciation

Emotion is intentionally excluded from this pass.

Source file:

- `services/audio_eval/evaluate_tali_likeness.py`

This evaluator builds an identity ensemble and adds a pronunciation score based on Whisper transcriptions compared against the expected prompt text.

Current identity stack:

- `speechbrain/spkrec-ecapa-voxceleb`
- `microsoft/wavlm-base-plus-sv`
- `pyannote/embedding` when a Hugging Face token with accepted access is provided

Current blend:

- `70%` identity
- `30%` pronunciation

## Optional speaker embeddings with Modal

The local evaluator can also use a remote speaker-embedding service on Modal.

That service now exposes a small ensemble of identity backends:

- `speechbrain/spkrec-ecapa-voxceleb`
- `microsoft/wavlm-base-plus-sv`
- optional `pyannote/embedding`

### Deploy the Modal service

Source file:

- `services/audio_eval/modal_speaker_embeddings_app.py`

Deploy:

```bash
modal deploy services/audio_eval/modal_speaker_embeddings_app.py
```

Optional auth secret expected by the service:

- Modal secret name: `audio-eval-api-auth`
- env var inside the container: `AUDIO_EVAL_AUTH_TOKEN`

Optional gated model token:

- root `.env` key: `AUDIO_EVAL_PYANNOTE_HF_TOKEN`
- this must be a Hugging Face token from an account that already accepted access to `pyannote/embedding`

### What the service exposes

- `GET /health`
- `POST /v1/audio/embed`
- `POST /v1/audio/compare`

The local evaluator uses `/v1/audio/embed`.

The service stays backward-compatible with the original ECAPA-only response, but it now also returns per-model embeddings and metadata for the full identity ensemble.

## Optional pronunciation service with Modal

The Tali-likeness pass can also use a dedicated Whisper transcription service on Modal.

Source file:

- `services/audio_eval/modal_pronunciation_whisper_app.py`

Deploy:

```bash
modal deploy services/audio_eval/modal_pronunciation_whisper_app.py
```

Optional auth secret expected by the service:

- Modal secret name: `audio-eval-whisper-auth`
- env var inside the container: `AUDIO_EVAL_WHISPER_AUTH_TOKEN`

Suggested `.env` values:

```dotenv
AUDIO_EVAL_ASR_URL=https://your-whisper-url.modal.run
AUDIO_EVAL_ASR_TOKEN=YOUR_TOKEN
```

## Important limitation

This is still a technical similarity check, not a final quality verdict.

It helps rank outputs and spot weak generations, but it does not replace listening tests.

## Usage

From the repository root:

```bash
python services/audio_eval/evaluate_generated_audio.py
```

With remote speaker embeddings:

```bash
python services/audio_eval/evaluate_generated_audio.py \
  --speaker-embed-url https://your-modal-url.modal.run \
  --speaker-embed-token YOUR_TOKEN
```

You can also use environment variables:

```bash
set AUDIO_EVAL_EMBED_URL=https://your-modal-url.modal.run
set AUDIO_EVAL_AUTH_TOKEN=YOUR_TOKEN
python services/audio_eval/evaluate_generated_audio.py
```

Or use a local `.env` file in the repository root:

```dotenv
AUDIO_EVAL_EMBED_URL=https://your-modal-url.modal.run
AUDIO_EVAL_AUTH_TOKEN=YOUR_TOKEN
```

Then run:

```bash
python services/audio_eval/evaluate_generated_audio.py
```

The evaluator reads `C:\Users\juan\Desktop\tali\.env` automatically if it exists.

Tali-likeness pass:

```bash
python services/audio_eval/evaluate_tali_likeness.py
```

With optional pyannote access in `.env`:

```dotenv
AUDIO_EVAL_PYANNOTE_HF_TOKEN=YOUR_HF_TOKEN
```

Optional arguments:

```bash
python services/audio_eval/evaluate_generated_audio.py \
  --reference-dir voices/me2_voice_reference_candidates \
  --generated-root output \
  --output-dir services/audio_eval/output
```

Quick check on only a few files:

```bash
python services/audio_eval/evaluate_generated_audio.py --limit 6
```

## Output files

The script writes reports to `services/audio_eval/output/`:

- `generated_clip_scores.csv`: per-clip scores and measurements
- `model_summary.csv`: average scores per model
- `prompt_summary.csv`: average scores per model and prompt set
- `reference_profiles.csv`: measured reference-bank profiles
- `summary.json`: structured summary
- `report.md`: readable report with rankings

## How to read the scores

- `reference_similarity_score`: how close the generated clip is to the overall Tali reference profile
- `nearest_reference_score`: how close it is to the closest single reference clip
- `technical_score`: loudness, silence, and clipping health
- `overall_score`: weighted combination of similarity and technical health

If the speaker-embedding service is enabled, the reports also include:

- `acoustic_reference_similarity_score`: FFmpeg-based acoustic similarity only
- `speaker_reference_similarity_score`: speaker-embedding similarity only
- `speaker_nearest_reference_score`: best matching single reference by speaker embedding

The Tali-likeness pass writes:

- `clip_scores.csv`: per-clip identity, pronunciation, and final Tali-likeness score
- `versus.csv`: direct `qwen-0.6b` vs `qwen-1.7b` comparison per prompt line
- `model_summary.csv`: average score per model under the new rubric

The identity-related columns are now broken down by backend so you can inspect:

- ensemble identity
- ECAPA identity
- WavLM identity
- pyannote identity when available

Higher is better.

## Current design choice

The local evaluator does not require extra Python packages.

It uses FFmpeg plus the Python standard library so it can run in the current repo without setting up a separate environment first.

The stronger speaker-identity path is offloaded to Modal, where `speechbrain`, `transformers`, and optional `pyannote.audio` can run without affecting the lightweight local workflow.
