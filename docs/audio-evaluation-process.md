# Audio Evaluation Process

This note documents the process used to build and validate the Tali audio evaluation workflow in this repository.

## Goal

The original goal was not just to score technical audio quality, but to answer a more specific question:

- which generated clips sound most like Tali
- which model wins in a direct clip-versus-clip comparison

Emotion was discussed, but intentionally left out of the final scoring pass for now.

## Phase 1: local acoustic baseline

The first evaluator was built in `services/audio_eval/evaluate_generated_audio.py`.

This baseline:

- compares generated clips in `output/` against reference clips in `voices/me2_voice_reference_candidates/`
- extracts acoustic and technical measurements with `ffmpeg`
- writes per-clip and per-model reports to `services/audio_eval/output/`

The first version measured things like:

- loudness and RMS
- clipping ratio
- silence ratio
- zero crossing rate
- spectral centroid, spread, entropy, flatness, flux, and rolloff

This was useful, but it weighted acoustic similarity more than the user perception of "sounds like Tali".

## Phase 2: speaker identity with Modal

To improve identity scoring, a speaker-embedding service was added in Modal:

- `services/audio_eval/modal_speaker_embeddings_app.py`

The first deployed version used only:

- `speechbrain/spkrec-ecapa-voxceleb`

This added a much better voice-identity signal than the pure acoustic baseline.

## Phase 3: Tali-likeness pass

After listening feedback, the scoring was changed to reflect the real evaluation target:

- identity first
- pronunciation second
- no emotion yet

That led to a second evaluator:

- `services/audio_eval/evaluate_tali_likeness.py`

This pass combines:

- speaker identity score
- Whisper-based pronunciation score

Current blend:

- `70%` identity
- `30%` pronunciation

## Phase 4: pronunciation service with Whisper

To score pronunciation consistently, a dedicated Whisper service was deployed on Modal:

- `services/audio_eval/modal_pronunciation_whisper_app.py`

This service transcribes each generated clip and compares the transcript with the expected prompt line.

The pronunciation score is derived from:

- word error rate
- character error rate

This is still an approximation of pronunciation, but it is more useful than a purely manual comparison at scale.

## Phase 5: identity ensemble from Hugging Face models

To avoid relying on a single speaker model, the identity backend was expanded into an ensemble.

The current stack in `services/audio_eval/modal_speaker_embeddings_app.py` is:

- `speechbrain/spkrec-ecapa-voxceleb`
- `microsoft/wavlm-base-plus-sv`
- `pyannote/embedding`

The local Tali-likeness evaluator now averages the identity signal from all enabled backends and then combines it with the pronunciation score.

## pyannote integration note

`pyannote/embedding` is gated on Hugging Face, so it required:

- accepted access to the model on Hugging Face
- a local Hugging Face token in `.env`

There was also a compatibility issue when loading `pyannote` under PyTorch 2.6 because `torch.load` now defaults to `weights_only=True`.

That was resolved in the Modal service by setting:

- `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1`

After that fix, the full identity ensemble worked.

## Current execution flow

The current evaluation process is:

1. run the speaker service on Modal
2. run the Whisper pronunciation service on Modal
3. keep credentials locally in `.env`
4. run `python services/audio_eval/evaluate_tali_likeness.py`
5. inspect the reports in `services/audio_eval/output_tali_likeness/`

## Current outputs

The main outputs are:

- `services/audio_eval/output_tali_likeness/clip_scores.csv`
- `services/audio_eval/output_tali_likeness/versus.csv`
- `services/audio_eval/output_tali_likeness/model_summary.csv`
- `services/audio_eval/output_tali_likeness/report.md`
- `services/audio_eval/output_tali_likeness/summary.json`

## Interpretation

The important outcome of this process is that the ranking now reflects the intended criterion better than the original acoustic-only pass.

In the current full ensemble setup:

- `qwen-0.6b` remains slightly ahead overall as the better Tali-like base
- `qwen-1.7b` remains competitive and often sounds more natural, but does not consistently win on identity

## Practical limitation

This pipeline is still an assistant, not an oracle.

It helps rank clips and surface likely winners, but the final judgment still depends on listening, especially when subtle pronunciation or characterization differences matter more than raw speaker similarity.
