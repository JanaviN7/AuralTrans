"""Real-time factor per stage, and peak VRAM when a CUDA GPU is used.

    python eval/run_speed.py --files a.wav b.wav --models small --device cpu

RTF = processing seconds / audio seconds (lower is faster). Each file is run once per
model, with models loaded before timing starts.
"""

import argparse
import time
from pathlib import Path

from auraltrans.config import settings
from auraltrans.evaluation.report import write_report
from auraltrans.speech.align import align
from auraltrans.speech.asr import FasterWhisperBackend
from auraltrans.speech.audio import prepare_audio
from auraltrans.speech.diarize import PyannoteDiarizer

REPORTS = Path(__file__).parent / "reports"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=["small"])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()

    cuda = args.device == "cuda"
    if cuda:
        import torch
    work = settings.eval_data_dir / "cache" / "speed"
    diarizer = PyannoteDiarizer(settings.hf_token, args.device)
    rows: list[list[object]] = []
    for model in args.models:
        asr = FasterWhisperBackend(model, args.device, args.compute_type)
        for f in args.files:
            if cuda:
                torch.cuda.reset_peak_memory_stats()
            t = time.perf_counter()
            wav = prepare_audio(f, work / f"{f.stem}.wav")
            t_audio = time.perf_counter() - t
            t = time.perf_counter()
            res = asr.transcribe(wav.path)
            t_asr = time.perf_counter() - t
            t = time.perf_counter()
            diar = diarizer.diarize(wav.path)
            t_diar = time.perf_counter() - t
            t = time.perf_counter()
            align(res.words, diar.exclusive, diar.overlap)
            t_align = time.perf_counter() - t
            total = t_audio + t_asr + t_diar + t_align
            d = wav.duration_s
            vram = f"{torch.cuda.max_memory_allocated() / 2**30:.2f} GiB" if cuda else "n/a (cpu)"
            rows.append([model, args.compute_type, args.device, f.name, f"{d / 60:.1f}",
                         f"{t_audio / d:.3f}", f"{t_asr / d:.3f}", f"{t_diar / d:.3f}", f"{t_align / d:.4f}",
                         f"{total / d:.3f}", vram])
            print(f"{model} {f.name}: end-to-end RTF {total / d:.3f}")

    md = write_report(
        REPORTS, "speed_rtf", "Speed: real-time factor per stage",
        ["model", "compute", "device", "file", "audio min", "RTF audio", "RTF asr", "RTF diarize", "RTF align",
         "RTF total", "peak VRAM"], rows,
        ["RTF = processing time / audio duration. Models are loaded before timing.",
         "Peak VRAM counts PyTorch allocations only (pyannote); faster-whisper (CTranslate2) memory is not included.",
         "Blueprint target (RTF <= 0.15 for a 60 min file) applies to a GPU run, not CPU."],
    )
    print("wrote", md)


if __name__ == "__main__":
    main()
