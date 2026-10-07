"""The transcript as the model sees it: one `[uN mm:ss Speaker] text` line per utterance."""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from auraltrans.api.queries import speakers_out
from auraltrans.db.models import Utterance


@dataclass(frozen=True)
class Line:
    uid: str
    idx: int
    start_s: float
    end_s: float
    speaker_id: uuid.UUID | None
    speaker: str
    text: str


def clock(seconds: float) -> str:
    s = int(seconds)
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def load_lines(session: Session, recording_id: uuid.UUID) -> list[Line]:
    names = {sp.id: sp.name for sp in speakers_out(session, recording_id)}
    rows = session.scalars(
        select(Utterance).where(Utterance.recording_id == recording_id).order_by(Utterance.idx)
    )
    return [
        Line(
            uid=f"u{u.idx}",
            idx=u.idx,
            start_s=u.start_s,
            end_s=u.end_s,
            speaker_id=u.speaker_id,
            speaker=names.get(u.speaker_id, "Unknown speaker") if u.speaker_id else "Unknown speaker",
            text=u.text.strip(),
        )
        for u in rows
        if u.text.strip()
    ]


def render_line(line: Line) -> str:
    return f"[{line.uid} {clock(line.start_s)} {line.speaker}] {line.text}"


def render(lines: list[Line]) -> str:
    return "\n".join(render_line(line) for line in lines)


def transcript_hash(lines: list[Line]) -> str:
    """Changes when any utterance text changes (speaker renames do not count)."""
    h = hashlib.sha256()
    for line in lines:
        h.update(f"{line.uid}\x1f{line.text}\x1e".encode())
    return h.hexdigest()


def chunk(lines: list[Line], max_chars: int) -> list[list[Line]]:
    """Split into consecutive windows of at most max_chars rendered characters."""
    chunks: list[list[Line]] = []
    current: list[Line] = []
    size = 0
    for line in lines:
        n = len(render_line(line)) + 1
        if current and size + n > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(line)
        size += n
    if current:
        chunks.append(current)
    return chunks
