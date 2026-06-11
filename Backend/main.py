"""
main.py
-------
Master runner. Executes the full pipeline in order:
  1. data_cleaner   – parse .dat files → cleaned CSVs
  2. topology       – correlate loss events → link assignment JSON
  3. capacity       – estimate link capacities → capacity + graph JSON
  4. aggregator     – build heatmap + cell stats JSON for the frontend

Usage:
    python main.py [--step STEP]

    --step   Optional. Run only one step: clean | topology | capacity | aggregate
             Default: run all steps in order.
"""

import argparse
import logging
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)

STEPS = ["clean", "topology", "capacity", "aggregate"]


def run_clean():
    from data_cleaner import clean_all
    logging.info("═══ Step 1 / 4 : Data Cleaning ═══")
    clean_all()


def run_topology():
    from topology import run_topology
    logging.info("═══ Step 2 / 4 : Topology Identification ═══")
    run_topology()


def run_capacity():
    from capacity import run_capacity
    logging.info("═══ Step 3 / 4 : Link Capacity Estimation ═══")
    run_capacity()


def run_aggregate():
    from aggregator import run_aggregator
    logging.info("═══ Step 4 / 4 : Aggregation for Frontend ═══")
    run_aggregator()


def main():
    parser = argparse.ArgumentParser(description="Fronthaul network optimization pipeline")
    parser.add_argument(
        "--step",
        choices=STEPS,
        default=None,
        help="Run only one step (default: run all steps)",
    )
    args = parser.parse_args()

    # Change working directory to backend/ so relative imports work
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if args.step is None or args.step == "clean":
        run_clean()
    if args.step is None or args.step == "topology":
        run_topology()
    if args.step is None or args.step == "capacity":
        run_capacity()
    if args.step is None or args.step == "aggregate":
        run_aggregate()

    logging.info("Pipeline complete. Frontend data is ready in backend/data/")


if __name__ == "__main__":
    main()
