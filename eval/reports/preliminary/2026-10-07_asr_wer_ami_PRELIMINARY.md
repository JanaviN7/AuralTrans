# PRELIMINARY: ASR WER: ami

> **PRELIMINARY: partial or early run, not for publication until the full evaluation is complete.**

Date: 2026-10-07  
Hardware: Windows-10-10.0.26200-SP0; Intel64 Family 6 Model 140 Stepping 1, GenuineIntel; no CUDA GPU

| model | compute | files | WER % | sub | del | ins | ref words | RTF (this run) |
|---|---|---|---|---|---|---|---|---|
| small | int8 | 2 | 21.10 | 167 | 736 | 59 | 4560 | 0.289 |

- WER uses the Whisper English text normalizer (jiwer, corpus level).
- language forced to 'en'; VAD on; condition_on_previous_text=False.
- RTF counts transcription only and reads 'cached' when results came from the cache.
