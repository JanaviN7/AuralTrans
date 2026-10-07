"""WER per Whisper model size on the LibriSpeech subset and/or the AMI meetings.

    python eval/run_asr.py --dataset librispeech --models tiny small
    python eval/run_asr.py --dataset ami --models small --limit 2

ASR output is cached under EVAL_DATA_DIR/cache/asr so run_cpwer.py can reuse it.
"""

import argparse
import time
from pathlib import Path

from auraltrans.config import settings
from auraltrans.evaluation import ami, librispeech
from auraltrans.evaluation.metrics import wer
from auraltrans.evaluation.report import (
    cache_path,
    load_cached,
    require_final,
    save_cached,
    write_report,
)
from auraltrans.speech.asr import AsrResult, FasterWhisperBackend
from auraltrans.speech.audio import prepare_audio

REPORTS = Path(__file__).parent / "reports"


def items(dataset: str, limit: int | None, meetings: list[str] | None) -> list[tuple[str, Path, str]]:
    """(id, audio path, reference text)."""
    data_dir = settings.eval_data_dir
    if dataset == "librispeech":
        rows = librispeech.load_manifest(data_dir)[:limit]
        return [(r["id"], Path(r["audio"]), r["text"]) for r in rows]
    out = []
    for m in ami.select_meetings(meetings, limit):
        text = " ".join(s.text for s in ami.load_reference(data_dir, m))
        out.append((m, ami.audio_path(data_dir, m), text))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["librispeech", "ami"], required=True)
    parser.add_argument("--models", nargs="+", default=["small"])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-vad", action="store_true", help="experiment: disable the VAD filter")
    parser.add_argument("--meetings", nargs="+", default=None, help="AMI meeting ids")
    parser.add_argument("--final", action="store_true", help="write a final (non-preliminary) report")
    args = parser.parse_args()
    data_dir = settings.eval_data_dir
    if args.final:
        problems = []
        if args.limit is not None or args.meetings:
            problems.append("--limit/--meetings select a subset; final reports need the full set")
        if args.no_vad:
            problems.append("--no-vad is an experiment, not the pipeline configuration")
        if args.device != "cuda":
            problems.append(f"final results come from the GPU run (device is '{args.device}')")
        require_final(problems)
    work = items(args.dataset, args.limit, args.meetings)
    vad_tag = "_novad" if args.no_vad else ""

    rows: list[list[object]] = []
    for model in args.models:
        backend: FasterWhisperBackend | None = None
        refs: list[str] = []
        hyps: list[str] = []
        audio_s = 0.0
        decode_s = 0.0
        for uid, path, ref in work:
            cp = cache_path(data_dir, "asr", f"{args.dataset}_{model}_{args.compute_type}{vad_tag}", uid)
            result = load_cached(cp, AsrResult)
            if result is None:
                backend = backend or FasterWhisperBackend(
                    model, args.device, args.compute_type, vad_filter=not args.no_vad
                )
                wav = prepare_audio(path, data_dir / "cache" / "wav16k" / f"{uid}.wav")
                t0 = time.perf_counter()
                result = backend.transcribe(wav.path, language="en")
                decode_s += time.perf_counter() - t0
                save_cached(cp, result)
            audio_s += result.duration_s
            refs.append(ref)
            hyps.append(" ".join(seg.text for seg in result.segments))
        counts = wer(refs, hyps)
        rows.append([model, args.compute_type, len(work), f"{counts.rate * 100:.2f}", counts.substitutions,
                     counts.deletions, counts.insertions, counts.length,
                     f"{decode_s / audio_s:.3f}" if decode_s else "cached"])
        print(f"{model}: WER {counts.rate * 100:.2f}% over {counts.length} words")
        if args.dataset == "ami":
            for (uid, _, _), ref, hyp in zip(work, refs, hyps, strict=True):
                c = wer([ref], [hyp])
                rows.append([model, args.compute_type, uid, f"{c.rate * 100:.2f}", c.substitutions,
                             c.deletions, c.insertions, c.length, ""])

    md = write_report(
        REPORTS, f"asr_wer_{args.dataset}{vad_tag}",
        f"ASR WER: {args.dataset}" + (" (VAD OFF experiment)" if args.no_vad else ""),
        ["model", "compute", "files", "WER %", "sub", "del", "ins", "ref words", "RTF (this run)"], rows,
        ["WER uses the Whisper English text normalizer (jiwer, corpus level).",
         f"language forced to 'en'; VAD {'OFF (experiment)' if args.no_vad else 'on'}; condition_on_previous_text=False.",
         "RTF counts transcription only and reads 'cached' when results came from the cache.",
         "AMI: the first row per model is pooled over all meetings; rows with a meeting id in `files` are per meeting.",
         "AMI reference excludes truncated word fragments (trunc=true)."],
        final=args.final,
    )
    print("wrote", md)


if __name__ == "__main__":
    main()
