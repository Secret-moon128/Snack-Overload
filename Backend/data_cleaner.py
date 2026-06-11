"""
data_cleaner.py
---------------
Reads raw .dat files (throughput and pkt-stats) from the data/ folder,
cleans them, and outputs cleaned CSV files to data/cleaned/.

File naming conventions (from the hackathon readme):
  throughput: throughput-cell-<N>.dat
  packet stats: pkt-stats-cell-<N>.dat

Run:
    python data_cleaner.py
"""

import os
import re
import csv
import math
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

RAW_DIR = os.path.join(os.path.dirname(__file__), "data")
CLEAN_DIR = os.path.join(RAW_DIR, "cleaned")
NUM_CELLS = 24


def ensure_dirs():
    os.makedirs(CLEAN_DIR, exist_ok=True)


# ── Throughput file parser ──────────────────────────────────────────────────
# Expected columns: symbol_index  bytes_sent
# 1 slot = 14 symbols = 500 µs  →  symbol duration = 500/14 µs
SYMBOL_DURATION_US = 500 / 14  # ~35.71 µs
SYMBOLS_PER_SLOT = 14


def parse_throughput(filepath: str) -> list[dict]:
    """
    Parse a throughput-cell-N.dat file.
    Returns a list of dicts with keys: symbol, bytes_sent, slot, time_us
    """
    records = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"[\s,;]+", line)
            if len(parts) < 2:
                continue
            try:
                symbol = int(parts[0])
                bytes_sent = int(parts[1])
            except ValueError:
                continue
            slot = symbol // SYMBOLS_PER_SLOT
            time_us = symbol * SYMBOL_DURATION_US
            records.append(
                {
                    "symbol": symbol,
                    "bytes_sent": bytes_sent,
                    "slot": slot,
                    "time_us": round(time_us, 3),
                }
            )
    return records


def aggregate_throughput_to_slots(records: list[dict]) -> list[dict]:
    """
    Sum bytes_sent per slot, compute Gbps for that slot.
    slot duration = 500 µs = 500e-6 s
    """
    SLOT_DURATION_S = 500e-6
    slot_map: dict[int, int] = {}
    for r in records:
        slot_map[r["slot"]] = slot_map.get(r["slot"], 0) + r["bytes_sent"]

    result = []
    for slot, total_bytes in sorted(slot_map.items()):
        bits = total_bytes * 8
        gbps = (bits / SLOT_DURATION_S) / 1e9
        result.append(
            {
                "slot": slot,
                "bytes_sent": total_bytes,
                "time_s": round(slot * SLOT_DURATION_S, 6),
                "gbps": round(gbps, 6),
            }
        )
    return result


# ── Packet stats file parser ────────────────────────────────────────────────
# Expected columns: slot  pkts_sent  pkts_received  pkts_lost
# (column names may vary; we detect by header or fall back to positional)

def parse_pkt_stats(filepath: str) -> list[dict]:
    """
    Parse a pkt-stats-cell-N.dat file.
    Returns list of dicts: slot, pkts_sent, pkts_received, pkts_lost, loss_flag
    loss_flag = 1 if pkts_lost > 0
    """
    records = []
    header_detected = False
    col_map: dict[str, int] = {}

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Header detection
            if line.startswith("#") or (not header_detected and not line[0].isdigit()):
                clean = line.lstrip("#").strip().lower()
                parts = re.split(r"[\s,;]+", clean)
                for i, p in enumerate(parts):
                    if "slot" in p:
                        col_map["slot"] = i
                    elif "sent" in p and "pkt" in p:
                        col_map["pkts_sent"] = i
                    elif "recv" in p or "received" in p:
                        col_map["pkts_received"] = i
                    elif "lost" in p or "drop" in p:
                        col_map["pkts_lost"] = i
                header_detected = True
                continue

            parts = re.split(r"[\s,;]+", line)
            try:
                if col_map:
                    slot = int(parts[col_map.get("slot", 0)])
                    pkts_sent = int(parts[col_map.get("pkts_sent", 1)])
                    pkts_recv = int(parts[col_map.get("pkts_received", 2)])
                    pkts_lost = int(parts[col_map.get("pkts_lost", 3)])
                else:
                    slot = int(parts[0])
                    pkts_sent = int(parts[1])
                    pkts_recv = int(parts[2])
                    pkts_lost = int(parts[3])
            except (ValueError, IndexError):
                continue

            loss_flag = 1 if pkts_lost > 0 else 0
            records.append(
                {
                    "slot": slot,
                    "pkts_sent": pkts_sent,
                    "pkts_received": pkts_recv,
                    "pkts_lost": pkts_lost,
                    "loss_flag": loss_flag,
                }
            )
    return records


# ── Write CSV helpers ────────────────────────────────────────────────────────

def write_csv(filepath: str, rows: list[dict], fieldnames: list[str]):
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logging.info(f"  Wrote {len(rows)} rows → {os.path.relpath(filepath)}")


# ── Main ─────────────────────────────────────────────────────────────────────

def clean_all():
    ensure_dirs()

    for cell in range(1, NUM_CELLS + 1):
        logging.info(f"Processing cell {cell}…")

        # ── Throughput
        tp_path = os.path.join(RAW_DIR, f"throughput-cell-{cell}.dat")
        if os.path.isfile(tp_path):
            raw = parse_throughput(tp_path)
            sym_out = os.path.join(CLEAN_DIR, f"throughput_symbol_cell{cell}.csv")
            write_csv(
                sym_out,
                raw,
                ["symbol", "bytes_sent", "slot", "time_us"],
            )
            slot_rows = aggregate_throughput_to_slots(raw)
            slot_out = os.path.join(CLEAN_DIR, f"throughput_slot_cell{cell}.csv")
            write_csv(slot_out, slot_rows, ["slot", "bytes_sent", "time_s", "gbps"])
        else:
            logging.warning(f"  throughput file not found: {tp_path}")

        # ── Packet stats
        pkt_path = os.path.join(RAW_DIR, f"pkt-stats-cell-{cell}.dat")
        if os.path.isfile(pkt_path):
            pkt_rows = parse_pkt_stats(pkt_path)
            pkt_out = os.path.join(CLEAN_DIR, f"pkt_stats_cell{cell}.csv")
            write_csv(
                pkt_out,
                pkt_rows,
                ["slot", "pkts_sent", "pkts_received", "pkts_lost", "loss_flag"],
            )
        else:
            logging.warning(f"  pkt-stats file not found: {pkt_path}")

    logging.info("Done. Cleaned files are in data/cleaned/")


if __name__ == "__main__":
    clean_all()
