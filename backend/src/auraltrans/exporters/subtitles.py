"""SRT and VTT. Utterances become cues; long ones are split on word timestamps."""

from dataclasses import dataclass

from auraltrans.exporters.common import ExportData, ExportUtterance, srt_time, vtt_time

MAX_CUE_S = 7.0
MAX_CUE_CHARS = 84
MIN_CUE_BEFORE_SENTENCE_BREAK_S = 2.0
_SENTENCE_END = (".", "?", "!")


@dataclass
class Cue:
    start: float
    end: float
    speaker: str
    text: str


def cues_for(utt: ExportUtterance) -> list[Cue]:
    if not utt.words:
        return [Cue(utt.start, utt.end, utt.speaker, utt.text)]
    cues: list[Cue] = []
    run: list[str] = []
    run_start = utt.words[0].start
    run_end = run_start
    for word in utt.words:
        candidate_len = len(" ".join([*run, word.text]))
        too_long = run and (word.end - run_start > MAX_CUE_S or candidate_len > MAX_CUE_CHARS)
        if too_long:
            cues.append(Cue(run_start, run_end, utt.speaker, " ".join(run)))
            run, run_start = [], word.start
        run.append(word.text)
        run_end = word.end
        if word.text.endswith(_SENTENCE_END) and run_end - run_start >= MIN_CUE_BEFORE_SENTENCE_BREAK_S:
            cues.append(Cue(run_start, run_end, utt.speaker, " ".join(run)))
            run = []
            run_start = run_end
    if run:
        cues.append(Cue(run_start, run_end, utt.speaker, " ".join(run)))
    return cues


def _all_cues(data: ExportData) -> list[Cue]:
    cues = [c for u in data.utterances for c in cues_for(u)]
    # a cue must have a visible duration, and never run into the next one
    for i, cue in enumerate(cues):
        if cue.end <= cue.start:
            cue.end = cue.start + 0.5
        if i + 1 < len(cues) and cue.end > cues[i + 1].start > cue.start:
            cue.end = cues[i + 1].start
    return cues


def to_srt(data: ExportData) -> str:
    blocks = [
        f"{n}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.speaker}: {c.text}\n"
        for n, c in enumerate(_all_cues(data), start=1)
    ]
    return "\n".join(blocks)


def to_vtt(data: ExportData) -> str:
    blocks = [
        f"{vtt_time(c.start)} --> {vtt_time(c.end)}\n<v {c.speaker}>{c.text}\n"
        for c in _all_cues(data)
    ]
    return "WEBVTT\n\n" + "\n".join(blocks)
