"""TXT, Markdown and JSON exports."""

import json

from auraltrans.exporters.common import ExportData, clock


def to_txt(data: ExportData) -> str:
    return "\n".join(f"[{clock(u.start)}] {u.speaker}: {u.text}" for u in data.utterances) + "\n"


def to_md(data: ExportData) -> str:
    lines = [f"# {data.title}", ""]
    meta = []
    if data.duration_s:
        meta.append(f"Duration: {clock(data.duration_s)}")
    if data.language:
        meta.append(f"Language: {data.language}")
    if meta:
        lines += [" · ".join(meta), ""]
    if data.speakers:
        lines += [
            "## Speakers",
            "",
            "| Speaker | Talk time | Share | Turns | Words/min |",
            "|---|---|---|---|---|",
        ]
        for s in data.speakers:
            lines.append(
                f"| {s.name} | {clock(s.talk_time_s)} | {s.talk_share * 100:.0f}% | {s.turns} | "
                f"{s.words_per_minute:.0f} |"
            )
        lines.append("")
    lines += ["## Transcript", ""]
    lines += [f"**{u.speaker}** ({clock(u.start)}): {u.text}\n" for u in data.utterances]
    return "\n".join(lines)


def to_json(data: ExportData) -> str:
    payload = {
        "title": data.title,
        "language": data.language,
        "duration_s": data.duration_s,
        "speakers": [
            {
                "name": s.name,
                "talk_time_s": round(s.talk_time_s, 3),
                "talk_share": round(s.talk_share, 4),
                "turns": s.turns,
                "words_per_minute": round(s.words_per_minute, 1),
            }
            for s in data.speakers
        ],
        "utterances": [
            {
                "idx": u.idx,
                "speaker": u.speaker,
                "start": round(u.start, 3),
                "end": round(u.end, 3),
                "text": u.text,
                "words": [
                    {"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in u.words
                ],
            }
            for u in data.utterances
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
