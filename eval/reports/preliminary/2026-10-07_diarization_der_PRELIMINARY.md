# PRELIMINARY: Diarization error rate: AMI

> **PRELIMINARY: partial or early run, not for publication until the full evaluation is complete.**

Date: 2026-10-07  
Hardware: Windows-10-10.0.26200-SP0; Intel64 Family 6 Model 140 Stepping 1, GenuineIntel; no CUDA GPU

| meeting | collar s | DER % | missed % | false alarm % | confusion % | JER % | speakers hyp/ref |
|---|---|---|---|---|---|---|---|
| IS1009a | 0.0 | 23.87 | 11.30 | 5.10 | 7.46 | 36.67 | 5/4 |
| IS1009a | 0.25 | 16.02 | 8.61 | 2.68 | 4.73 | 26.07 | 5/4 |
| ES2004a | 0.0 | 19.54 | 11.37 | 3.64 | 4.53 | 24.33 | 5/4 |
| ES2004a | 0.25 | 11.89 | 7.31 | 1.74 | 2.84 | 15.93 | 5/4 |
| ALL (speech-weighted) | 0.0 | 21.40 |  |  |  |  |  |
| ALL (speech-weighted) | 0.25 | 13.66 |  |  |  |  |  |

- Pipeline: pyannote/speaker-diarization-community-1, no speaker-count hint, overlap-aware output scored.
- Reference: AMI-diarization-setup only_words RTTM; scoring region from the UEM files.
- Collar 0 is the strict setting; collar 0.25 forgives +/-0.25 s around each reference boundary (NIST convention).
