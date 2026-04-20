# Tali-Likeness Report

- Focus: identity and pronunciation only.
- Blend: 70% identity and 30% pronunciation.
- Emotion is intentionally excluded in this pass.

## Model Summary

| model | clips | identity | pronunciation | tali-likeness |
| --- | ---: | ---: | ---: | ---: |
| qwen-0.6b | 25 | 83.14 | 99.632 | 88.088 |
| qwen-1.7b | 25 | 81.401 | 99.811 | 86.924 |

## Pairwise Versus

| prompt set | clip | 0.6b identity | 0.6b pron. | 0.6b final | 1.7b identity | 1.7b pron. | 1.7b final | winner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| tali_test_dialogues | 1 | 84.901 | 95.2 | 87.991 | 84.424 | 100.0 | 89.097 | qwen-1.7b |
| tali_test_dialogues | 2 | 78.985 | 95.601 | 83.97 | 60.284 | 95.276 | 70.782 | qwen-0.6b |
| tali_test_dialogues | 3 | 85.054 | 100.0 | 89.538 | 85.369 | 100.0 | 89.758 | qwen-1.7b |
| tali_test_dialogues | 4 | 80.426 | 100.0 | 86.298 | 80.304 | 100.0 | 86.213 | qwen-0.6b |
| tali_test_dialogues | 5 | 82.516 | 100.0 | 87.761 | 83.704 | 100.0 | 88.593 | qwen-1.7b |
| tali_test_dialogues_v2 | 1 | 81.64 | 100.0 | 87.148 | 80.962 | 100.0 | 86.673 | qwen-0.6b |
| tali_test_dialogues_v2 | 2 | 84.392 | 100.0 | 89.074 | 82.612 | 100.0 | 87.828 | qwen-0.6b |
| tali_test_dialogues_v2 | 3 | 81.622 | 100.0 | 87.135 | 81.008 | 100.0 | 86.706 | qwen-0.6b |
| tali_test_dialogues_v2 | 4 | 84.924 | 100.0 | 89.447 | 81.293 | 100.0 | 86.905 | qwen-0.6b |
| tali_test_dialogues_v2 | 5 | 86.457 | 100.0 | 90.52 | 78.846 | 100.0 | 85.192 | qwen-0.6b |
| tali_test_dialogues_v2 | 6 | 81.142 | 100.0 | 86.799 | 82.058 | 100.0 | 87.441 | qwen-1.7b |
| tali_test_dialogues_v2 | 7 | 83.864 | 100.0 | 88.705 | 78.762 | 100.0 | 85.133 | qwen-0.6b |
| tali_test_dialogues_v2 | 8 | 84.893 | 100.0 | 89.425 | 80.406 | 100.0 | 86.284 | qwen-0.6b |
| tali_test_dialogues_v2 | 9 | 81.664 | 100.0 | 87.165 | 83.533 | 100.0 | 88.473 | qwen-1.7b |
| tali_test_dialogues_v2 | 10 | 82.932 | 100.0 | 88.052 | 84.971 | 100.0 | 89.48 | qwen-1.7b |
| tali_test_dialogues_v3_romance | 1 | 84.133 | 100.0 | 88.893 | 81.58 | 100.0 | 87.106 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 2 | 82.577 | 100.0 | 87.804 | 82.003 | 100.0 | 87.402 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 3 | 85.324 | 100.0 | 89.727 | 86.822 | 100.0 | 90.775 | qwen-1.7b |
| tali_test_dialogues_v3_romance | 4 | 80.953 | 100.0 | 86.667 | 79.231 | 100.0 | 85.462 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 5 | 82.477 | 100.0 | 87.734 | 83.6 | 100.0 | 88.52 | qwen-1.7b |
| tali_test_dialogues_v3_romance | 6 | 85.036 | 100.0 | 89.525 | 83.881 | 100.0 | 88.717 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 7 | 84.707 | 100.0 | 89.295 | 84.057 | 100.0 | 88.84 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 8 | 88.038 | 100.0 | 91.627 | 83.675 | 100.0 | 88.572 | qwen-0.6b |
| tali_test_dialogues_v3_romance | 9 | 79.67 | 100.0 | 85.769 | 80.075 | 100.0 | 86.052 | qwen-1.7b |
| tali_test_dialogues_v3_romance | 10 | 80.181 | 100.0 | 86.127 | 81.573 | 100.0 | 87.101 | qwen-1.7b |
