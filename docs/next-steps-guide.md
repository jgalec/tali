# Next Steps Guide

This note summarizes the most sensible next steps for the repository after the current cloning, evaluation, and UI work.

## Current position

The repository already has:

- a working voice-cloning backend flow
- an evaluation stack for identity and pronunciation
- a local Voice Lab UI for profile setup, generation, and evaluation
- documentation for future fine-tuning paths

That means the next steps should focus on improving reference quality and making comparisons more reliable before moving into heavier training work.

## Priority order

## 1. Improve reference quality

This is the highest-value next step.

Focus on extracting better Tali dialogue, not just more dialogue.

Prioritize clips that are:

- clean
- isolated
- calm or emotionally controlled
- easy to transcribe
- representative of Tali's normal speaking voice

Avoid, when possible:

- combat barks
- overlapping dialogue
- very noisy scenes
- heavily distorted radio-like processing

## 2. Build new reference bundles

Once new clips are extracted, create several new bundles instead of only one larger bundle.

Good bundle categories:

- neutral / conversational
- affectionate / romance
- technical / engineering
- lightly tense but still clean

The goal is to test whether different reference sets improve cloning more than simply changing model size.

## 3. Re-run the same benchmark

Keep the prompt sets stable.

For every new reference bundle:

1. generate the same prompt sets
2. compare `qwen-0.6b` and `qwen-1.7b`
3. score the outputs with the current Tali-likeness evaluator
4. listen manually to the strongest and weakest clips

This keeps the comparison meaningful across iterations.

## 4. Use the Voice Lab UI as the main workbench

The new UI should become the fastest way to iterate.

Recommended usage loop:

1. connect to the backend
2. select or create a profile
3. upload a reference sample
4. generate one or more test lines
5. evaluate the result in the UI
6. keep notes on what changed and why

This is the best place to do quick comparison work before running larger scripted batches.

## 5. Keep `qwen-0.6b` as the current identity baseline

Based on the current evaluation stack, `qwen-0.6b` is still the better baseline when the main question is:

- does it sound like Tali

`qwen-1.7b` remains useful as a contrast point because it can sound more natural or expressive.

So the practical recommendation is:

- use `qwen-0.6b` as the identity baseline
- use `qwen-1.7b` as the naturality comparison model

## 6. Do not jump to fine-tuning yet

Fine-tuning is still future work.

It only becomes worth prioritizing if:

- the cloning approach starts to plateau
- the dataset becomes noticeably larger and cleaner
- transcript quality improves enough to justify training

Until then, better references and better evaluation discipline are likely to produce more value.

## 7. If the repo will become public, do a final hygiene pass

Before making the repository public, do a short final review:

- rotate any exposed tokens
- confirm `.env` is not tracked
- re-check that `voices/` stays ignored
- decide whether `output/` should remain public

This is mostly a release hygiene step, not a blocker for normal local work.

## Suggested short roadmap

### Immediate

- extract a new batch of high-quality Tali clips
- build 3 to 5 new reference bundles
- test them in the Voice Lab UI

### Near term

- rerun the benchmark on the same prompt sets
- keep the best profiles and discard weak bundles
- add side-by-side comparison features to the UI if needed

### Later

- decide whether cloning has plateaued
- only then revisit TTS fine-tuning with tools like Unsloth Studio plus Modal

## Practical decision rule

If the question is:

- how do we make it sound more like Tali right now

Then the answer is:

- better references
- better bundle design
- repeated evaluation

If the question becomes:

- can a trained model beat the current cloning baseline

Then the answer is:

- prepare a larger clean dataset
- design a fine-tuning workflow
- compare it against the existing cloning baseline using the same evaluator
