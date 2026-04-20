# Unsloth Studio and Modal

This note explains how `Unsloth Studio` could fit into this repository in the future, and how it can work together with `Modal`.

## Short version

Recommended split:

- use `Unsloth Studio` for local dataset work, fine-tuning experiments, and export
- use `Modal` for remote inference, scalable evaluation, and hosted backends

That keeps training and experimentation flexible, while keeping heavy serving and batch scoring reproducible.

## Why this is future work

Right now this repository is stronger at:

- short-reference voice cloning
- remote backend testing
- identity and pronunciation evaluation

It is not yet centered on full TTS fine-tuning.

`Unsloth Studio` becomes more relevant if the project moves toward:

- TTS fine-tuning
- dataset iteration
- comparing trained checkpoints against the current cloning baseline

## What Unsloth Studio is good for here

In this repo, `Unsloth Studio` is most useful for:

- preparing or transforming TTS datasets
- running local no-code or low-code fine-tuning experiments
- exporting model artifacts after training
- comparing a base model and a tuned model side by side

It is less useful as a direct replacement for the current Modal services.

## What Modal is good for here

In this repo, `Modal` is most useful for:

- hosting GPU-heavy inference backends
- exposing HTTP services for generation and evaluation
- running repeatable batch jobs
- keeping model caches and volumes persistent across runs

That means the natural integration is not "Studio instead of Modal", but "Studio plus Modal".

## Recommended integration pattern

### 1. Local preparation in Unsloth Studio

Use `Unsloth Studio` locally to:

- inspect and clean dataset files
- build or refine TTS training data
- run an initial fine-tuning experiment
- compare base vs tuned behavior

Useful outputs from this stage:

- adapter weights
- merged checkpoints
- exported `safetensors`
- exported `GGUF` when relevant
- dataset manifests and config files

### 2. Artifact handoff

Do not store large trained checkpoints directly in this repository.

Preferred options:

- Hugging Face model repo
- Modal volume
- private object storage
- a local non-versioned models directory

The repo should keep:

- code
- configs
- docs
- small manifests
- evaluation reports

## 3. Remote inference on Modal

Once a model artifact exists, Modal can host it behind a small HTTP service.

That service would follow the same pattern already used in this repo:

- load model from persistent storage
- expose a generation endpoint
- protect the endpoint with a token
- run evaluation against fixed prompt sets

Conceptually, this would be similar to the existing services in:

- `services/voicebox/`
- `services/whisper/`
- `services/audio_eval/`

## 4. Compare against the current baseline

Any future Unsloth-based fine-tuned model should be judged against the current cloning baseline, not only by subjective listening.

The comparison loop should stay the same:

1. generate the same prompt sets
2. keep the same Tali reference bank
3. score identity and pronunciation
4. compare against the existing `qwen-0.6b` and `qwen-1.7b` outputs

## Practical future workflow

A realistic future workflow for this repo would be:

1. curate more clean Tali dialogue
2. normalize transcripts and split train vs validation sets
3. prepare the dataset in `Unsloth Studio`
4. run a first TTS fine-tuning experiment locally
5. export the resulting artifact
6. upload the artifact to a private model store or Modal volume
7. create a Modal inference backend for the tuned model
8. run the existing evaluation pipeline on the same prompt sets
9. compare it against the current cloning baseline

## Suggested repository shape if this happens

If the project moves in this direction later, a clean addition could be:

- `services/unsloth_tts/`: Modal backend for a fine-tuned TTS model
- `docs/unsloth-studio-and-modal.md`: planning and workflow note
- optional training configs under a small config directory

But this should happen only after the dataset is strong enough to justify training.

## Decision rule

Use the current cloning flow if the question is:

- can better references improve Tali similarity
- which existing model size sounds closer to Tali
- can we improve outputs without training

Use `Unsloth Studio` plus `Modal` if the question is:

- has short-reference cloning plateaued
- do we now have enough clean Tali data to justify fine-tuning
- can a tuned model beat the current cloning baseline on the same prompts

## Current recommendation

For this repository today:

- keep `Unsloth Studio` documented as a future training tool
- keep `Modal` as the deployment and evaluation layer
- do not treat `Unsloth Studio` as an immediate replacement for the current voice-cloning workflow
