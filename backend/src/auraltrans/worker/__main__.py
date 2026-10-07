"""`python -m auraltrans.worker`: run the background worker."""

import argparse
import logging

from auraltrans.pipeline.models import LoadedModels
from auraltrans.storage import get_storage
from auraltrans.worker.runner import run_forever


def main() -> None:
    parser = argparse.ArgumentParser(prog="auraltrans-worker")
    parser.add_argument("--lazy", action="store_true", help="load models on the first job instead of at start")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    models = LoadedModels()
    if not args.lazy:
        logging.getLogger("auraltrans.worker").info("loading models (once)...")
        models.warm_up()
    run_forever(get_storage(), models)


if __name__ == "__main__":
    main()
