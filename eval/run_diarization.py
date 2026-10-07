"""DER and JER on the AMI meetings, with and without a 0.25 s collar.

    python eval/run_diarization.py --limit 2

Hypotheses are cached under EVAL_DATA_DIR/cache/diarization for run_cpwer.py.
Scoring region comes from the AMI UEM files. Overlapped speech is scored.
"""

import argparse
from pathlib import Path

from auraltrans.config import settings
from auraltrans.evaluation import ami
from auraltrans.evaluation.metrics import DerResult, der
from auraltrans.evaluation.report import cache_path, load_cached, save_cached, write_report
from auraltrans.speech.audio import prepare_audio
from auraltrans.speech.diarize import DiarizationResult, PyannoteDiarizer

REPORTS = Path(__file__).parent / "reports"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    data_dir = settings.eval_data_dir

    diarizer: PyannoteDiarizer | None = None
    rows: list[list[object]] = []
    pooled: dict[float, list[tuple[DerResult, float]]] = {0.0: [], 0.25: []}
    for m in ami.TEST_SUBSET[: args.limit]:
        cp = cache_path(data_dir, "diarization", "community-1", m)
        hyp = load_cached(cp, DiarizationResult)
        if hyp is None:
            diarizer = diarizer or PyannoteDiarizer(settings.hf_token, args.device)
            wav = prepare_audio(ami.audio_path(data_dir, m), data_dir / "cache" / "wav16k" / f"{m}.wav")
            hyp = diarizer.diarize(wav.path)
            save_cached(cp, hyp)
        ref = ami.load_reference_turns(data_dir, m)
        uem = ami.read_uem(ami.uem_path(data_dir, m))
        speech_s = sum(t.end - t.start for t in ref)
        n_ref, n_hyp = len({t.speaker for t in ref}), len({t.speaker for t in hyp.overlap})
        for collar in (0.0, 0.25):
            r = der(ref, hyp.overlap, uem, collar)
            pooled[collar].append((r, speech_s))
            rows.append([m, collar, f"{r.der * 100:.2f}", f"{r.missed * 100:.2f}", f"{r.false_alarm * 100:.2f}",
                         f"{r.confusion * 100:.2f}", f"{r.jer * 100:.2f}", f"{n_hyp}/{n_ref}"])
    for collar, items in pooled.items():
        total = sum(w for _, w in items)
        if total:
            avg = sum(r.der * w for r, w in items) / total
            rows.append(["ALL (speech-weighted)", collar, f"{avg * 100:.2f}", "", "", "", "", ""])

    md = write_report(
        REPORTS, "diarization_der", "Diarization error rate: AMI",
        ["meeting", "collar s", "DER %", "missed %", "false alarm %", "confusion %", "JER %", "speakers hyp/ref"],
        rows,
        ["Pipeline: pyannote/speaker-diarization-community-1, no speaker-count hint, overlap-aware output scored.",
         "Reference: AMI-diarization-setup only_words RTTM; scoring region from the UEM files.",
         "Collar 0 is the strict setting; collar 0.25 forgives +/-0.25 s around each reference boundary (NIST convention)."],
    )
    print("wrote", md)


if __name__ == "__main__":
    main()
