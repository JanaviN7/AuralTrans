"""Peak GPU memory via nvidia-smi polling.

faster-whisper (CTranslate2) allocates outside PyTorch, so torch.cuda.max_memory_allocated would
miss it. Polling the device-wide figure covers both, but it also includes the CUDA context and any
other process on the GPU, so report it as "device memory used", not "model memory".
"""

import shutil
import subprocess
import threading
import time
from types import TracebackType
from typing import Self


def gpu_name() -> str | None:
    return _query("name")


def _query(field: str) -> str | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    out = subprocess.run(
        [exe, f"--query-gpu={field}", "--format=csv,noheader,nounits", "-i", "0"],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip() or None if out.returncode == 0 else None


def used_mib() -> float | None:
    value = _query("memory.used")
    try:
        return float(value) if value else None
    except ValueError:
        return None


class GpuMemorySampler:
    """Context manager that records peak device memory (MiB) while the block runs."""

    def __init__(self, poll_s: float = 0.25):
        self.poll_s = poll_s
        self.peak_mib: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._record()
            time.sleep(self.poll_s)

    def _record(self) -> None:
        value = used_mib()
        if value is not None and (self.peak_mib is None or value > self.peak_mib):
            self.peak_mib = value

    def __enter__(self) -> Self:
        self._record()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        self._record()

    @property
    def peak_gib(self) -> float | None:
        return None if self.peak_mib is None else self.peak_mib / 1024
