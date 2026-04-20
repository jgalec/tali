# Voice Cloning vs. Fine-Tuning

This note explains the difference between two related but different goals in this repository:

- cloning Tali from a small reference clip
- fine-tuning a model on a larger Tali-specific dataset

They are not the same workflow, and they do not have the same data requirements.

## Short version

### Voice cloning

Use voice cloning when the model already knows how to speak and you want it to imitate Tali from one or a few reference clips.

Typical inputs:

- `ref_audio`
- matching `ref_text`
- a new line to generate

Best fit in this repo:

- fast iteration
- prompt and reference comparison
- testing `qwen-0.6b` vs `qwen-1.7b`
- ranking outputs by identity and pronunciation

### Fine-tuning

Use fine-tuning when you want to adapt the model itself so it learns Tali's voice characteristics more deeply from many examples.

Typical inputs:

- a larger clean dataset
- normalized transcripts
- training configuration
- compute for repeated training runs

Best fit in this repo:

- future work, not the current main path

## Why the distinction matters here

This repository currently has a curated Tali dataset, reference bundles, remote inference backends, and an evaluation stack.

That makes it strong for voice cloning experiments right now.

It does not yet make the repo ideal for serious TTS fine-tuning because:

- the dataset is still small
- the source audio comes from in-game dialogue with character-specific filtering
- transcript alignment and normalization still matter a lot
- training and evaluation loops are heavier than simple clone inference

## Voice cloning in this repo

Voice cloning is the current practical workflow.

The pattern is:

1. curate Tali clips
2. build a reference bank
3. generate new lines from short references
4. compare outputs across models and prompt sets
5. score identity and pronunciation

This is the path used by the current Qwen-style experiments.

Relevant repo pieces:

- `voices/me2_voice_reference_candidates/`
- `services/voicebox/build_voicebox_references.py`
- `services/audio_eval/evaluate_generated_audio.py`
- `services/audio_eval/evaluate_tali_likeness.py`

## Fine-tuning in this repo

Fine-tuning is a valid future direction, but it should be treated as a separate phase.

Before it becomes worthwhile, the repo would benefit from:

- more clean Tali audio
- better transcript normalization
- stronger train/validation splits
- a TTS-specific training notebook or training pipeline
- clear evaluation against the current cloning baseline

At the moment, the repo has a Whisper fine-tuning notebook for STT, not a finished TTS fine-tuning workflow.

Relevant repo pieces:

- `notebooks/notebookac74553ff1.ipynb`
- `docs/future-tts-notes.md`

## Tradeoffs

### Voice cloning advantages

- works with much less data
- easier to iterate on references
- cheaper to test remotely
- easier to compare model sizes and prompts

### Voice cloning limitations

- heavily dependent on reference quality
- can drift in pronunciation or identity across prompts
- does not permanently adapt the model to Tali

### Fine-tuning advantages

- can produce a more consistent character voice if the dataset is strong enough
- can reduce dependence on a tiny reference bundle
- may improve stability across many generations

### Fine-tuning limitations

- needs much more clean data
- requires real training infrastructure
- can overfit badly with a small or noisy dataset
- takes more time to evaluate properly

## Current recommendation

For this repository today:

- treat voice cloning as the primary path
- treat fine-tuning as future work
- use the current evaluation pipeline to decide whether better references and better clone models are enough before investing in training

## Practical decision rule

Use voice cloning if the question is:

- which reference bundle sounds most like Tali
- whether `0.6B` or `1.7B` is better
- which generated take wins for identity and pronunciation

Use fine-tuning if the question is:

- whether the current clone approach has plateaued
- whether the dataset is large and clean enough to justify training
- whether a custom Tali voice model would beat the current cloning baseline over many prompts
