"""200 LibriSpeech test-clean utterances, fetched as whole parquet row groups by range request.

The parquet file is one 350 MB object made of 27 row groups of ~100 utterances (~13 MB each).
Only complete row groups can be fetched, so the subset is taken from 4 spread-out groups
(50 random utterances from each, seeded) to get 9 speakers for about 47.5 MB instead of 350 MB.
"""

import json
import random
from pathlib import Path
from typing import Any

PARQUET = "datasets/openslr/librispeech_asr@refs/convert/parquet/clean/test/0000.parquet"
ROW_GROUPS = (0, 9, 18, 25)  # group 26 holds only 20 rows, so it is not used
PER_GROUP = 50
SEED = 1337


def libri_dir(data_dir: Path) -> Path:
    return data_dir / "librispeech"


def plan(token: str) -> dict[str, int]:
    """Exact compressed bytes of the row groups fetch() will read (footer-only request)."""
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem

    with HfFileSystem(token=token).open(PARQUET, "rb") as f:
        pf: Any = pq.ParquetFile(f)  # type: ignore[no-untyped-call]
        md = pf.metadata
        return {
            f"row_group_{g}": sum(
                md.row_group(g).column(c).total_compressed_size for c in range(md.row_group(g).num_columns)
            )
            for g in ROW_GROUPS
        }


def fetch(data_dir: Path, token: str) -> Path:
    """Write flac files plus manifest.jsonl (id, speaker, audio path, reference text)."""
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem

    out = libri_dir(data_dir)
    (out / "audio").mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    rng = random.Random(SEED)
    rows: list[dict[str, str]] = []
    with HfFileSystem(token=token).open(PARQUET, "rb") as f:
        pf: Any = pq.ParquetFile(f)  # type: ignore[no-untyped-call]
        for g in ROW_GROUPS:
            table = pf.read_row_group(g, columns=["id", "speaker_id", "text", "audio"])
            for i in sorted(rng.sample(range(table.num_rows), PER_GROUP)):
                row = {k: table.column(k)[i].as_py() for k in ("id", "speaker_id", "text", "audio")}
                path = out / "audio" / f"{row['id']}.flac"
                path.write_bytes(row["audio"]["bytes"])
                rows.append({"id": row["id"], "speaker": str(row["speaker_id"]), "text": row["text"], "audio": str(path)})
    manifest.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return manifest


def load_manifest(data_dir: Path) -> list[dict[str, str]]:
    path = libri_dir(data_dir) / "manifest.jsonl"
    if not path.exists():
        raise FileNotFoundError("LibriSpeech subset not downloaded; run eval/datasets/fetch.py")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
