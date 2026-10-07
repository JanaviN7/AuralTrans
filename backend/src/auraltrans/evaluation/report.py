"""Dated markdown + CSV reports, and small JSON caches so slow stages run once."""

import csv
import datetime as dt
import os
import platform
import subprocess
from importlib import metadata
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _today() -> dt.date:
    return dt.datetime.now().astimezone().date()


def cache_path(data_dir: Path, kind: str, key: str, name: str) -> Path:
    return data_dir / "cache" / kind / key / f"{name}.json"


def load_cached(path: Path, model: type[T]) -> T | None:
    return model.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def save_cached(path: Path, value: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.model_dump_json(), encoding="utf-8")


def hardware_line() -> str:
    parts = [platform.platform(), platform.processor() or platform.machine()]
    try:
        import torch

        parts.append(f"CUDA: {torch.cuda.get_device_name(0)}" if torch.cuda.is_available() else "no CUDA GPU")
    except ImportError:
        pass
    return "; ".join(parts)


_TRACKED_PACKAGES = (
    "faster-whisper", "ctranslate2", "pyannote.audio", "pyannote.metrics", "torch",
    "jiwer", "meeteval", "whisper-normalizer",
)


def software_line() -> str:
    """Package versions and git commit, so a result can be tied to the code that produced it."""
    versions = []
    for pkg in _TRACKED_PACKAGES:
        try:
            versions.append(f"{pkg} {metadata.version(pkg)}")
        except metadata.PackageNotFoundError:
            versions.append(f"{pkg} (not installed)")
    commit = os.environ.get("AURALTRANS_COMMIT", "")
    if not commit:
        try:
            out = subprocess.run(
                ["git", "-C", str(Path(__file__).parent), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=False,
            )
            commit = out.stdout.strip() if out.returncode == 0 else "unknown"
        except OSError:  # git is not installed
            commit = "unknown"
    return f"commit {commit}; " + ", ".join(versions)


def require_final(problems: list[str]) -> None:
    """Refuse to write a final (publishable) report unless every condition holds."""
    if problems:
        raise SystemExit("--final refused:\n  - " + "\n  - ".join(problems))


def write_report(
    out_dir: Path,
    name: str,
    title: str,
    columns: list[str],
    rows: list[list[object]],
    notes: list[str],
    final: bool = False,
    banners: list[str] | None = None,
) -> Path:
    """Write eval/reports/YYYY-MM-DD_<name>[_PRELIMINARY].md and .csv, returning the markdown path.

    Reports are PRELIMINARY unless the caller passes final=True, which should only happen for the
    complete evaluation. `banners` are extra warnings shown under the title.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_today().isoformat()}_{name}" + ("" if final else "_PRELIMINARY")
    with (out_dir / f"{stem}.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    heading = title if final else f"PRELIMINARY: {title}"
    warnings = list(banners or [])
    if not final:
        warnings.insert(0, "PRELIMINARY: partial or early run, not for publication until the full evaluation is complete.")
    lines = [f"# {heading}", ""]
    lines.extend(f"> **{w}**" for w in warnings)
    lines += ["", f"Date: {_today().isoformat()}  ", f"Hardware: {hardware_line()}", f"Software: {software_line()}", ""]
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join("---" for _ in columns) + "|")
    lines.extend("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    lines.append("")
    lines.extend(f"- {n}" for n in notes)
    md = out_dir / f"{stem}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md
