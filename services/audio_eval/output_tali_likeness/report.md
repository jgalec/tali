# Tali-Likeness Report

- Focus: identity and pronunciation only.
- Blend: 70% identity and 30% pronunciation.
- Identity stack: SpeechBrain ECAPA, Microsoft WavLM speaker verification, and optional pyannote embeddings.
- Emotion is intentionally excluded in this pass.

## Model Summary

| model | clips | ensemble identity | ecapa | wavlm | pyannote | pronunciation | tali-likeness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| qwen-0.6b | 25 | 87.098 | 83.14 | 97.278 | 80.875 | 99.632 | 90.858 |
| qwen-1.7b | 25 | 86.227 | 81.401 | 96.323 | 80.957 | 99.811 | 90.302 |

## Pairwise Versus

| prompt set | clip | 0.6b identity | 0.6b final | 1.7b identity | 1.7b final | winner |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| tali_test_dialogues | 1 | 88.574 | 90.562 | 87.843 | 91.49 | qwen-1.7b |
| tali_test_dialogues | 2 | 84.377 | 87.744 | 72.135 | 79.077 | qwen-0.6b |
| tali_test_dialogues | 3 | 87.994 | 91.596 | 88.828 | 92.18 | qwen-1.7b |
| tali_test_dialogues | 4 | 86.289 | 90.402 | 86.386 | 90.47 | qwen-1.7b |
| tali_test_dialogues | 5 | 87.45 | 91.215 | 87.722 | 91.405 | qwen-1.7b |
| tali_test_dialogues_v2 | 1 | 85.993 | 90.195 | 86.174 | 90.322 | qwen-1.7b |
| tali_test_dialogues_v2 | 2 | 87.997 | 91.598 | 86.794 | 90.756 | qwen-0.6b |
| tali_test_dialogues_v2 | 3 | 85.812 | 90.068 | 86.828 | 90.78 | qwen-1.7b |
| tali_test_dialogues_v2 | 4 | 87.705 | 91.393 | 85.488 | 89.842 | qwen-0.6b |
| tali_test_dialogues_v2 | 5 | 89.226 | 92.458 | 84.898 | 89.429 | qwen-0.6b |
| tali_test_dialogues_v2 | 6 | 86.53 | 90.571 | 87.205 | 91.043 | qwen-1.7b |
| tali_test_dialogues_v2 | 7 | 87.866 | 91.506 | 85.566 | 89.896 | qwen-0.6b |
| tali_test_dialogues_v2 | 8 | 87.476 | 91.233 | 86.099 | 90.269 | qwen-0.6b |
| tali_test_dialogues_v2 | 9 | 85.626 | 89.938 | 87.934 | 91.554 | qwen-1.7b |
| tali_test_dialogues_v2 | 10 | 87.541 | 91.279 | 87.523 | 91.266 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 1 | 87.744 | 91.421 | 86.602 | 90.621 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 2 | 87.054 | 90.938 | 85.794 | 90.056 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 3 | 86.445 | 90.511 | 88.787 | 92.151 | qwen-1.7b |
| tali_test_dialogues_v3_romance | 4 | 86.632 | 90.642 | 84.532 | 89.172 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 5 | 87.099 | 90.969 | 87.848 | 91.494 | qwen-1.7b |
| tali_test_dialogues_v3_romance | 6 | 88.411 | 91.888 | 89.171 | 92.42 | qwen-1.7b |
| tali_test_dialogues_v3_romance | 7 | 88.439 | 91.907 | 88.407 | 91.885 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 8 | 89.572 | 92.7 | 87.211 | 91.048 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 9 | 85.27 | 89.689 | 83.874 | 88.712 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 10 | 84.329 | 89.03 | 86.03 | 90.221 | qwen-1.7b |
