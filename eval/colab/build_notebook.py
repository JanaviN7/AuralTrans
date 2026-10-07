"""Generate eval/colab/auraltrans_ami_eval.ipynb.

    python eval/colab/build_notebook.py

The notebook is generated so its cells can be reviewed as plain text. It runs the same scripts, on
the same subset, with the same configuration as the Windows CPU pilot.
"""

import json
from pathlib import Path

OUT = Path(__file__).parent / "auraltrans_ami_eval.ipynb"

CELLS: list[tuple[str, str]] = []


def md(text: str) -> None:
    CELLS.append(("markdown", text.strip("\n")))


def code(text: str) -> None:
    CELLS.append(("code", text.strip("\n")))


md("""
# AuralTrans 2.0: AMI evaluation on a Colab GPU

Runs the **same** pipeline, scripts and 10-meeting AMI subset as the Windows CPU pilot, on a GPU,
with `meeteval` for cpWER. Reports land in the same format as the local ones.

| Result | Where from | Status |
|---|---|---|
| Windows CPU pilot (2 meetings, local cpWER fallback) | files named `*_PRELIMINARY` | **Preliminary. Not publishable.** |
| This notebook (all 10 meetings, GPU, `meeteval`) | files **without** `_PRELIMINARY` | **Final**, only if every `--final` check passes |

The scripts refuse to write a final report unless the full subset ran, the device is CUDA, and (for
cpWER) `meeteval` is installed.

**Before you run**
1. Runtime > Change runtime type > **T4 GPU** (any NVIDIA GPU works).
2. Colab **Secrets** (key icon): add `HF_TOKEN` (a read-only Hugging Face token) and switch on
   notebook access. Your account must have accepted the terms of
   `pyannote/speaker-diarization-community-1`. The token is never printed or saved.
3. On your PC, from the repo: `python eval/colab/make_bundle.py`, then put the resulting
   `dist/auraltrans-eval-bundle-<commit>.zip` into Google Drive at `MyDrive/auraltrans/`
   (or upload it when the notebook asks).

**Do not change the configuration to improve numbers.** The config cell pins what the pilot used.
Any deviation is recorded in the run manifest and shown in the final summary.
""")

code("""
# 1. Confirm a GPU is attached
import subprocess
gpu = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
print(gpu.stdout or gpu.stderr)
assert gpu.returncode == 0, "No GPU: Runtime > Change runtime type > T4 GPU, then reconnect."
""")

code("""
# 2. Configuration (pinned to match the Windows CPU pilot)
import datetime as dt
import os
from pathlib import Path

PILOT_CONFIG = dict(asr_model="small", compute_type="int8")   # what the CPU pilot used
ASR_MODEL = "small"          # Whisper size (same as the pilot)
COMPUTE_TYPE = "int8"        # same as the pilot; if CUDA rejects it, see the note under cell 10
RUN_LIBRISPEECH = True       # also re-run the 200-utterance LibriSpeech WER check on the GPU
RESUME_RUN = None            # set to an earlier run id (folder under Drive/runs) to reuse its cached ASR/diarization

# Fixed by the code, recorded for the manifest (not editable here):
FIXED_BY_CODE = dict(
    language="en", vad_filter=True, condition_on_previous_text=False,
    diarization="pyannote/speaker-diarization-community-1, no speaker-count hint",
    subset="AMI test subset, 10 meetings (see eval/README.md)",
    collar="0.0 and 0.25 (+/-0.25 s)", cpwer="meeteval",
)

REPO = Path("/content/auraltrans")
DATA_DIR = Path("/content/auraltrans-data")
DRIVE = Path("/content/drive/MyDrive/auraltrans")
RUN_ID = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
OUT_DIR = DRIVE / "runs" / RUN_ID
os.environ["EVAL_DATA_DIR"] = str(DATA_DIR)

deviations = []
if ASR_MODEL != PILOT_CONFIG["asr_model"]:
    deviations.append(f"asr_model {ASR_MODEL} != pilot {PILOT_CONFIG['asr_model']}")
if COMPUTE_TYPE != PILOT_CONFIG["compute_type"]:
    deviations.append(f"compute_type {COMPUTE_TYPE} != pilot {PILOT_CONFIG['compute_type']}")
print("run id:", RUN_ID)
print("DEVIATIONS FROM PILOT:", deviations or "none")
""")

code("""
# 3. Google Drive (results and checkpoints are saved here, so a disconnect does not lose them)
from google.colab import drive
drive.mount("/content/drive")
OUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
print("results will be saved to", OUT_DIR)
""")

