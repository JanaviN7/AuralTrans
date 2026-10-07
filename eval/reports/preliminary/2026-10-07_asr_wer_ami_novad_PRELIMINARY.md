# PRELIMINARY: ASR WER: ami (VAD OFF experiment)

> **PRELIMINARY: partial or early run, not for publication until the full evaluation is complete.**

Date: 2026-10-07  
Hardware: Windows-10-10.0.26200-SP0; Intel64 Family 6 Model 140 Stepping 1, GenuineIntel; no CUDA GPU

| model | compute | files | WER % | sub | del | ins | ref words | RTF (this run) |
|---|---|---|---|---|---|---|---|---|
| small | int8 | 1 | 23.65 | 92 | 310 | 52 | 1920 | 0.401 |

- WER uses the Whisper English text normalizer (jiwer, corpus level).
- language forced to 'en'; VAD OFF (experiment); condition_on_previous_text=False.
- RTF counts transcription only and reads 'cached' when results came from the cache.
