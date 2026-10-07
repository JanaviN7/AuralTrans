# PRELIMINARY: does Voice Activity Detection cause the AMI deletions?

> **PRELIMINARY: one meeting, CPU (Windows, no CUDA GPU), not for publication. The final run is the Colab GPU evaluation.**

Date: 2026-10-07 · Meeting: IS1009a (1,920 reference words) · ASR: faster-whisper `small`, int8
Reproduce from cached results: `python eval/run_vad_compare.py IS1009a`

Question: the 2-meeting pilot (WER 21.10%) was dominated by deletions. Is faster-whisper's built-in VAD
cutting out speech? The configuration was **not** changed for the pipeline; VAD off is an experiment only.

| setting | WER % | substitutions | deletions | insertions | ASR segments | ASR-covered seconds |
|---|---|---|---|---|---|---|
| VAD on (shipped) | 23.12 | 76 | 330 | 38 | 135 | 691 |
| VAD off | 23.65 | 92 | 310 | 52 | 156 | 577 |

Finding: turning VAD off **did not help** (+0.52 WER points). It recovered only 20 of 330 deletions and added
14 insertions and 16 substitutions, with no repeated-phrase hallucination loops in either run.
The deleted words are mostly short backchannels and function words (`yeah` 41, `okay` 17, `yes` 15, `i` 15),
which is consistent with Whisper skipping quiet or overlapped speech on a single headset mix, not with VAD clipping.
Decision: VAD stays on.
