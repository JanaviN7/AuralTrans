"""WER, DER and cpWER on top of jiwer, pyannote.metrics and (where installable) meeteval."""

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jiwer
from pyannote.core.annotation import Annotation
from pyannote.core.segment import Segment
from pyannote.core.timeline import Timeline
from pyannote.metrics.diarization import DiarizationErrorRate, JaccardErrorRate
from scipy.optimize import linear_sum_assignment  # type: ignore[attr-defined]

from auraltrans.schemas import Turn


@dataclass(frozen=True)
class ErrorCounts:
    errors: int
    length: int
    substitutions: int
    deletions: int
    insertions: int

    @property
    def rate(self) -> float:
        return self.errors / self.length if self.length else 0.0


@lru_cache(maxsize=1)
def _normalizer() -> Any:
    from whisper_normalizer.english import EnglishTextNormalizer

    return EnglishTextNormalizer()  # type: ignore[no-untyped-call]


def normalize_text(text: str) -> str:
    return str(_normalizer()(text)).strip()


def wer(references: list[str], hypotheses: list[str]) -> ErrorCounts:
    """Corpus-level WER after the Whisper English normalizer; empty references are skipped."""
    pairs = [(normalize_text(r), normalize_text(h)) for r, h in zip(references, hypotheses, strict=True)]
    pairs = [(r, h) for r, h in pairs if r]
    if not pairs:
        return ErrorCounts(0, 0, 0, 0, 0)
    out = jiwer.process_words([r for r, _ in pairs], [h for _, h in pairs])
    return ErrorCounts(
        errors=out.substitutions + out.deletions + out.insertions,
        length=out.substitutions + out.deletions + out.hits,
        substitutions=out.substitutions,
        deletions=out.deletions,
        insertions=out.insertions,
    )


# --- diarization -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DerResult:
    der: float
    missed: float
    false_alarm: float
    confusion: float
    jer: float
    collar: float


def _annotation(turns: list[Turn]) -> Annotation:
    ann = Annotation()
    for t in turns:
        if t.end > t.start:
            ann[Segment(t.start, t.end)] = t.speaker
    return ann


def der(
    reference: list[Turn],
    hypothesis: list[Turn],
    uem: tuple[float, float] | None = None,
    collar: float = 0.0,
) -> DerResult:
    """DER (and JER) for one file. Overlapped speech is scored, not skipped.

    `collar` is the usual one-sided value: 0.25 forgives +/-0.25 s around each reference boundary.
    pyannote's own parameter is the total width, so it receives twice this value.
    """
    ref, hyp = _annotation(reference), _annotation(hypothesis)
    pyannote_collar = 2 * collar
    uem_tl = Timeline([Segment(*uem)]) if uem else None
    metric: Any = DiarizationErrorRate(collar=pyannote_collar, skip_overlap=False)
    value = metric(ref, hyp, uem=uem_tl)
    comp: dict[str, float] = dict(metric[:])
    total = comp["total"] or 1.0
    jer_metric: Any = JaccardErrorRate(collar=pyannote_collar, skip_overlap=False)  # type: ignore[no-untyped-call]
    jer = jer_metric(ref, hyp, uem=uem_tl)
    return DerResult(
        der=float(value),
        missed=comp["missed detection"] / total,
        false_alarm=comp["false alarm"] / total,
        confusion=comp["confusion"] / total,
        jer=float(jer),
        collar=collar,
    )


def pooled_der(per_file: list[tuple[DerResult, float]]) -> float:
    """Duration-weighted DER across files; each item is (result, reference speech seconds)."""
    total = sum(w for _, w in per_file)
    return sum(r.der * w for r, w in per_file) / total if total else 0.0


# --- cpWER -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class SpeakerText:
    speaker: str
    start: float
    end: float
    text: str


def _per_speaker_words(items: list[SpeakerText]) -> dict[str, list[str]]:
    grouped: dict[str, list[SpeakerText]] = defaultdict(list)
    for it in items:
        grouped[it.speaker].append(it)
    return {
        spk: normalize_text(" ".join(i.text for i in sorted(group, key=lambda i: (i.start, i.end)))).split()
        for spk, group in grouped.items()
    }


def cpwer_fallback(reference: list[SpeakerText], hypothesis: list[SpeakerText]) -> ErrorCounts:
    """Concatenated minimum-permutation WER, solved as an assignment problem.

    Used on Windows, where meeteval cannot be installed. Published numbers use meeteval.
    """
    ref, hyp = _per_speaker_words(reference), _per_speaker_words(hypothesis)
    ref_names, hyp_names = sorted(ref), sorted(hyp)
    size = max(len(ref_names), len(hyp_names))
    empty: list[str] = []
    ref_words = [ref[n] for n in ref_names] + [empty] * (size - len(ref_names))
    hyp_words = [hyp[n] for n in hyp_names] + [empty] * (size - len(hyp_names))

    def counts(r: list[str], h: list[str]) -> tuple[int, int, int]:
        if not r:
            return 0, 0, len(h)
        if not h:
            return 0, len(r), 0
        o = jiwer.process_words(" ".join(r), " ".join(h))
        return o.substitutions, o.deletions, o.insertions

    table = [[counts(r, h) for h in hyp_words] for r in ref_words]
    cost = [[sum(c) for c in row] for row in table]
    rows, cols = linear_sum_assignment(cost)
    s = sum(table[i][j][0] for i, j in zip(rows, cols, strict=True))
    d = sum(table[i][j][1] for i, j in zip(rows, cols, strict=True))
    ins = sum(table[i][j][2] for i, j in zip(rows, cols, strict=True))
    return ErrorCounts(s + d + ins, sum(len(w) for w in ref_words), s, d, ins)


def cpwer_meeteval(reference: list[SpeakerText], hypothesis: list[SpeakerText]) -> ErrorCounts:
    """cpWER via meeteval (Linux/Colab/CI only). Inputs are normalized the same way as the fallback."""
    import meeteval

    def seglst(items: list[SpeakerText]) -> list[dict[str, object]]:
        return [
            {
                "session_id": "s",
                "speaker": i.speaker,
                "start_time": i.start,
                "end_time": i.end,
                "words": normalize_text(i.text),
            }
            for i in items
        ]

    result = meeteval.wer.cpwer(seglst(reference), seglst(hypothesis))["s"]
    return ErrorCounts(
        errors=result.errors,
        length=result.length,
        substitutions=result.substitutions,
        deletions=result.deletions,
        insertions=result.insertions,
    )


def meeteval_available() -> bool:
    try:
        import meeteval  # noqa: F401
    except ImportError:
        return False
    return True


def cpwer(reference: list[SpeakerText], hypothesis: list[SpeakerText]) -> tuple[ErrorCounts, str]:
    """Returns the counts and the implementation used ('meeteval' or 'fallback')."""
    if meeteval_available():
        return cpwer_meeteval(reference, hypothesis), "meeteval"
    return cpwer_fallback(reference, hypothesis), "fallback"
