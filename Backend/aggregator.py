"""
aggregator.py
-------------
Aggregates cleaned per-cell data into link-level summaries and heatmap
data for the frontend. Outputs JSON files that the frontend reads directly
(no server needed — just static JSON served from data/).

Run:
    python aggregator.py
"""

import os
import csv
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CLEAN_DIR = os.path.join(os.path.dirname(__file__), "data", "cleaned")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
NUM_CELLS = 24

# Number of slots to include in the heatmap (first N for performance)
HEATMAP_SLOT_LIMIT = 2000


def load_loss_flags(cell: int) -> dict[int, int]:
    path = os.path.join(CLEAN_DIR, f"pkt_stats_cell{cell}.csv")
    if not os.path.isfile(path):
        return {}
    result = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            result[int(row["slot"])] = int(row["loss_flag"])
    return result


def load_slot_gbps(cell: int) -> dict[int, float]:
    path = os.path.join(CLEAN_DIR, f"throughput_slot_cell{cell}.csv")
    if not os.path.isfile(path):
        return {}
    result = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            result[int(row["slot"])] = float(row["gbps"])
    return result


def build_heatmap_data(loss_map: dict[int, dict[int, int]]) -> dict:
    """
    Build slot-level heatmap: for each slot, each cell gets value:
      0 = no traffic
      1 = traffic, no loss
      2 = traffic with loss
    """
    all_slots: set[int] = set()
    throughput_map: dict[int, dict[int, float]] = {}
    for cell in range(1, NUM_CELLS + 1):
        gbps = load_slot_gbps(cell)
        throughput_map[cell] = gbps
        all_slots |= set(gbps.keys())

    sorted_slots = sorted(all_slots)[:HEATMAP_SLOT_LIMIT]

    rows = []
    for slot in sorted_slots:
        row = {"slot": slot}
        for cell in range(1, NUM_CELLS + 1):
            has_traffic = throughput_map[cell].get(slot, 0.0) > 0
            has_loss = loss_map[cell].get(slot, 0) == 1
            if not has_traffic:
                row[f"cell{cell}"] = 0
            elif has_loss:
                row[f"cell{cell}"] = 2
            else:
                row[f"cell{cell}"] = 1
        rows.append(row)

    return rows


def build_cell_stats() -> dict:
    """Per-cell summary statistics."""
    stats = {}
    for cell in range(1, NUM_CELLS + 1):
        gbps_map = load_slot_gbps(cell)
        nonzero = [v for v in gbps_map.values() if v > 0]
        avg = sum(nonzero) / len(nonzero) if nonzero else 0.0
        peak = max(nonzero) if nonzero else 0.0
        stats[cell] = {
            "avg_gbps": round(avg, 4),
            "peak_gbps": round(peak, 4),
            "active_slots": len(nonzero),
            "total_slots": len(gbps_map),
        }
    return stats


def run_aggregator():
    # Load loss flags for all cells
    loss_map: dict[int, dict[int, int]] = {}
    for cell in range(1, NUM_CELLS + 1):
        loss_map[cell] = load_loss_flags(cell)

    logging.info("Building heatmap data…")
    heatmap = build_heatmap_data(loss_map)
    heatmap_path = os.path.join(DATA_DIR, "heatmap_data.json")
    with open(heatmap_path, "w") as f:
        json.dump(heatmap, f)
    logging.info(f"  Heatmap: {len(heatmap)} slots → {heatmap_path}")

    logging.info("Building per-cell stats…")
    cell_stats = build_cell_stats()
    stats_path = os.path.join(DATA_DIR, "cell_stats.json")
    with open(stats_path, "w") as f:
        json.dump(cell_stats, f, indent=2)
    logging.info(f"  Cell stats → {stats_path}")

    logging.info("Done.")


if __name__ == "__main__":
    run_aggregator()
