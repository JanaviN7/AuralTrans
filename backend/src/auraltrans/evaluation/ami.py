"""AMI test subset: meeting list, reference parsing, and a size-first downloader."""

import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from auraltrans.evaluation.metrics import SpeakerText
from auraltrans.schemas import Turn
from auraltrans.speech.diarize import read_rttm

# Official AMI full-corpus-ASR test split has 16 meetings; the blueprint asks for about 10.
# Two to three sessions from each of the four scenarios, chosen once and fixed.
TEST_SUBSET = [
    "IS1009a", "IS1009b", "IS1009c",
    "ES2004a", "ES2004b", "ES2004c",
    "TS3003a", "TS3003b",
    "EN2002a", "EN2002b",
]  # fmt: skip

AUDIO_URL = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/{m}/audio/{m}.Mix-Headset.wav"
ANNOTATIONS_URL = "https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip"
SETUP_RAW = "https://raw.githubusercontent.com/BUTSpeechFIT/AMI-diarization-setup/main"
GAP_JOIN_S = 1.0


@dataclass(frozen=True)
class RefWord:
    start: float
    end: float
    text: str


def ami_dir(data_dir: Path) -> Path:
    return data_dir / "ami"


def audio_path(data_dir: Path, meeting: str) -> Path:
    return ami_dir(data_dir) / "audio" / f"{meeting}.Mix-Headset.wav"


def rttm_path(data_dir: Path, meeting: str) -> Path:
    return ami_dir(data_dir) / "rttm" / f"{meeting}.rttm"


def uem_path(data_dir: Path, meeting: str) -> Path:
    return ami_dir(data_dir) / "uem" / f"{meeting}.uem"


def words_paths(data_dir: Path, meeting: str) -> list[Path]:
    return sorted((ami_dir(data_dir) / "words").glob(f"{meeting}.*.words.xml"))


def parse_words_xml(xml_text: str) -> list[RefWord]:
    """Words from one speaker's NXT words file. Punctuation and vocal sounds are dropped."""
    words: list[RefWord] = []
    for el in ET.fromstring(xml_text).iter():
        if el.tag.rsplit("}", 1)[-1] != "w" or el.get("punc") == "true":
            continue
        text = (el.text or "").strip()
        start, end = el.get("starttime"), el.get("endtime")
        if text and start is not None and end is not None:
            words.append(RefWord(float(start), float(end), text))
    return sorted(words, key=lambda w: (w.start, w.end))


def speaker_segments(speaker: str, words: list[RefWord], gap_s: float = GAP_JOIN_S) -> list[SpeakerText]:
    """Group one speaker's words into segments, splitting at pauses longer than gap_s."""
    segments: list[SpeakerText] = []
    run: list[RefWord] = []
    for w in words:
        if run and w.start - run[-1].end > gap_s:
            segments.append(SpeakerText(speaker, run[0].start, run[-1].end, " ".join(x.text for x in run)))
            run = []
        run.append(w)
    if run:
        segments.append(SpeakerText(speaker, run[0].start, run[-1].end, " ".join(x.text for x in run)))
    return segments


def load_reference(data_dir: Path, meeting: str) -> list[SpeakerText]:
    """Speaker-attributed reference transcript for one meeting, from the downloaded words files."""
    files = words_paths(data_dir, meeting)
    if not files:
        raise FileNotFoundError(f"no words files for {meeting}; run eval/datasets/fetch.py")
    out: list[SpeakerText] = []
    for f in files:
        speaker = f.name.split(".")[1]
        out.extend(speaker_segments(speaker, parse_words_xml(f.read_text(encoding="utf-8"))))
    return sorted(out, key=lambda s: s.start)


def load_reference_turns(data_dir: Path, meeting: str) -> list[Turn]:
    return read_rttm(rttm_path(data_dir, meeting))


def read_uem(path: Path) -> tuple[float, float]:
    fields = path.read_text(encoding="utf-8").split()
    return float(fields[2]), float(fields[3])


# --- download ---------------------------------------------------------------------------------


def remote_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return int(resp.headers["Content-Length"])


def _download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    tmp.replace(dst)


def plan_download(meetings: list[str]) -> dict[str, int]:
    """Exact byte sizes of everything fetch() would download. Makes HEAD requests only."""
    sizes = {f"audio/{m}": remote_size(AUDIO_URL.format(m=m)) for m in meetings}
    sizes["annotations.zip (deleted after extraction)"] = remote_size(ANNOTATIONS_URL)
    return sizes


def fetch(data_dir: Path, meetings: list[str]) -> None:
    """Download audio, word annotations, RTTM and UEM for the given meetings (skips existing)."""
    for m in meetings:
        wav = audio_path(data_dir, m)
        if not wav.exists() or wav.stat().st_size != remote_size(AUDIO_URL.format(m=m)):
            _download(AUDIO_URL.format(m=m), wav)
        _download(f"{SETUP_RAW}/only_words/rttms/test/{m}.rttm", rttm_path(data_dir, m))
        _download(f"{SETUP_RAW}/uems/test/{m}.uem", uem_path(data_dir, m))

    if all(words_paths(data_dir, m) for m in meetings):
        return
    zip_path = ami_dir(data_dir) / "ami_public_manual_1.6.2.zip"
    _download(ANNOTATIONS_URL, zip_path)
    out_dir = ami_dir(data_dir) / "words"
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            base = name.rsplit("/", 1)[-1]
            in_words_dir = name.startswith("words/") or "/words/" in name
            if in_words_dir and base.endswith(".words.xml") and any(base.startswith(f"{m}.") for m in meetings):
                (out_dir / base).write_bytes(zf.read(name))
    zip_path.unlink()
