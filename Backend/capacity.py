"""
capacity.py  —  Link capacity estimation
Uses cleaned throughput_slot_cellN.csv (real or estimated from pkt-stats).
"""

import os, csv, json, logging, math

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
CLEAN_DIR       = os.path.join(BASE_DIR, "data", "cleaned")
TOPO_PATH       = os.path.join(BASE_DIR, "data", "topology_result.json")
OUT_DIR         = os.path.join(BASE_DIR, "data")

SLOT_DURATION_S = 500e-6
BUFFER_TIME_S   = 4 * (SLOT_DURATION_S / 14)   # 4 symbols = ~142.86 µs
MAX_LOSS_FRAC   = 0.01


def load_slot_gbps(cell):
    path = os.path.join(CLEAN_DIR, f"throughput_slot_cell{cell}.csv")
    if not os.path.isfile(path):
        return {}
    result = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                result[int(row["slot"])] = float(row["gbps"])
            except (ValueError, KeyError):
                pass
    return result


def aggregate_link_gbps(cells):
    combined = {}
    for cell in cells:
        for slot, gbps in load_slot_gbps(cell).items():
            combined[slot] = combined.get(slot, 0.0) + gbps
    return combined


def capacity_no_buffer(slot_gbps):
    nonzero = sorted(v for v in slot_gbps.values() if v > 0)
    if not nonzero: return 0.0
    idx = max(0, math.ceil(0.99 * len(nonzero)) - 1)
    return nonzero[min(idx, len(nonzero) - 1)]


def capacity_with_buffer(slot_gbps):
    nonzero_slots = sorted((s, v) for s, v in slot_gbps.items() if v > 0)
    if not nonzero_slots: return 0.0
    total = len(nonzero_slots)
    max_drops = math.floor(MAX_LOSS_FRAC * total)

    def drops_at(C_gbps):
        C_bps = C_gbps * 1e9
        buf_bits = BUFFER_TIME_S * C_bps
        buffered = 0.0; drops = 0
        for _, gbps in nonzero_slots:
            arriving = gbps * 1e9 * SLOT_DURATION_S
            service  = C_bps * SLOT_DURATION_S
            excess   = arriving - service
            buffered = max(0.0, buffered + excess)
            if buffered > buf_bits:
                drops += 1
                buffered = buf_bits
        return drops

    for C in [x * 0.5 for x in range(2, 401)]:
        if drops_at(C) <= max_drops:
            return C
    return 200.0


def run_capacity():
    if not os.path.isfile(TOPO_PATH):
        raise FileNotFoundError("topology_result.json not found — run topology step first")

    with open(TOPO_PATH) as f:
        topo = json.load(f)

    link_assignment = topo["link_assignment"]
    results = {}
    graph_data = {}

    for link_name, cells in link_assignment.items():
        logging.info(f"\n{link_name}: cells {cells}")
        slot_gbps = aggregate_link_gbps(cells)

        if not slot_gbps:
            logging.warning(f"  No throughput data for {link_name}")
            results[link_name] = {
                "cells": cells, "average_gbps": 0.0, "peak_gbps": 0.0,
                "required_capacity_no_buffer_gbps": 0.0,
                "required_capacity_with_buffer_gbps": 0.0,
            }
            graph_data[link_name] = []
            continue

        avg  = sum(slot_gbps.values()) / len(slot_gbps)
        peak = max(slot_gbps.values())
        nb   = capacity_no_buffer(slot_gbps)
        wb   = capacity_with_buffer(slot_gbps)

        logging.info(f"  Slots: {len(slot_gbps)}  Avg: {avg:.3f} Gbps  Peak: {peak:.3f} Gbps")
        logging.info(f"  Cap (no buf): {nb:.2f} Gbps  Cap (w/ buf): {wb:.2f} Gbps")

        results[link_name] = {
            "cells": cells,
            "average_gbps": round(avg, 4),
            "peak_gbps": round(peak, 4),
            "required_capacity_no_buffer_gbps": round(nb, 4),
            "required_capacity_with_buffer_gbps": round(wb, 4),
        }

        graph_data[link_name] = [
            {"slot": s, "time_s": round(s * SLOT_DURATION_S, 6), "gbps": round(g, 6)}
            for s, g in sorted(slot_gbps.items())
        ]

    with open(os.path.join(OUT_DIR, "capacity_result.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(OUT_DIR, "graph_data.json"), "w") as f:
        json.dump(graph_data, f)

    logging.info("\nCapacity results saved.")
    return results


if __name__ == "__main__":
    run_capacity()