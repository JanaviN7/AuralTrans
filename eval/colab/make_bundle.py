"""Zip the evaluation code for Colab, tied to the git commit it came from.

    python eval/colab/make_bundle.py

Writes dist/auraltrans-eval-bundle-<commit>.zip containing backend/ (source, tests, lock file) and
eval/ (scripts and docs), plus BUNDLE_MANIFEST.json with the commit and a SHA-256 per file.
Refuses to bundle uncommitted changes unless --allow-dirty, so a final result can always be traced
to a commit. No .env, virtualenv, data or reports are included.
"""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INCLUDE = ["backend/pyproject.toml", "backend/uv.lock", "backend/src", "backend/tests", "eval"]
EXCLUDE_PARTS = {"__pycache__", ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", "reports"}
EXCLUDE_NAMES = {".env"}
EXCLUDE_SUFFIXES = {".pyc", ".wav", ".mp3", ".m4a", ".flac"}


def git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def collect() -> list[Path]:
    files: list[Path] = []
    for item in INCLUDE:
        path = ROOT / item
        candidates = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for p in candidates:
            rel = p.relative_to(ROOT)
            if EXCLUDE_PARTS & set(rel.parts) or p.name in EXCLUDE_NAMES or p.suffix in EXCLUDE_SUFFIXES:
                continue
            files.append(p)
    return files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()

    commit = git("rev-parse", "--short", "HEAD")
    dirty_files = [line for line in git("status", "--porcelain", "--", *INCLUDE).splitlines() if line]
    if dirty_files and not args.allow_dirty:
        raise SystemExit(
            "Uncommitted changes in bundled paths; commit first (or pass --allow-dirty):\n  "
            + "\n  ".join(dirty_files)
        )

    files = collect()
    manifest = {
        "commit": commit,
        "dirty": bool(dirty_files),
        "files": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"auraltrans-eval-bundle-{commit}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(ROOT).as_posix())
        zf.writestr("BUNDLE_MANIFEST.json", json.dumps(manifest, indent=2))
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB, {len(files)} files, commit {commit}"
          f"{', DIRTY' if dirty_files else ''})")


if __name__ == "__main__":
    main()