code("""
# 4. Get the code: the bundle built by eval/colab/make_bundle.py
import glob, json, shutil, zipfile

bundles = sorted(glob.glob(str(DRIVE / "auraltrans-eval-bundle-*.zip")), key=os.path.getmtime)
if bundles:
    bundle = bundles[-1]
else:
    from google.colab import files
    print("No bundle found in Drive; upload auraltrans-eval-bundle-<commit>.zip")
    up = files.upload()
    bundle = "/content/" + next(iter(up))
print("using", bundle)

shutil.rmtree(REPO, ignore_errors=True)
with zipfile.ZipFile(bundle) as zf:
    zf.extractall(REPO)
bundle_manifest = json.loads((REPO / "BUNDLE_MANIFEST.json").read_text())
os.environ["AURALTRANS_COMMIT"] = bundle_manifest["commit"]
print("code commit:", bundle_manifest["commit"], "| dirty:", bundle_manifest["dirty"])
if bundle_manifest["dirty"]:
    deviations.append("bundle was built from uncommitted changes")
""")

code("""
# 5. Install (Linux: includes meeteval)
import subprocess, sys

def run(cmd, cwd=REPO):
    print("$", cmd, flush=True)
    p = subprocess.Popen(cmd, shell=True, cwd=str(cwd), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, env=os.environ)
    for line in p.stdout:
        print(line, end="")
    rc = p.wait()
    if rc:
        raise RuntimeError(f"command failed (exit {rc}): {cmd}")

# meeteval ships no wheels and compiles C++ at install time, so a compiler is required.
if shutil.which("g++") is None:
    run("apt-get update -qq && apt-get install -y -qq g++")
run('pip install -q -e "backend[speech,eval]"')
run("pip install -q pytest")   # the dev tools are not part of the extras
run("ffmpeg -version | head -1")
import importlib.metadata as md_
for pkg in ["faster-whisper", "ctranslate2", "pyannote.audio", "pyannote.metrics", "torch", "jiwer", "meeteval"]:
    print(f"{pkg:20s}", md_.version(pkg))
""")

code("""
# 6. Preflight: the unit tests must pass, including the meeteval cross-check (it is skipped without meeteval)
run("python -m pytest -q -rs backend/tests/unit")   # raises if any test fails
from auraltrans.evaluation.metrics import meeteval_available
assert meeteval_available(), "meeteval did not install; final cpWER is impossible"
""")

code("""
# 7. Hugging Face access (token comes from Colab Secrets and is never printed)
from google.colab import userdata
os.environ["HF_TOKEN"] = userdata.get("HF_TOKEN")
from huggingface_hub import hf_hub_download
try:
    hf_hub_download("pyannote/speaker-diarization-community-1", "config.yaml", token=os.environ["HF_TOKEN"])
    print("pyannote community-1 access OK")
except Exception as exc:
    raise SystemExit(f"No access to the gated pyannote model. Accept its terms on Hugging Face "
                     f"with the account that owns this token. ({type(exc).__name__})")
""")

code("""
# 8. Data: the same 10 AMI meetings and 200 LibriSpeech utterances. First a dry run that shows sizes.
run("python eval/datasets/fetch.py")
""")

code("""
run("python eval/datasets/fetch.py --yes")
""")

code("""
# 9. Optional resume: reuse cached ASR/diarization from an earlier run of THIS notebook
def checkpoint():
    # copy caches and reports to Drive so a disconnect does not lose finished stages
    for kind in ("asr", "diarization"):
        src = DATA_DIR / "cache" / kind
        if src.exists():
            shutil.copytree(src, OUT_DIR / "cache" / kind, dirs_exist_ok=True)
    rep = REPO / "eval" / "reports"
    if rep.exists():
        shutil.copytree(rep, OUT_DIR / "reports", dirs_exist_ok=True)
    print("checkpoint saved to", OUT_DIR)

if RESUME_RUN:
    prev = DRIVE / "runs" / RESUME_RUN / "cache"
    shutil.copytree(prev, DATA_DIR / "cache", dirs_exist_ok=True)
    print("restored caches from", prev)
""")

code("""
# 10. ASR WER on the AMI subset (final = full set, GPU)
# If CUDA rejects int8 ("Requested int8 compute type, but the target device does not support it"),
# do not silently change it: set COMPUTE_TYPE = "int8_float16" in cell 2, re-run from cell 2, and
# the deviation will be recorded.
run(f"python eval/run_asr.py --dataset ami --models {ASR_MODEL} --device cuda "
    f"--compute-type {COMPUTE_TYPE} --final")
checkpoint()
""")

code("""
# 11. Diarization: DER and JER, collar 0 and 0.25
run("python eval/run_diarization.py --device cuda --final")
checkpoint()
""")

code("""
# 12. Alignment ablation (a/b/c on identical ASR and diarization output): cpWER with meeteval
run(f"python eval/run_cpwer.py --model {ASR_MODEL} --compute-type {COMPUTE_TYPE} --final")
checkpoint()
""")

code("""
# 13. Stage RTF and peak GPU memory over all 10 meetings
run(f"python eval/run_speed.py --ami-subset --models {ASR_MODEL} --device cuda "
    f"--compute-type {COMPUTE_TYPE} --final")
checkpoint()
""")

