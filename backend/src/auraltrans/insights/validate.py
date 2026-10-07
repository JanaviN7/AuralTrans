"""Schema and citation validation for model output. Pure functions, no I/O.

Policy: the model proposes, this code disposes.
- Unknown utterance ids are removed from evidence.
- An item left with no valid evidence is dropped (never shown as fact).
- An item whose wording or numbers are not found in the cited lines is kept but marked "unverified".
- Chapters must reference real utterances; they are ordered and made non-overlapping.
"""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from auraltrans.insights.support import support_ratio
from auraltrans.insights.transcript import Line
from auraltrans.schemas.insights import (
    ActionItem,
    Chapter,
    Citation,
    Decision,
    Insights,
    OpenQuestion,
    SummaryPoint,
)

# A summary synthesises many lines, so it is held to a looser wording test (numbers are still checked).
SUPPORT_THRESHOLD = 0.3
SUMMARY_THRESHOLD = 0.2


class _Raw(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RawItem(_Raw):
    text: str
    evidence: list[str | int] = []

    @field_validator("evidence", mode="before")
    @classmethod
    def _listify(cls, v: Any) -> Any:
        return [] if v is None else ([v] if isinstance(v, (str, int)) else v)


class RawAction(_Raw):
    task: str
    owner: str | None = None
    due: str | None = None
    evidence: list[str | int] = []

    @field_validator("evidence", mode="before")
    @classmethod
    def _listify(cls, v: Any) -> Any:
        return RawItem._listify(v)


class RawChapter(_Raw):
    title: str
    start: str | int
    end: str | int


class RawInsights(_Raw):
    summary: RawItem | None = None
    key_points: list[RawItem] = []
    decisions: list[RawItem] = []
    action_items: list[RawAction] = []
    open_questions: list[RawItem] = []
    chapters: list[RawChapter] = []

    @field_validator("key_points", "decisions", "action_items", "open_questions", "chapters", mode="before")
    @classmethod
    def _none_is_empty(cls, v: Any) -> Any:
        return [] if v is None else v


_UID = re.compile(r"^\W*u?(\d+)\W*$", re.IGNORECASE)


_LEADING_UID = re.compile(r"^\[u(\d+)[\s\]]", re.IGNORECASE)


def parse_uid(value: str | int) -> int | None:
    text = str(value).strip()
    m = _UID.match(text) or _LEADING_UID.match(text)  # a whole pasted line: "[u3 00:12 Ann] ..."
    return int(m.group(1)) if m else None


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def merge_raw(parts: list[RawInsights]) -> RawInsights:
    """Combine per-chunk results. Summaries are joined; list items are concatenated and de-duplicated."""
    if len(parts) == 1:
        return parts[0]
    summaries = [p.summary for p in parts if p.summary and p.summary.text.strip()]
    merged = RawInsights(
        summary=RawItem(
            text=" ".join(s.text.strip() for s in summaries), evidence=[e for s in summaries for e in s.evidence]
        )
        if summaries
        else None,
        chapters=[c for p in parts for c in p.chapters],
    )
    for name in ("key_points", "decisions", "open_questions"):
        seen: set[str] = set()
        for p in parts:
            for item in getattr(p, name):
                if _norm(item.text) not in seen:
                    seen.add(_norm(item.text))
                    getattr(merged, name).append(item)
    seen_tasks: set[str] = set()
    for p in parts:
        for a in p.action_items:
            if _norm(a.task) not in seen_tasks:
                seen_tasks.add(_norm(a.task))
                merged.action_items.append(a)
    return merged


class _Checker:
    def __init__(self, lines: list[Line], names: list[str]) -> None:
        self.names = names
        self.by_idx = {line.idx: line for line in lines}
        self.stats: dict[str, dict[str, int]] = {}

    def evidence(self, raw: list[str | int]) -> tuple[list[Line], int]:
        """Valid, de-duplicated, ordered cited lines, and how many citations were invalid."""
        found: dict[int, Line] = {}
        bad = 0
        for e in raw:
            idx = parse_uid(e)
            if idx is not None and idx in self.by_idx:
                found[idx] = self.by_idx[idx]
            else:
                bad += 1
        return [found[i] for i in sorted(found)], bad

    def cited(
        self, section: str, claim: str, raw: list[str | int], threshold: float = SUPPORT_THRESHOLD
    ) -> tuple[list[Citation], str] | None:
        st = self.stats.setdefault(
            section, {"proposed": 0, "kept": 0, "dropped_no_evidence": 0, "invalid_citations": 0, "unverified": 0}
        )
        st["proposed"] += 1
        lines, bad = self.evidence(raw)
        st["invalid_citations"] += bad
        if not lines:
            st["dropped_no_evidence"] += 1
            return None
        ratio, numbers_ok = support_ratio(claim, [ln.text for ln in lines], self.names)
        status = "verified" if ratio >= threshold and numbers_ok else "unverified"
        st["kept"] += 1
        st["unverified"] += status == "unverified"
        return [Citation(utterance_id=ln.uid) for ln in lines], status


def _owner(owner: str | None, speakers: dict[str, str]) -> str | None:
    """Map the owner name the model wrote back to a real speaker id (name -> id); unknown -> None."""
    if not owner or owner.strip().lower() in {"null", "none", "unknown", "n/a", ""}:
        return None
    o = owner.strip().lower()
    for name, sid in speakers.items():
        if name.lower() == o:
            return sid
    matches = [sid for name, sid in speakers.items() if o in name.lower() or name.lower() in o]
    return matches[0] if len(matches) == 1 else None


def validate_insights(
    raw: RawInsights, lines: list[Line], speakers: dict[str, str]
) -> tuple[Insights, dict[str, Any]]:
    """`speakers` maps display name -> speaker id. Returns the checked payload and a report."""
    chk = _Checker(lines, list(speakers))

    def points(section: str, items: list[RawItem], cls: type[SummaryPoint] | type[Decision] | type[OpenQuestion]) -> list[Any]:
        out = []
        for it in items:
            r = chk.cited(section, it.text, it.evidence)
            if r and it.text.strip():
                out.append(cls(text=it.text.strip(), evidence=r[0], status=r[1]))
        return out

    summary = None
    if raw.summary and raw.summary.text.strip():
        r = chk.cited("summary", raw.summary.text, raw.summary.evidence, SUMMARY_THRESHOLD)
        if r:
            summary = SummaryPoint(text=raw.summary.text.strip(), evidence=r[0], status=r[1])

    actions: list[ActionItem] = []
    for a in raw.action_items:
        r = chk.cited("action_items", a.task, a.evidence)
        if r and a.task.strip():
            actions.append(
                ActionItem(
                    task=a.task.strip(),
                    owner_speaker_id=_owner(a.owner, speakers),
                    due_text=(a.due or "").strip() or None,
                    evidence=r[0],
                    status=r[1],
                )
            )

    chapters, dropped = _chapters(raw.chapters, chk.by_idx)
    report: dict[str, Any] = {
        "sections": chk.stats,
        "chapters": {"proposed": len(raw.chapters), "kept": len(chapters), "dropped": dropped},
    }
    insights = Insights(
        summary=summary,
        key_points=points("key_points", raw.key_points, SummaryPoint),
        decisions=points("decisions", raw.decisions, Decision),
        action_items=actions,
        chapters=chapters,
        open_questions=points("open_questions", raw.open_questions, OpenQuestion),
    )
    return insights, report


def _chapters(raw: list[RawChapter], by_idx: dict[int, Line]) -> tuple[list[Chapter], int]:
    parsed: list[tuple[int, int, str]] = []
    for c in raw:
        s, e = parse_uid(c.start), parse_uid(c.end)
        if s is None or e is None or s not in by_idx or e not in by_idx or not c.title.strip():
            continue
        if s > e:
            s, e = e, s
        parsed.append((s, e, c.title.strip()))
    parsed.sort()
    kept: list[Chapter] = []
    prev_end = -1
    ordered = sorted(by_idx)
    for s, e, title in parsed:
        if s <= prev_end:  # overlaps the previous chapter: start right after it
            nxt = [i for i in ordered if i > prev_end]
            s = nxt[0] if nxt else s
        if s > e or s <= prev_end:
            continue
        kept.append(Chapter(title=title, start_uid=by_idx[s].uid, end_uid=by_idx[e].uid))
        prev_end = e
    return kept, len(raw) - len(kept)
