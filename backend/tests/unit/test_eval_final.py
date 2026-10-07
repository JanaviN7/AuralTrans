import subprocess
import sys
from pathlib import Path

import pytest

from auraltrans.evaluation import gpu
from auraltrans.evaluation.report import require_final, software_line, write_report

REPO = Path(__file__).resolve().parents[3]


def test_require_final_passes_with_no_problems_and_lists_all_problems() -> None:
    require_final([])
    with pytest.raises(SystemExit) as exc:
        require_final(["subset run", "device is cpu"])
    message = str(exc.value)
    assert "--final refused" in message and "subset run" in message and "device is cpu" in message


def test_reports_are_preliminary_unless_final(tmp_path: Path) -> None:
    prelim = write_report(tmp_path, "x", "Title", ["a"], [[1]], ["note"])
    assert prelim.name.endswith("_PRELIMINARY.md")
    text = prelim.read_text(encoding="utf-8")
    assert text.startswith("# PRELIMINARY: Title") and "not for publication" in text
    assert (tmp_path / prelim.name.replace(".md", ".csv")).exists()

    final = write_report(tmp_path, "x", "Title", ["a"], [[1]], ["note"], final=True)
    assert "PRELIMINARY" not in final.name and "PRELIMINARY" not in final.read_text(encoding="utf-8")


def test_extra_banners_are_shown(tmp_path: Path) -> None:
    md = write_report(tmp_path, "y", "T", ["a"], [[1]], [], banners=["NOT PUBLISHABLE: reason"])
    assert "NOT PUBLISHABLE: reason" in md.read_text(encoding="utf-8")


def test_software_line_names_commit_and_packages() -> None:
    line = software_line()
    assert line.startswith("commit ") and "jiwer" in line


def test_software_line_survives_missing_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AURALTRANS_COMMIT", raising=False)

    def no_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)
    assert software_line().startswith("commit unknown")


def test_software_line_uses_commit_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AURALTRANS_COMMIT", "abc1234")
    assert software_line().startswith("commit abc1234")


def test_gpu_sampler_keeps_the_peak(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter([100.0, 500.0, 300.0] + [200.0] * 1000)
    monkeypatch.setattr(gpu, "used_mib", lambda: next(values))
    with gpu.GpuMemorySampler(poll_s=0.001) as sampler:
        import time

        time.sleep(0.05)
    assert sampler.peak_mib == 500.0
    assert sampler.peak_gib == pytest.approx(500.0 / 1024)


def test_gpu_sampler_without_nvidia_smi_reports_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpu, "used_mib", lambda: None)
    with gpu.GpuMemorySampler(poll_s=0.001) as sampler:
        pass
    assert sampler.peak_gib is None


@pytest.mark.parametrize(
    "args",
    [
        ["eval/run_asr.py", "--dataset", "ami", "--final"],  # cpu device
        ["eval/run_asr.py", "--dataset", "ami", "--device", "cuda", "--limit", "1", "--final"],
        ["eval/run_asr.py", "--dataset", "ami", "--device", "cuda", "--no-vad", "--final"],
        ["eval/run_diarization.py", "--device", "cuda", "--meetings", "IS1009a", "--final"],
        ["eval/run_diarization.py", "--final"],  # cpu device
        ["eval/run_speed.py", "--files", "x.wav", "--final"],
    ],
)
def test_final_flag_is_refused_for_preliminary_conditions(args: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, *args], cwd=REPO, capture_output=True, text=True, check=False, timeout=180
    )
    assert result.returncode != 0
    assert "--final refused" in result.stderr + result.stdout
