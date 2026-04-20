# Qwen3-TTS Notes

This note records why `Qwen3-TTS` is relevant to this repository and how it should be treated in the current Tali workflow.

References reviewed:

- `https://github.com/QwenLM/Qwen3-TTS`
- `https://arxiv.org/abs/2601.15621`

## Bottom Line

`Qwen3-TTS` looks useful for this repository.

Not because it forces a new architecture, but because it validates the direction the repo is already taking:

- profile-based voice generation
- short-reference voice cloning
- comparing multiple model sizes
- evaluating identity and pronunciation, not only subjective quality

## Why It Matters Here

This repository is centered on Tali voice experiments.

The practical workflow is:

1. curate Tali audio
2. transcribe and clean it
3. build reference clips
4. generate new lines with a remote TTS backend
5. score the results against the Tali reference bank

`Qwen3-TTS` fits that workflow well because its `Base` models are explicitly designed for voice cloning from a reference audio clip plus transcript.

## Relevant Claims From Qwen3-TTS

The reviewed materials describe a few points that matter directly to this repo:

- `Qwen3-TTS-12Hz-0.6B-Base` and `Qwen3-TTS-12Hz-1.7B-Base` are intended for voice cloning
- the clone path uses `ref_audio` and `ref_text`, which matches this repo's reference-bank approach
- the project exposes both smaller and larger models, which fits the current `qwen-0.6b` vs `qwen-1.7b` comparison style
- the system is multilingual and supports English, which is the relevant target language for Tali
- the project reports strong objective performance for content consistency and competitive speaker similarity

## Why This Is Useful For The Current Repo

The repo already has signs that `Qwen3-TTS` is part of the intended direction:

- the Voicebox backend setup installs `Qwen3-TTS`
- the deployment notes recommend testing one engine at a time
- the evaluation pipeline already compares generated clips by identity and pronunciation

That means the paper is less a reason to pivot and more a reason to continue the current line of work with better confidence.

More concretely, `Qwen3-TTS` is relevant here because:

- this repo is about cloning a specific character voice, not generic TTS
- the current workflow already depends on reference audio plus matching text
- the repo already compares model sizes and generated outputs under the same rubric
- the current evaluation stack is strong enough to tell whether `Qwen3-TTS` helps in practice

## Concrete Use Cases In This Repo

### 1. Clone Tali from short reference material

Use `Qwen3-TTS Base` when the goal is to synthesize new Tali lines from a short reference clip and its transcript.

Why it fits:

- this is the native usage pattern described by `Qwen3-TTS`
- it matches the current reference-bank workflow in this repo
- it allows quick testing without building a full fine-tuning pipeline

### 2. Compare `0.6B` vs `1.7B` models

Use `Qwen3-TTS` when the goal is to measure the tradeoff between:

- speaker identity
- pronunciation
- latency
- cost

This fits the current repo because it already compares variants like `qwen-0.6b` and `qwen-1.7b` on the same prompts and references.

### 3. Test different Tali reference bundles

Use `Qwen3-TTS` when the goal is to find which reference clips produce the most Tali-like output.

Examples:

- `soft_dialogue_a`
- `soft_dialogue_b`
- `normandy_relationship_a`
- `normandy_relationship_b`

This is important because cloning quality in this repo depends as much on reference quality as on model choice.

### 4. Benchmark prompt sets and generated lines

Use `Qwen3-TTS` when the goal is to run the same test prompts across multiple model and reference combinations.

This helps answer questions such as:

- which prompt set preserves pronunciation best
- which model drifts less from Tali's identity
- which reference mix is most stable across many lines

### 5. Run generation through the existing remote backend pattern

Use `Qwen3-TTS` when the goal is to keep generation on GPU infrastructure instead of the local machine.

This matters here because the repo already favors remote backend execution for heavy inference workloads.

### 6. Rank outputs with the existing evaluation stack

Use `Qwen3-TTS` when the goal is not just to generate audio, but to judge whether it is actually better for this project.

The current evaluators already support the key checks this repo cares about:

- acoustic similarity
- speaker identity
- pronunciation
- side-by-side model comparison

## Where It Is Less Relevant

`Qwen3-TTS` is not the main answer for every problem in this repo.

It is less relevant for:

- transcription, where `Whisper` is still the main tool
- full TTS training from scratch with the current small Tali dataset
- infrastructure rewrites that are not required for model evaluation

## What It Changes

What this review changes:

- `Qwen3-TTS Base` should stay on the shortlist of primary engines for Tali cloning tests
- reference quality remains a first-class concern because cloning depends on `ref_audio` and `ref_text`
- model comparison should continue at both smaller and larger sizes when cost and latency matter

What this review does not change:

- it does not prove that `Qwen3-TTS` is automatically the best model for Tali
- it does not remove the need for project-specific listening tests
- it does not solve the limited size of the current curated Tali dataset
- it does not justify rebuilding the repo around a new infrastructure stack right now

## Current Recommendation

Recommended stance for this repository:

- keep `Qwen3-TTS` as a priority engine candidate
- continue using the existing evaluation workflow to judge real outputs, not paper metrics alone
- spend more effort on stronger Tali references and prompt sets before spending large effort on infrastructure changes

## Practical Next Step

When revisiting TTS experiments, the most useful next validation is:

1. run the same prompt set through `Qwen3-TTS` variants
2. keep the same Tali reference inputs
3. score outputs with the existing identity and pronunciation evaluators
4. confirm results with listening tests

That will tell us whether the paper's promise translates into better Tali-like output in this specific repo.
