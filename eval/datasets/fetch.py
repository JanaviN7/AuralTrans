"""Show the exact download size, and only download with --yes.

    python eval/datasets/fetch.py            # prints sizes, downloads nothing
    python eval/datasets/fetch.py --yes      # downloads the subsets into EVAL_DATA_DIR
"""

import argparse

from auraltrans.config import settings
from auraltrans.evaluation import ami, librispeech


def _fmt(n: int) -> str:
    return f"{n / 1e6:,.1f} MB"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="actually download")
    parser.add_argument("--only", choices=["ami", "librispeech"])
    args = parser.parse_args()
    data_dir = settings.eval_data_dir

    plans: dict[str, dict[str, int]] = {}
    if args.only in (None, "ami"):
        plans["AMI (10 meetings, Mix-Headset)"] = ami.plan_download(ami.TEST_SUBSET)
    if args.only in (None, "librispeech"):
        plans["LibriSpeech test-clean (200 utterances)"] = librispeech.plan(settings.hf_token)

    grand = 0
    for name, sizes in plans.items():
        total = sum(sizes.values())
        grand += total
        print(f"{name}: {_fmt(total)}")
        for k, v in sizes.items():
            print(f"    {k}: {_fmt(v)}")
    print(f"TOTAL download: {_fmt(grand)}  ->  {data_dir}")

    if not args.yes:
        print("Dry run only. Re-run with --yes to download.")
        return
    if "AMI (10 meetings, Mix-Headset)" in plans:
        ami.fetch(data_dir, ami.TEST_SUBSET)
    if "LibriSpeech test-clean (200 utterances)" in plans:
        librispeech.fetch(data_dir, settings.hf_token)
    print("done")


if __name__ == "__main__":
    main()
