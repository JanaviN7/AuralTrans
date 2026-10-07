# Evaluation

Every number in the project README must come from these scripts. Data lives outside the repo in
`EVAL_DATA_DIR` (default `~/auraltrans-data`, set it in `backend/.env`). No audio is committed.

## Data (nothing downloads without `--yes`)
    python eval/datasets/fetch.py          # prints exact sizes, downloads nothing
    python eval/datasets/fetch.py --yes    # downloads

| Set | What | Download |
|---|---|---|
| AMI test subset | 10 of the 16 official test meetings (Mix-Headset audio), word annotations, RTTM, UEM | 601.7 MB (incl. a 22.9 MB annotations zip deleted after extraction) |
| LibriSpeech test-clean | 200 utterances: 50 each from 4 parquet row groups (0, 9, 18, 25), 9 speakers | 47.5 MB |

Meetings: IS1009a-c, ES2004a-c, TS3003a-b, EN2002a-b (about 301 min of audio).

## Run order (from `backend/`, with `--extra speech --extra eval`)
1. `eval/run_asr.py --dataset librispeech --models tiny small` : WER per model size
2. `eval/run_asr.py --dataset ami --models small` : WER on meetings (caches ASR output)
3. `eval/run_diarization.py` : DER/JER, collar 0 and 0.25 (caches diarization)
4. `eval/run_cpwer.py --model small` : alignment ablation (needs 2 and 3)
5. `eval/run_speed.py --files ...` : RTF per stage, peak VRAM on CUDA

Reports are written to `eval/reports/` as dated markdown + CSV. Any run that is not the full
10-meeting set on CUDA (and, for cpWER, with meeteval) is named `*_PRELIMINARY` and carries a banner;
`--final` refuses to write a final report otherwise.

- `eval/reports/preliminary/` holds the committed Windows CPU pilot reports (2 AMI meetings,
  200 LibriSpeech utterances, one VAD experiment). The root `eval/reports/` is for **final** reports only
  (from the Colab run). Local `*_PRELIMINARY` outputs in the root are git-ignored; the cpWER pilot used the
  non-meeteval fallback and is deliberately not committed.
- `eval/run_vad_compare.py [MEETING]` compares VAD on/off from the cached ASR results.

## Final run (Colab GPU)
`python eval/colab/make_bundle.py` builds a commit-pinned zip; `eval/colab/auraltrans_ami_eval.ipynb`
runs the identical scripts on a GPU with meeteval and writes the final reports plus `run_manifest.json`.
See the main README, "Reproduce the evaluation".

## Notes
- `meeteval` has no Windows wheel, so cpWER falls back to an equivalent assignment-based
  implementation here. The fallback is cross-checked against meeteval in tests on Linux. Publish
  only cpWER numbers produced with meeteval (Colab/CI).
- A 0.25 s collar means +/-0.25 s around each reference boundary (pyannote's own parameter is the
  total width, so the code passes 0.5).
- RTF and VRAM targets in the blueprint need a GPU run; CPU runs are reported as such.
- The AMI words-XML parser is unit-tested on a hand-made sample and was validated against the real
  annotation files after download.
