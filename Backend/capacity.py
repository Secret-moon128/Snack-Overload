"""
capacity.py
-----------
Estimates the required Ethernet link capacity for Links 1, 2, and 3.

Two cases:
  A) Without buffer  – link must handle the peak slot data rate without any
                       buffering. Capacity = 99th-percentile of per-slot
                       aggregate Gbps (1% packet loss allowed).
  B) With buffer     – the leaf switch has a buffer of 4 symbols (143 µs).
                       Excess traffic that fits in the buffer is absorbed;
                       capacity is reduced accordingly.

Formula (with buffer):
  Buffer size in bits = buffer_time_s × link_rate_Gbps × 1e9
  We iterate candidate link rates and find the minimum that keeps packet
  loss ≤ 1% of traffic-carrying slots.

Run standalone:
    python capacity.py
"""

import os
import csv
import json
import logging
import math

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CLEAN_DIR = os.path.join(os.path.dirname(__file__), "data", "cleaned")
TOPO_PATH = os.path.join(os.path.dirname(__file__), "data", "topology_result.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")

NUM_CELLS = 24
SLOT_DURATION_S = 500e-6        # 500 µs
BUFFER_SYMBOLS = 4
SYMBOL_DURATION_S = SLOT_DURATION_S / 14   # ~35.71 µs
BUFFER_TIME_S = BUFFER_SYMBOLS * SYMBOL_DURATION_S  # ~142.86 µs
MAX_LOSS_FRACTION = 0.01         # 1% permitted packet loss per cell


def load_slot_gbps(cell: int) -> dict[int, float]:
    """Return {slot: gbps} for a cell from the cleaned throughput CSV."""
    path = os.path.join(CLEAN_DIR, f"throughput_slot_cell{cell}.csv")
    if not os.path.isfile(path):
        return {}
    result = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            result[int(row["slot"])] = float(row["gbps"])
    return result


def aggregate_link_gbps(cells: list[int]) -> dict[int, float]:
    """Sum per-slot Gbps across all cells on a link."""
    combined: dict[int, float] = {}
    for cell in cells:
        for slot, gbps in load_slot_gbps(cell).items():
            combined[slot] = combined.get(slot, 0.0) + gbps
    return combined


def capacity_no_buffer(slot_gbps: dict[int, float]) -> float:
    """
    Minimum link rate so that at most 1% of traffic-carrying slots see
    congestion (i.e., instantaneous rate > link rate).
    → 99th-percentile of nonzero slot rates.
    """
    nonzero = sorted(v for v in slot_gbps.values() if v > 0)
    if not nonzero:
        return 0.0
    idx = math.ceil(0.99 * len(nonzero)) - 1
    return nonzero[min(idx, len(nonzero) - 1)]


def capacity_with_buffer(slot_gbps: dict[int, float]) -> float:
    """
    Binary search for the minimum link rate C (Gbps) such that:
      - Excess bits = max(0, (slot_gbps[s] - C) * SLOT_DURATION_S * 1e9)
        are absorbed by the buffer.
      - A slot causes a drop if cumulative buffer overflow exceeds
        BUFFER_TIME_S * C * 1e9 bits.
      - Fraction of traffic-carrying slots with drops ≤ 1%.

    We do a linear sweep over candidate rates from 1 to 200 Gbps in steps.
    """
    nonzero_slots = sorted((s, v) for s, v in slot_gbps.items() if v > 0)
    if not nonzero_slots:
        return 0.0

    total_traffic_slots = len(nonzero_slots)
    max_allowed_drops = math.floor(MAX_LOSS_FRACTION * total_traffic_slots)

    def drops_at_rate(C_gbps: float) -> int:
        C_bps = C_gbps * 1e9
        buffer_bits = BUFFER_TIME_S * C_bps
        buffered = 0.0
        drop_count = 0
        for _, gbps in nonzero_slots:
            arriving_bits = gbps * 1e9 * SLOT_DURATION_S
            serviceable = C_bps * SLOT_DURATION_S
            excess = arriving_bits - serviceable
            if excess > 0:
                buffered += excess
            else:
                buffered = max(0.0, buffered + excess)
            if buffered > buffer_bits:
                drop_count += 1
                buffered = buffer_bits  # buffer saturates, drops the overflow
        return drop_count

    # Sweep from 1 to 200 Gbps in 0.5 Gbps steps
    for C in [x * 0.5 for x in range(2, 401)]:
        if drops_at_rate(C) <= max_allowed_drops:
            return C
    return 200.0  # upper bound


def per_slot_series(slot_gbps: dict[int, float]) -> list[dict]:
    """Return sorted list of {slot, time_s, gbps} for graphing."""
    return [
        {"slot": s, "time_s": round(s * SLOT_DURATION_S, 6), "gbps": round(g, 6)}
        for s, g in sorted(slot_gbps.items())
    ]


def run_capacity() -> dict:
    # Load topology
    if not os.path.isfile(TOPO_PATH):
        raise FileNotFoundError(
            f"topology_result.json not found at {TOPO_PATH}. "
            "Run topology.py first."
        )
    with open(TOPO_PATH) as f:
        topo = json.load(f)

    link_assignment: dict[str, list[int]] = topo["link_assignment"]

    results = {}
    graph_data = {}

    for link_name, cells in link_assignment.items():
        logging.info(f"\n{link_name}: cells {cells}")
        slot_gbps = aggregate_link_gbps(cells)

        no_buf = capacity_no_buffer(slot_gbps)
        with_buf = capacity_with_buffer(slot_gbps)

        avg = (sum(slot_gbps.values()) / len(slot_gbps)) if slot_gbps else 0.0
        peak = max(slot_gbps.values()) if slot_gbps else 0.0

        logging.info(f"  Average data rate : {avg:.3f} Gbps")
        logging.info(f"  Peak data rate    : {peak:.3f} Gbps")
        logging.info(f"  Required capacity (no buffer)  : {no_buf:.2f} Gbps")
        logging.info(f"  Required capacity (with buffer): {with_buf:.2f} Gbps")

        results[link_name] = {
            "cells": cells,
            "average_gbps": round(avg, 4),
            "peak_gbps": round(peak, 4),
            "required_capacity_no_buffer_gbps": round(no_buf, 4),
            "required_capacity_with_buffer_gbps": round(with_buf, 4),
        }
        graph_data[link_name] = per_slot_series(slot_gbps)

    out_cap = os.path.join(OUT_DIR, "capacity_result.json")
    with open(out_cap, "w") as f:
        json.dump(results, f, indent=2)
    logging.info(f"\nCapacity results saved → {out_cap}")

    out_graph = os.path.join(OUT_DIR, "graph_data.json")
    with open(out_graph, "w") as f:
        json.dump(graph_data, f, indent=2)
    logging.info(f"Graph data saved → {out_graph}")

    return results


if __name__ == "__main__":
    run_capacity()
