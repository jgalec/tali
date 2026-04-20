# Tali Audio Filtering Workflow

This document summarizes the process used to keep only the relevant Tali audio files and leave the project in a clean, consistent state.

## Goal

- Keep only audio files related to Tali.
- Remove unwanted audio files from the working set.
- Maintain a duration manifest that matches the final files.
- Generate clean, reviewed transcriptions for that subset.

## Workflow Followed

### 1. Start from the full set

- `me2_game_files/` was used as the source folder.
- The total number of audio files was checked before cleanup.

### 2. Filter using the short manifest

- A reduced manifest containing only a short clip selection was used.
- Audio files not listed in that manifest were deleted.
- At this stage, `.pcc` files were preserved and only audio files were removed.

Intermediate result:

- The set went from `1740` audio files down to `536` audio files.
- The `.pcc` files were kept intact.

### 3. Filter by filename containing `tali`

- A second filter was then applied to the remaining `536` audio files.
- Only files whose name contained `tali` or `Tali` were kept.
- Audio files without that text in the filename were removed, even if they lived inside Tali-related folders.

Final file result:

- `461` audio files in `me2_game_files/`
- all of them contain `tali` in the filename
- `9` `.pcc` files preserved

## Transcription of the Filtered Set

### 4. Run the full transcription

- The filtered audio set was transcribed using the Whisper service deployed on Modal.
- A full output was generated first, then a derived `tali_only` output was created.

Relevant files:

- full raw output: `services/whisper/output_modal_final/transcriptions.jsonl`
- full raw output: `services/whisper/output_modal_final/transcriptions.txt`
- Tali-only filtered output: `services/whisper/output_modal_final/transcriptions_tali_only.jsonl`
- Tali-only filtered output: `services/whisper/output_modal_final/transcriptions_tali_only.txt`

### 5. Apply light text cleanup

- A conservative post-processing step was applied to the `tali_only` output.
- Frequent ASR mistakes were corrected without retranscribing the whole corpus.
- A manual review list was also generated for doubtful cases.

Examples of applied corrections:

- `Disabling the MEX systems.` -> `Disabling the Mech systems.`
- `Combat thrown away.` -> `Combat drone away.`
- `Combat throne ready.` -> `Combat drone ready.`
- `Possessed Throne!` -> `Suppressing fire!`
- `I light a fire.` -> `Allied fire!`

Final clean output:

- `services/whisper/output_modal_final/transcriptions_tali_only_clean.jsonl`
- `services/whisper/output_modal_final/transcriptions_tali_only_clean.txt`

## Final Duration Manifest

### 6. Update the root manifest

- The old full duration file was used as the base.
- It was rewritten so it only kept entries that still exist in `me2_game_files/`.
- It was then renamed to English to keep the project consistent.

Final file:

- `me2_game_files_durations.txt`

Old files removed:

- `me2_game_files_duraciones_1s_a_2s_sin_1337ms.txt`
- `me2_game_files_duraciones_1s_a_2s.txt`
- `me2_game_files_duraciones_menos_de_2s.txt`
- `me2_game_files_duraciones.txt`

## Expected Final State

At the end of the process, the project should look like this:

- `me2_game_files/` contains only `461` Tali audio files
- the `.pcc` files are still present
- `me2_game_files_durations.txt` matches that exact set
- `services/whisper/output_modal_final/transcriptions_tali_only_clean.txt` is the final clean text output
- `services/whisper/output_modal_final/transcriptions_tali_only_clean.jsonl` is the final structured output

## Practical Rule for Repeating the Process

If this workflow is repeated on another batch, the recommended order is:

1. Filter files using the desired rule.
2. Keep the duration manifest updated.
3. Transcribe the resulting set.
4. Filter the text output if needed.
5. Apply light ASR cleanup.
6. Keep a separate `clean` output apart from the raw output.