code("""
# 14. LibriSpeech 200-utterance WER (tiny and small), as in the preliminary CPU run
if RUN_LIBRISPEECH:
    run(f"python eval/run_asr.py --dataset librispeech --models tiny small --device cuda "
        f"--compute-type {COMPUTE_TYPE} --final")
    checkpoint()
""")

code("""
# 15. Run manifest: ties these results to the code, packages, hardware and configuration
import platform
def smi(field):
    r = subprocess.run(["nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader", "-i", "0"],
                       capture_output=True, text=True)
    return r.stdout.strip()

freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout
(OUT_DIR / "requirements-freeze.txt").write_text(freeze)
manifest = dict(
    run_id=RUN_ID, finished=dt.datetime.now().isoformat(timespec="seconds"),
    commit=bundle_manifest["commit"], bundle_dirty=bundle_manifest["dirty"],
    gpu=smi("name"), gpu_memory_total=smi("memory.total"), driver=smi("driver_version"),
    python=platform.python_version(), platform=platform.platform(),
    asr_model=ASR_MODEL, compute_type=COMPUTE_TYPE, fixed_by_code=FIXED_BY_CODE,
    deviations_from_pilot=deviations,
    reports=sorted(p.name for p in (REPO / "eval" / "reports").glob("*")),
)
(OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
checkpoint()
print(json.dumps(manifest, indent=2))
""")

code("""
# 16. Final reports, and a side-by-side with the PRELIMINARY CPU pilot on the same two meetings
import csv, glob
def latest(pattern):
    hits = sorted(glob.glob(str(REPO / "eval" / "reports" / pattern)))
    return hits[-1] if hits else None

for pat in ["*_asr_wer_ami.md", "*_diarization_der.md", "*_alignment_ablation_cpwer.md", "*_speed_rtf.md"]:
    f = latest(pat)
    print("=" * 100); print(f)
    print(Path(f).read_text() if f else "MISSING")
""")

code("""
import pandas as pd
# Numbers from the Windows CPU pilot (PRELIMINARY; its cpWER used the local fallback and is not publishable).
PILOT = pd.DataFrame([
    dict(meeting="IS1009a", WER=23.1, DER_collar0=23.87, DER_collar025=16.02, JER_collar0=36.67,
         cpWER_a=33.80, cpWER_b=29.79, cpWER_c=28.65, speakers="5/4"),
    dict(meeting="ES2004a", WER=19.6, DER_collar0=19.54, DER_collar025=11.89, JER_collar0=24.33,
         cpWER_a=23.11, cpWER_b=23.56, cpWER_c=22.84, speakers="5/4"),
]).set_index("meeting")

def rows(pattern):
    f = latest(pattern.replace(".md", ".csv"))
    return list(csv.DictReader(open(f))) if f else []

final = {}
for r in rows("*_asr_wer_ami.csv"):
    if r["files"] in PILOT.index:
        final.setdefault(r["files"], {})["WER"] = float(r["WER %"])
for r in rows("*_diarization_der.csv"):
    if r["meeting"] in PILOT.index:
        key = "DER_collar0" if float(r["collar s"]) == 0 else "DER_collar025"
        final.setdefault(r["meeting"], {})[key] = float(r["DER %"])
        if float(r["collar s"]) == 0:
            final[r["meeting"]]["JER_collar0"] = float(r["JER %"])
            final[r["meeting"]]["speakers"] = r["speakers hyp/ref"]
for r in rows("*_alignment_ablation_cpwer.csv"):
    if r["meeting"] in PILOT.index:
        final.setdefault(r["meeting"], {})["cpWER_" + r["variant"][0]] = float(r["cpWER %"])
FINAL = pd.DataFrame(final).T
print("PRELIMINARY Windows CPU pilot (cpWER = local fallback, NOT publishable):")
display(PILOT)
print("FINAL Colab GPU run, same two meetings (cpWER = meeteval):")
display(FINAL)
print("Difference (final - pilot), numeric columns only:")
display((FINAL[PILOT.columns.difference(['speakers'])].astype(float) - PILOT[PILOT.columns.difference(['speakers'])]).round(2))
""")

code("""
# 17. Download everything (also already saved in Drive under OUT_DIR)
shutil.make_archive("/content/auraltrans-results-" + RUN_ID, "zip", OUT_DIR)
from google.colab import files
files.download(f"/content/auraltrans-results-{RUN_ID}.zip")
""")

md("""
**After the run**, copy the final `eval/reports/*.md|csv` files (no `_PRELIMINARY` suffix) into the
repo's `eval/reports/` on your PC, together with `run_manifest.json`. Keep the preliminary CPU reports
separate; do not mix them in any table.
""")


def main() -> None:
    cells = []
    for kind, text in CELLS:
        lines = text.split("\n")
        source = [ln + "\n" for ln in lines[:-1]] + [lines[-1]]
        cell: dict[str, object] = {"cell_type": kind, "metadata": {}, "source": source}
        if kind == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
        cells.append(cell)
    notebook = {
        "cells": cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": [], "gpuType": "T4"},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    OUT.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(cells)} cells)")


if __name__ == "__main__":
    main()
