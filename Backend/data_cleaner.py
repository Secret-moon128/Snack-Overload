"""
data_cleaner.py  v3
-------------------
pkt-stats format confirmed:
  <slot>  <slotStart>  <txPackets>  <rxPackets>  <tooLateRxPackets>
  1.00001  0  0  0  0
  1.00465  0  16  16  0

slot column is a float. The INTEGER part is the slot number (1, 2, 3…).
slotStart (col 1) is a sub-slot timestamp — IGNORE it.

Throughput estimation:
  eCPRI packets in fronthaul are ~9000 bits (1125 bytes) per packet.
  But more precisely: we count bytes per SLOT, not per symbol.
  1 slot = 500 µs.  If txPackets packets of avg size B bytes arrive in a slot:
    Gbps = (txPackets * B * 8) / (500e-6) / 1e9

  The slot float is like 1.00001, 1.00023, 1.00065 — these are
  MULTIPLE ROWS PER SLOT (sub-slot granularity ~35 µs = 1 symbol).
  So we SUM txPackets across all rows where floor(slot_float) == slot_int.
"""

import os, re, csv, logging, glob, math

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
RAW_DIR   = os.path.join(BASE_DIR, "data")
CLEAN_DIR = os.path.join(RAW_DIR, "cleaned")
NUM_CELLS = 24

SLOT_DURATION_S    = 500e-6       # 500 µs
# eCPRI / fronthaul typical: ~1500 byte Ethernet frame for user data
# Using 1500 bytes = conservative upper bound
AVG_PKT_BYTES = 1500


def ensure_dirs():
    os.makedirs(CLEAN_DIR, exist_ok=True)


def is_header(line):
    s = line.strip()
    if not s: return True
    if s[0] in ("#", "%", "!"): return True
    if "<" in s or re.search(r"[A-Za-z]", s): return True
    return False


def safe_int(v):
    try: return int(float(v))
    except: return None

def safe_float(v):
    try: return float(v)
    except: return None


def find_file(patterns):
    for pat in patterns:
        direct = os.path.join(RAW_DIR, pat)
        if os.path.isfile(direct):
            return direct
        matches = glob.glob(os.path.join(RAW_DIR, "**", pat), recursive=True)
        if matches:
            return matches[0]
    return None


def parse_pkt_stats(path):
    """
    Returns list of symbol-level records, then slot-level aggregation.
    Each row is one sub-slot (symbol) measurement.
    slot_int = integer part of slot float column.
    """
    symbol_records = []

    with open(path, "r", errors="replace") as f:
        lines = f.readlines()

    for line in lines:
        if is_header(line):
            continue
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 4:
            continue

        slot_f  = safe_float(parts[0])
        tx      = safe_int(parts[2]) if len(parts) > 2 else None
        rx      = safe_int(parts[3]) if len(parts) > 3 else None
        late    = safe_int(parts[4]) if len(parts) > 4 else 0

        if slot_f is None or tx is None or rx is None:
            continue

        # Integer slot = floor of slot float
        slot_int = int(math.floor(slot_f))
        lost     = max(0, tx - rx)

        symbol_records.append({
            "slot":     slot_int,
            "slot_f":   round(slot_f, 5),
            "tx":       tx,
            "rx":       rx,
            "lost":     lost,
            "late":     late or 0,
        })

    return symbol_records


def aggregate_pkt_to_slots(symbol_records):
    """Aggregate symbol-level rows → per-slot totals."""
    slot_map = {}
    for r in symbol_records:
        s = r["slot"]
        if s not in slot_map:
            slot_map[s] = {"tx": 0, "rx": 0, "lost": 0, "late": 0}
        slot_map[s]["tx"]   += r["tx"]
        slot_map[s]["rx"]   += r["rx"]
        slot_map[s]["lost"] += r["lost"]
        slot_map[s]["late"] += r["late"]

    result = []
    for slot, d in sorted(slot_map.items()):
        lost      = d["lost"]
        late      = d["late"]
        loss_flag = 1 if (lost > 0 or late > 0) else 0
        result.append({
            "slot":          slot,
            "pkts_sent":     d["tx"],
            "pkts_received": d["rx"],
            "pkts_lost":     lost,
            "too_late":      late,
            "loss_flag":     loss_flag,
        })
    return result


