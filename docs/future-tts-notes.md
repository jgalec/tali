# Future TTS Notes

Reference for later:

- Unsloth TTS fine-tuning guide: `https://unsloth.ai/docs/basics/text-to-speech-tts-fine-tuning`
- `docs/qwen3-tts-notes.md`: current notes on why `Qwen3-TTS` is relevant here
- `docs/unsloth-studio-and-modal.md`: future note on how local fine-tuning work could integrate with Modal

Current status:

- The current notebook in `notebooks/notebookac74553ff1.ipynb` is for Whisper STT fine-tuning, not voice cloning or TTS.
- The current Tali dataset is useful as a curated base, but it is still too small for strong TTS fine-tuning.
- Current filtered set: `461` audio clips, about `9.69` minutes total.

Recommended next step when revisiting this:

1. Gather more clean Tali audio.
2. Prefer longer dialogue clips over short combat barks.
3. Keep transcripts normalized and aligned.
4. Switch to a real TTS notebook/model instead of Whisper.
