# To Do

## Next steps for Tali voice work

1. Keep focusing on voice cloning, not fine-tuning yet.
2. Extract more Tali audio only when it is high quality and useful.
3. Prioritize calm, clean, well-isolated dialogue over noisy or overlapping lines.
4. Gather lines across a few styles:
   - neutral
   - affectionate / romance
   - technical / engineering
   - light tension
5. Avoid low-value clips when possible:
   - combat shouts
   - heavily filtered radio-like lines
   - overlapping dialogue
   - very noisy scenes
6. Build 3-5 new reference bundles from the new curated clips.
7. Test the new bundles on the same prompt sets used so far.
8. Use `qwen-0.6b` as the main identity baseline.
9. Use `qwen-1.7b` as a comparison point for naturality.
10. Re-run the evaluation pipeline and compare against the current baseline.

## Decision rule

- If the goal is "sounds more like Tali", prioritize better references over more raw audio.
- If the cloning approach starts to plateau and the dataset becomes much larger and cleaner, revisit fine-tuning later.
