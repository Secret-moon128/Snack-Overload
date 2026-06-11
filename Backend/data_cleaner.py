"""
data_cleaner.py
---------------
Reads raw .dat files from data/ folder and outputs cleaned CSVs to data/cleaned/.

Handles multiple possible dat file formats:
  - Space/tab/comma separated
  - With or without headers
  - Comments starting with # or %
  - Possible formats: symbol bytes | slot pkts_sent pkts_recv pkts_lost
"""

import os, re, csv, logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

RAW_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CLEAN_DIR = os.path.join(RAW_DIR, "cleaned")
NUM_CELLS = 24

SYMBOL_DURATION_US = 500 / 14   # 35.714 µs
SYMBOLS_PER_SLOT   = 14
SLOT_DURATION_S    = 500e-6     # 500 µs


def ensure_dirs():
    os.makedirs(CLEAN_DIR, exist_ok=True)


def split_line(line):
    """Split on any whitespace or comma/semicolon."""
    return re.split(r"[\s,;]+", line.strip())


def is_comment(line):
    s = line.strip()
    return not s or s[0] in ("#", "%", "!")


def is_header(line):
    """True if line contains letters (column names)."""
    return bool(re.search(r"[A-Za-z]", line.strip()))


def safe_int(v):
    try:
        return int(float(v))
    except Exception:
        return None


def safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


# ── Throughput parser ────────────────────────────────────────────────────────
def parse_throughput(path):
    """
    Expected: two numeric columns — symbol_index  bytes_sent
    Also handles: time_us  bytes  or  slot  bytes (auto-detected by magnitude).
    Returns list of dicts: symbol, bytes_sent, slot, time_us
    """
    records = []
    with open(path, "r", errors="replace") as f:
        lines = f.readlines()

    # Find first data line to detect column count & scale
    first_vals = None
    for line in lines:
        if is_comment(line) or is_header(line):
            continue
        parts = split_line(line)
        if len(parts) >= 2:
            v0, v1 = safe_float(parts[0]), safe_float(parts[1])
            if v0 is not None and v1 is not None:
                first_vals = (v0, v1)
                break

    if first_vals is None:
        logging.warning(f"  No data found in {path}")
        return []

    # Heuristic: if col0 is very large (>1e6) it might be microseconds timestamp
    # If col0 < 100000 treat as symbol index directly
    col0_is_time_us = first_vals[0] > 1_000_000

    for line in lines:
        if is_comment(line) or is_header(line):
            continue
        parts = split_line(line)
        if len(parts) < 2:
            continue
        v0 = safe_float(parts[0])
        v1 = safe_float(parts[1])
        if v0 is None or v1 is None:
            continue

        if col0_is_time_us:
            time_us = v0
            symbol  = int(round(time_us / SYMBOL_DURATION_US))
        else:
            symbol  = int(v0)
            time_us = symbol * SYMBOL_DURATION_US

        slot = symbol // SYMBOLS_PER_SLOT
        records.append({
            "symbol":     symbol,
            "bytes_sent": int(v1),
            "slot":       slot,
            "time_us":    round(time_us, 3),
        })

    return records


def aggregate_to_slots(records):
    slot_map = {}
    for r in records:
        slot_map[r["slot"]] = slot_map.get(r["slot"], 0) + r["bytes_sent"]
    result = []
    for slot, total_bytes in sorted(slot_map.items()):
        bits = total_bytes * 8
        gbps = (bits / SLOT_DURATION_S) / 1e9
        result.append({
            "slot":       slot,
            "bytes_sent": total_bytes,
            "time_s":     round(slot * SLOT_DURATION_S, 6),
            "gbps":       round(gbps, 6),
        })
    return result


