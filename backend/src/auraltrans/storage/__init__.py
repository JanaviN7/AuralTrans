from pathlib import Path

from auraltrans.config import settings
from auraltrans.storage.local import LocalStorage, Storage

__all__ = ["LocalStorage", "Storage", "get_storage"]

_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if settings.storage_backend != "local":
            raise NotImplementedError("only local storage is implemented")
        _storage = LocalStorage(Path(settings.storage_path))
    return _storage
