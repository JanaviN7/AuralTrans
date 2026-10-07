"""The alignment ablation: cpWER for per-segment vs per-word vs per-word+smoothing+exclusive.

    python eval/run_cpwer.py --model small

Reuses the ASR and diarization caches, so run run_asr.py (dataset ami) and
run_diarization.py first. All three variants see identical ASR and diarization output.
"""

import argparse
from pathlib import Path

from auraltrans.config import settings
from auraltrans.evaluation import ami
from auraltrans.evaluation.baselines import VARIANTS
from auraltrans.evaluation.metrics import (
    ErrorCounts,
    SpeakerText,
    cpwer,
    cpwer_fallback,
    meeteval_available,
)
from auraltrans.evaluation.report import cache_path, load_cached, require_final, write_report
from auraltrans.speech.asr import AsrResult
from auraltrans.speech.diarize import DiarizationResult

REPORTS = Path(__file__).parent / "reports"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="small")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--meetings", nargs="+", default=None, help="AMI meeting ids")
    parser.add_argument("--final", action="store_true", help="write a final (publishable) report")
    args = parser.parse_args()
    data_dir = settings.eval_data_dir
    meetings = ami.select_meetings(args.meetings, args.limit)
    if args.final:
        problems = []
        if args.limit is not None or args.meetings:
            problems.append("--limit/--meetings select a subset; final reports need all 10 meetings")
        if not meeteval_available():
            problems.append("meeteval is not installed; final cpWER must come from meeteval (Linux/Colab)")
        require_final(problems)
    skipped: list[str] = []
    mismatches: list[str] = []

    totals = {name: [0, 0, 0, 0, 0] for name in VARIANTS}
    rows: list[list[object]] = []
    impl = ""
    for m in meetings:
        asr = load_cached(cache_path(data_dir, "asr", f"ami_{args.model}_{args.compute_type}", m), AsrResult)
        diar = load_cached(cache_path(data_dir, "diarization", "community-1", m), DiarizationResult)
        if asr is None or diar is None:
            print(f"skip {m}: missing cached ASR or diarization")
            skipped.append(m)
            continue
        ref = ami.load_reference(data_dir, m)
        for name, variant in VARIANTS.items():
            utts = variant(asr.segments, diar.exclusive, diar.overlap)
            hyp = [SpeakerText(u.speaker, u.start, u.end, u.text) for u in utts]
            counts, impl = cpwer(ref, hyp)
            if impl == "meeteval":
                fb = cpwer_fallback(ref, hyp)
                if (fb.errors, fb.length) != (counts.errors, counts.length):
                    mismatches.append(
                        f"{m}/{name}: meeteval {counts.errors}/{counts.length} vs fallback {fb.errors}/{fb.length}"
                    )
            t = totals[name]
            for i, v in enumerate((counts.errors, counts.length, counts.substitutions, counts.deletions, counts.insertions)):
                t[i] += v
            rows.append([m, name, f"{counts.rate * 100:.2f}", counts.length])
    if args.final and skipped:
        require_final([f"missing cached ASR or diarization for {skipped}"])
    if impl == "meeteval" and not mismatches:
        cross_check = "Cross-check: the local fallback implementation agreed with meeteval on every meeting and variant."
    elif mismatches:
        cross_check = f"Cross-check MISMATCHES (meeteval vs fallback): {mismatches}"
    else:
        cross_check = "Cross-check against meeteval not possible here (meeteval not installed)."
    for name, t in totals.items():
        if t[1]:
            total = ErrorCounts(*t)
            rows.append(["ALL", name, f"{total.rate * 100:.2f}", total.length])

    md = write_report(
        REPORTS, "alignment_ablation_cpwer", "Alignment ablation: cpWER on AMI",
        ["meeting", "variant", "cpWER %", "ref words"], rows,
        [f"cpWER implementation: {impl or 'n/a'} (publish only numbers produced with meeteval).",
         f"ASR: faster-whisper {args.model} {args.compute_type}. Diarization: pyannote community-1.",
         ("a = one speaker per Whisper segment (overlap-aware turns); b = per-word overlap assignment "
          "(overlap-aware turns); c = per-word on exclusive turns + smoothing (shipped method)."),
         "ALL rows pool errors over all meetings, not an average of per-meeting rates.",
         cross_check],
        final=args.final,
        banners=([] if impl == "meeteval" else [
            "NOT PUBLISHABLE: cpWER computed with the local fallback, not meeteval. Re-run on Linux/Colab."]),
    )
    print("wrote", md)


if __name__ == "__main__":
    main()
