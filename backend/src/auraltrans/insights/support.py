"""Cheap, deterministic checks that a claim is supported by the transcript lines it cites.

This is not entailment checking. It catches the common failures: citing unrelated lines, and
inventing numbers. A claim that fails is marked "unverified" (or, for Ask, abstained), never trusted.
"""

import re

_STOP = frozenset(
    """a an and are as at be been but by can could did do does for from had has have he her his i if in
    into is it its just me my not of on or our she should so than that the their them then there these
    they this to too us was we were what when where which who will with would you your about also very
    really okay yeah yes like going got get one some any all more most such only own same""".split()  # noqa: SIM905
)
_NUMBER_WORDS = {
    w: str(n)
    for n, w in enumerate(
        ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
    )
} | {"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "hundred": "100"}
_TENS = {"twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90"}
_UNITS = {w: str(n) for n, w in enumerate("one two three four five six seven eight nine".split(), 1)}  # noqa: SIM905
_WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")


def _stem(w: str) -> str:
    for suffix in ("ing", "ed", "es", "ly", "s"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def normalize(text: str) -> str:
    return " ".join(_WORD.findall(text.lower().replace("'", "")))


def content_tokens(text: str) -> set[str]:
    out: set[str] = set()
    raw = _WORD.findall(text.lower().replace("'", ""))
    words: list[str] = []
    for w in raw:  # "twenty five" -> "25"
        prev = words[-1] if words else ""
        if prev in _TENS and w in _UNITS:
            words[-1] = str(int(_TENS[prev]) + int(_UNITS[w]))
        else:
            words.append(w)
    for w in words:
        w = _NUMBER_WORDS.get(w, w)
        if w in _STOP or (len(w) < 3 and not w.isdigit()):
            continue
        out.add(w if w.isdigit() else _stem(w))
    return out


def numbers(text: str) -> set[str]:
    return {t for t in content_tokens(text) if t[0].isdigit()}


def strip_names(text: str, names: list[str]) -> str:
    """Remove speaker names ("Speaker 2", "Priya") so they count neither as words nor numbers."""
    text = re.sub(r"\bspeaker\s*\d+\b", " ", text, flags=re.IGNORECASE)
    for name in sorted(names, key=len, reverse=True):
        if name.strip():
            text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    return text


def support_ratio(claim: str, cited: list[str], names: list[str] | None = None) -> tuple[float, bool]:
    """(fraction of the claim's content words found in the cited lines, no number is invented)."""
    claim = strip_names(claim, names or [])
    claim_tokens = content_tokens(claim)
    if not claim_tokens:
        return 1.0, True
    cited_tokens: set[str] = set()
    for t in cited:
        cited_tokens |= content_tokens(t)
    hit = len(claim_tokens & cited_tokens) / len(claim_tokens)
    return hit, numbers(claim) <= cited_tokens


def quote_in(quote: str, line_text: str) -> bool:
    """True if `quote` is (nearly) verbatim from the line: substring after normalisation, or the
    quote's words all appear in order-insensitive fashion with at most 15% missing."""
    q, t = normalize(quote), normalize(line_text)
    if not q:
        return False
    if q in t:
        return True
    qw = q.split()
    if len(qw) < 4:
        return False
    present = sum(1 for w in qw if w in set(t.split()))
    return present / len(qw) >= 0.85
