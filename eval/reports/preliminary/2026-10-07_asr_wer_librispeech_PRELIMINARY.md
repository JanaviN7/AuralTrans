# PRELIMINARY: ASR WER: librispeech

> **PRELIMINARY: partial or early run, not for publication until the full evaluation is complete.**

Date: 2026-10-07  
Hardware: Windows-10-10.0.26200-SP0; Intel64 Family 6 Model 140 Stepping 1, GenuineIntel; no CUDA GPU

| model | compute | files | WER % | sub | del | ins | ref words | RTF (this run) |
|---|---|---|---|---|---|---|---|---|
| tiny | int8 | 200 | 6.43 | 183 | 17 | 40 | 3733 | 0.157 |
| small | int8 | 200 | 3.16 | 89 | 17 | 12 | 3733 | 0.630 |

- WER uses the Whisper English text normalizer (jiwer, corpus level).
- language forced to 'en'; VAD on; condition_on_previous_text=False.
- RTF counts transcription only and reads 'cached' when results came from the cache.
