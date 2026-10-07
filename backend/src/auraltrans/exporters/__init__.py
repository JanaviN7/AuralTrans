from collections.abc import Callable

from auraltrans.exporters.common import (
    ExportData,
    ExportSpeakerStats,
    ExportUtterance,
    ExportWord,
)
from auraltrans.exporters.subtitles import to_srt, to_vtt
from auraltrans.exporters.text import to_json, to_md, to_txt

# format -> (renderer, content type, file extension)
EXPORTERS: dict[str, tuple[Callable[[ExportData], str], str, str]] = {
    "srt": (to_srt, "application/x-subrip", "srt"),
    "vtt": (to_vtt, "text/vtt", "vtt"),
    "txt": (to_txt, "text/plain", "txt"),
    "md": (to_md, "text/markdown", "md"),
    "json": (to_json, "application/json", "json"),
}

__all__ = [
    "EXPORTERS",
    "ExportData",
    "ExportSpeakerStats",
    "ExportUtterance",
    "ExportWord",
]