def estimate_throughput_from_slots(slot_records):
    """
    Gbps = (pkts_sent * AVG_PKT_BYTES * 8) / SLOT_DURATION_S / 1e9
    Only count slots with actual traffic (pkts_sent > 0).
    """
    result = []
    for r in slot_records:
        tx = r["pkts_sent"]
        if tx == 0:
            continue
        total_bytes = tx * AVG_PKT_BYTES
        gbps = (total_bytes * 8 / SLOT_DURATION_S) / 1e9
        result.append({
            "slot":       r["slot"],
            "bytes_sent": total_bytes,
            "time_s":     round(r["slot"] * SLOT_DURATION_S, 6),
            "gbps":       round(gbps, 6),
        })
    return result


def parse_throughput(path):
    SYMBOL_DUR = 500 / 14  # µs
    records = []
    with open(path, "r", errors="replace") as f:
        lines = f.readlines()
    for line in lines:
        if is_header(line):
            continue
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 2:
            continue
        v0 = safe_float(parts[0])
        v1 = safe_float(parts[1])
        if v0 is None or v1 is None:
            continue
        symbol  = int(v0) if v0 < 1_000_000 else int(round(v0 / SYMBOL_DUR))
        slot    = symbol // 14
        records.append({"symbol": symbol, "bytes_sent": int(v1),
                        "slot": slot, "time_us": round(symbol * SYMBOL_DUR, 3)})
    return records


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    logging.info(f"    {os.path.basename(path)}  ({len(rows)} rows)")


def clean_all():
    ensure_dirs()
    found_tp = 0; found_pkt = 0

    for cell in range(1, NUM_CELLS + 1):
        logging.info(f"Cell {cell:2d}:")

        # ── pkt-stats ────────────────────────────────────────────
        pkt_path = find_file([f"pkt-stats-cell-{cell}.dat",
                               f"pkt_stats_cell_{cell}.dat",
                               f"pkt-stats-cell{cell}.dat"])
        slot_records = []
        if pkt_path:
            sym_recs = parse_pkt_stats(pkt_path)
            slot_records = aggregate_pkt_to_slots(sym_recs)
            if slot_records:
                write_csv(os.path.join(CLEAN_DIR, f"pkt_stats_cell{cell}.csv"),
                          slot_records,
                          ["slot","pkts_sent","pkts_received","pkts_lost","too_late","loss_flag"])
                found_pkt += 1
                total_tx   = sum(r["pkts_sent"] for r in slot_records)
                total_lost = sum(r["pkts_lost"] for r in slot_records)
                logging.info(f"    pkt-stats: {len(slot_records)} slots, "
                             f"tx={total_tx}, lost={total_lost}")
        else:
            logging.warning(f"    pkt-stats-cell-{cell}.dat NOT FOUND")

        # ── throughput ───────────────────────────────────────────
        tp_path = find_file([f"throughput-cell-{cell}.dat",
                              f"throughput_cell_{cell}.dat",
                              f"throughput-cell{cell}.dat"])
        if tp_path:
            raw = parse_throughput(tp_path)
            if raw:
                # aggregate to slots
                slot_map = {}
                for r in raw:
                    s = r["slot"]
                    slot_map[s] = slot_map.get(s, 0) + r["bytes_sent"]
                tp_slots = []
                for s, b in sorted(slot_map.items()):
                    gbps = (b * 8 / SLOT_DURATION_S) / 1e9
                    tp_slots.append({"slot": s, "bytes_sent": b,
                                     "time_s": round(s * SLOT_DURATION_S, 6),
                                     "gbps": round(gbps, 6)})
                write_csv(os.path.join(CLEAN_DIR, f"throughput_slot_cell{cell}.csv"),
                          tp_slots, ["slot","bytes_sent","time_s","gbps"])
                found_tp += 1
                peak = max(r["gbps"] for r in tp_slots)
                logging.info(f"    throughput: {len(tp_slots)} slots, peak={peak:.2f} Gbps")
        else:
            # Estimate from pkt-stats
            if slot_records:
                tp_slots = estimate_throughput_from_slots(slot_records)
                write_csv(os.path.join(CLEAN_DIR, f"throughput_slot_cell{cell}.csv"),
                          tp_slots, ["slot","bytes_sent","time_s","gbps"])
                if tp_slots:
                    peak = max(r["gbps"] for r in tp_slots)
                    logging.info(f"    throughput ESTIMATED: {len(tp_slots)} slots, peak={peak:.2f} Gbps")

    logging.info(f"\nDone. pkt-stats={found_pkt}/24  throughput={found_tp}/24")
    return found_pkt, found_tp


if __name__ == "__main__":
    clean_all()