"""Single-recording Q&A. The whole transcript goes in the prompt (no retrieval), and an answer is
only returned when its citations check out against the transcript. Otherwise the service abstains."""

import time
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from auraltrans.config import settings
from auraltrans.insights.support import quote_in, support_ratio
from auraltrans.insights.transcript import Line, render
from auraltrans.insights.validate import parse_uid
from auraltrans.llm import LLM, complete_validated

PROMPT_VERSION = "ask-v1"
AbstainReason = Literal["model_declined", "no_valid_citation", "unsupported_answer"]
ABSTAIN_MESSAGE = "I can't find that in this recording."
SUPPORT_THRESHOLD = 0.25

SYSTEM = """You answer questions about ONE recording, using only its transcript.

Rules:
- If the transcript does not contain the answer, set "answerable" to false and "answer" to an empty string. Do not guess, do not use outside knowledge, and do not answer from what is merely plausible.
- Otherwise answer concisely (1-4 sentences), in the language of the question, using only what the transcript says. Say who said it when that matters.
- Support the answer with 1 to 3 citations. Each citation has the line "id" (for example "u12") and a short "quote": words copied exactly from that line.
- A question about something never discussed is unanswerable, even if it sounds related to the topics discussed.
- Reply with ONE JSON object: {"answerable": true|false, "answer": "...", "citations": [{"id": "u12", "quote": "..."}]}"""


JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["id", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answerable", "answer", "citations"],
    "additionalProperties": False,
}


class _RawCitation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | int
    quote: str = ""


class _RawAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answerable: bool
    answer: str = ""
    citations: list[_RawCitation] = []


@dataclass
class AskResult:
    answer: str
    citations: list[dict[str, str]] = field(default_factory=list)  # {"uid", "quote"}
    abstained: bool = False
    abstain_reason: AbstainReason | None = None
    model: str = ""
    latency_ms: int = 0


class TranscriptTooLong(ValueError):
    pass


def too_long(lines: list[Line]) -> bool:
    return sum(len(line.text) + 24 for line in lines) > settings.llm_context_chars


def ask(llm: LLM, question: str, title: str, lines: list[Line]) -> AskResult:
    if too_long(lines):
        raise TranscriptTooLong(
            "This recording is too long to answer questions about in one pass yet. "
            "Searching inside long recordings is planned but not built."
        )
    started = time.perf_counter()
    user = f'Recording: "{title}"\n\n<transcript>\n{render(lines)}\n</transcript>\n\nQuestion: {question}'
    raw, _ = complete_validated(
        llm, SYSTEM, user, _RawAnswer, purpose="ask", prompt_version=PROMPT_VERSION, max_tokens=1200,
        schema=JSON_SCHEMA,
    )
    result = verify(raw, lines)
    result.model = llm.model
    result.latency_ms = int((time.perf_counter() - started) * 1000)
    return result


def verify(raw: _RawAnswer, lines: list[Line]) -> AskResult:
    def abstain(reason: AbstainReason) -> AskResult:
        return AskResult(ABSTAIN_MESSAGE, abstained=True, abstain_reason=reason)

    if not raw.answerable or not raw.answer.strip():
        return abstain("model_declined")
    by_idx = {line.idx: line for line in lines}
    good: dict[int, str] = {}
    for c in raw.citations:
        idx = parse_uid(c.id)
        line = by_idx.get(idx) if idx is not None else None
        if line and quote_in(c.quote, line.text):
            good.setdefault(idx, c.quote.strip())  # type: ignore[arg-type]
    if not good:
        return abstain("no_valid_citation")
    ratio, numbers_ok = support_ratio(
        raw.answer, [by_idx[i].text for i in good], sorted({line.speaker for line in lines})
    )
    if ratio < SUPPORT_THRESHOLD or not numbers_ok:
        return abstain("unsupported_answer")
    return AskResult(
        raw.answer.strip(), citations=[{"uid": f"u{i}", "quote": q} for i, q in sorted(good.items())]
    )
