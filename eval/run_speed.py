"""Real-time factor per stage, and peak VRAM when a CUDA GPU is used.

    python eval/run_speed.py --files a.wav b.wav --models small --device cpu

RTF = processing seconds / audio seconds (lower is faster). Each file is run once per
model, with models loaded before timing starts.
"""

import argparse
import time
from pathlib import Path

from auraltrans.config import settings
from auraltrans.evaluation import ami
from auraltrans.evaluation.gpu import GpuMemorySampler, gpu_name
from auraltrans.evaluation.report import require_final, write_report
from auraltrans.speech.align import align
from auraltrans.speech.asr import FasterWhisperBackend
from auraltrans.speech.audio import prepare_audio
from auraltrans.speech.diarize import PyannoteDiarizer

REPORTS = Path(__file__).parent / "reports"


def _gib(sampler: GpuMemorySampler) -> str:
    return f"{sampler.peak_gib:.2f}" if sampler.peak_gib is not None else "n/a"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", type=Path, default=None)
    parser.add_argument("--ami-subset", action="store_true", help="use all 10 AMI test-subset meetings")
    parser.add_argument("--models", nargs="+", default=["small"])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--no-warmup", action="store_true", help="skip the untimed warm-up pass")
    parser.add_argument("--final", action="store_true", help="write a final (non-preliminary) report")
    args = parser.parse_args()
    data_dir = settings.eval_data_dir
    if args.ami_subset:
        files = [ami.audio_path(data_dir, m) for m in ami.TEST_SUBSET]
    elif args.files:
        files = args.files
    else:
        parser.error("pass --files or --ami-subset")
    if args.final:
        problems = []
        if not args.ami_subset:
            problems.append("final speed results use --ami-subset (all 10 meetings)")
        if args.device != "cuda" or gpu_name() is None:
            problems.append("final speed results need a CUDA GPU visible to nvidia-smi")
        if args.no_warmup:
            problems.append("final results need the warm-up pass (first CUDA call is slow)")
        require_final(problems)

    cuda = args.device == "cuda"
    work = data_dir / "cache" / "speed"
    diarizer = PyannoteDiarizer(settings.hf_token, args.device)
    rows: list[list[object]] = []
    for model in args.models:
        asr = FasterWhisperBackend(model, args.device, args.compute_type)
        if cuda and not args.no_warmup:
            # Untimed pass on the first file so CUDA initialisation and kernel selection are not
            # charged to it.
            warm = prepare_audio(files[0], work / f"warmup_{files[0].stem}.wav")
            asr.transcribe(warm.path)
            diarizer.diarize(warm.path)
        for f in files:
            t = time.perf_counter()
            wav = prepare_audio(f, work / f"{f.stem}.wav")
            t_audio = time.perf_counter() - t
            with GpuMemorySampler() as mem_asr:
                t = time.perf_counter()
                res = asr.transcribe(wav.path)
                t_asr = time.perf_counter() - t
            with GpuMemorySampler() as mem_diar:
                t = time.perf_counter()
                diar = diarizer.diarize(wav.path)
                t_diar = time.perf_counter() - t
            t = time.perf_counter()
            align(res.words, diar.exclusive, diar.overlap)
            t_align = time.perf_counter() - t
            total = t_audio + t_asr + t_diar + t_align
            d = wav.duration_s
            rows.append([model, args.compute_type, args.device, f.name, f"{d / 60:.1f}",
                         f"{t_audio / d:.3f}", f"{t_asr / d:.3f}", f"{t_diar / d:.3f}", f"{t_align / d:.4f}",
                         f"{total / d:.3f}", _gib(mem_asr), _gib(mem_diar)])
            print(f"{model} {f.name}: end-to-end RTF {total / d:.3f}")

    md = write_report(
        REPORTS, "speed_rtf", "Speed: real-time factor per stage",
        ["model", "compute", "device", "file", "audio min", "RTF audio", "RTF asr", "RTF diarize", "RTF align",
         "RTF total", "peak GPU GiB (asr)", "peak GPU GiB (diarize)"], rows,
        ["RTF = processing time / audio duration. Models are loaded before timing; on GPU one untimed warm-up pass runs first.",
         ("Peak GPU memory is device-wide memory.used from nvidia-smi (polled every 0.25 s) during that stage, so it"
          " includes both resident models and the CUDA context. It is not the memory of one model alone."),
         "'n/a' means no NVIDIA GPU was visible.",
         ("Blueprint target (RTF <= 0.15 for a 60 min file) applies to the GPU run; the AMI meetings are 14-39 min,"
          " so this is a per-meeting measurement, not a 60 min file.")],
        final=args.final,
    )
    print("wrote", md)


if __name__ == "__main__":
    main()
