"""Local-disk storage behind a small interface (put, get, path, exists, delete_prefix)."""

import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, Protocol


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def put_stream(self, key: str, stream: BinaryIO) -> int: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def local_path(self, key: str) -> Path: ...
    def delete_prefix(self, prefix: str) -> None: ...


def _clear_readonly_and_retry(func: Callable[[str], object], path: str, _exc: object) -> None:
    """rmtree error hook. Synced folders (OneDrive) mark directories read-only, which Windows
    refuses to delete; clear the flag and retry once."""
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    func(path)


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"storage key escapes the storage root: {key!r}")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)  # readers never see a half-written checkpoint

    def put_stream(self, key: str, stream: BinaryIO) -> int:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        try:
            with tmp.open("wb") as out:
                shutil.copyfileobj(stream, out)
        except BaseException:
            tmp.unlink(missing_ok=True)  # never leave a partial upload behind
            raise
        tmp.replace(path)
        return path.stat().st_size

    def get(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def local_path(self, key: str) -> Path:
        return self._resolve(key)

    def delete_prefix(self, prefix: str) -> None:
        target = self._resolve(prefix)
        if target.is_dir():
            shutil.rmtree(target, onerror=_clear_readonly_and_retry)
        elif target.exists():
            target.unlink()