# ── Pkt-stats parser ─────────────────────────────────────────────────────────
def parse_pkt_stats(path):
    """
    Expected columns: slot  pkts_sent  pkts_received  pkts_lost
    Column detection: header line or positional fallback.
    Also handles 5-column files with extra fields.
    """
    records = []
    col = {"slot": 0, "sent": 1, "recv": 2, "lost": 3}

    with open(path, "r", errors="replace") as f:
        lines = f.readlines()

    # Try to detect header
    for line in lines:
        if is_comment(line):
            continue
        if is_header(line):
            parts = [p.lower() for p in split_line(line.lstrip("#%! "))]
            for i, p in enumerate(parts):
                if "slot" in p or "time" in p:          col["slot"] = i
                elif "sent" in p:                        col["sent"] = i
                elif "recv" in p or "received" in p:     col["recv"] = i
                elif "lost" in p or "drop" in p:         col["lost"] = i
            break

    for line in lines:
        if is_comment(line) or is_header(line):
            continue
        parts = split_line(line)
        if len(parts) < 4:
            continue

        slot      = safe_int(parts[col["slot"]])
        pkts_sent = safe_int(parts[col["sent"]])
        pkts_recv = safe_int(parts[col["recv"]])
        pkts_lost = safe_int(parts[col["lost"]])

        if any(v is None for v in [slot, pkts_sent, pkts_recv, pkts_lost]):
            continue

        # Sometimes lost is computed, sometimes it's in the file — recompute to be safe
        computed_lost = max(0, pkts_sent - pkts_recv)
        actual_lost   = pkts_lost if pkts_lost >= 0 else computed_lost

        records.append({
            "slot":          slot,
            "pkts_sent":     pkts_sent,
            "pkts_received": pkts_recv,
            "pkts_lost":     actual_lost,
            "loss_flag":     1 if actual_lost > 0 else 0,
        })

    return records


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    logging.info(f"    → {os.path.relpath(path)}  ({len(rows)} rows)")


def clean_all():
    ensure_dirs()
    found_tp  = 0
    found_pkt = 0

    for cell in range(1, NUM_CELLS + 1):
        logging.info(f"Cell {cell:2d}:")

        # ── throughput
        for name in [f"throughput-cell-{cell}.dat", f"throughput_cell_{cell}.dat",
                     f"throughput-cell{cell}.dat",   f"cell{cell}_throughput.dat"]:
            tp_path = os.path.join(RAW_DIR, name)
            if os.path.isfile(tp_path):
                raw = parse_throughput(tp_path)
                if raw:
                    write_csv(os.path.join(CLEAN_DIR, f"throughput_symbol_cell{cell}.csv"),
                              raw, ["symbol","bytes_sent","slot","time_us"])
                    slots = aggregate_to_slots(raw)
                    write_csv(os.path.join(CLEAN_DIR, f"throughput_slot_cell{cell}.csv"),
                              slots, ["slot","bytes_sent","time_s","gbps"])
                    found_tp += 1
                break
        else:
            logging.warning(f"    throughput file for cell {cell} not found in {RAW_DIR}")

        # ── pkt-stats
        for name in [f"pkt-stats-cell-{cell}.dat", f"pkt_stats_cell_{cell}.dat",
                     f"pkt-stats-cell{cell}.dat",   f"cell{cell}_pkt_stats.dat"]:
            pkt_path = os.path.join(RAW_DIR, name)
            if os.path.isfile(pkt_path):
                rows = parse_pkt_stats(pkt_path)
                if rows:
                    write_csv(os.path.join(CLEAN_DIR, f"pkt_stats_cell{cell}.csv"),
                              rows, ["slot","pkts_sent","pkts_received","pkts_lost","loss_flag"])
                    found_pkt += 1
                break
        else:
            logging.warning(f"    pkt-stats file for cell {cell} not found in {RAW_DIR}")

    logging.info(f"\nDone. Parsed {found_tp} throughput + {found_pkt} pkt-stats files.")
    if found_tp == 0:
        logging.error("No throughput files found! Check that .dat files are in Backend/data/")
    return found_tp, found_pkt


if __name__ == "__main__":
    clean_all()