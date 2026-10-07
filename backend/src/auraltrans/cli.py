"""`auraltrans run file.wav --out out/`: the speech core without the API."""

import argparse
import json
from pathlib import Path

from auraltrans.config import settings
from auraltrans.schemas import Speaker, Transcript
from auraltrans.speech.align import align
from auraltrans.speech.analytics import compute_analytics
from auraltrans.speech.asr import FasterWhisperBackend
from auraltrans.speech.audio import prepare_audio
from auraltrans.speech.diarize import PyannoteDiarizer, write_rttm


def run(args: argparse.Namespace) -> None:
    out: Path = args.out
    artifacts = out / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    audio = prepare_audio(args.file, out / "audio_16k.wav")
    asr = FasterWhisperBackend(args.model, args.device, args.compute_type).transcribe(
        audio.path, args.language
    )
    (artifacts / "asr.json").write_text(asr.model_dump_json(indent=2), encoding="utf-8")

    diar = PyannoteDiarizer(settings.hf_token, args.device).diarize(
        audio.path, args.min_speakers, args.max_speakers
    )
    write_rttm(diar.overlap, artifacts / "diarization.rttm")
    write_rttm(diar.exclusive, artifacts / "diarization_exclusive.rttm")

    utterances = align(asr.words, diar.exclusive, diar.overlap)
    analytics = compute_analytics(utterances, audio.duration_s, diar.overlap)
    transcript = Transcript(
        language=asr.language,
        duration_s=audio.duration_s,
        speakers=[
            Speaker(id=sp, talk_time_s=s.talk_time_s) for sp, s in sorted(analytics.speakers.items())
        ],
        utterances=utterances,
    )
    (artifacts / "aligned.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    (artifacts / "analytics.json").write_text(analytics.model_dump_json(indent=2), encoding="utf-8")
    print(json.dumps({"speakers": len(analytics.speakers), "utterances": len(utterances)}))


def main() -> None:
    parser = argparse.ArgumentParser(prog="auraltrans")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="transcribe, diarize, align and analyse one recording")
    p.add_argument("file", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default="small")
    p.add_argument("--device", default="cpu")
    p.add_argument("--compute-type", default="int8")
    p.add_argument("--language", default=None)
    p.add_argument("--min-speakers", type=int, default=None)
    p.add_argument("--max-speakers", type=int, default=None)
    p.set_defaults(func=run)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
