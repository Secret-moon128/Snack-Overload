"""
data_cleaner.py  —  fixed for actual file format
------------------------------------------------
pkt-stats-cell-N.dat confirmed format:
  Header: <slot> <slotStart> <txPackets> <rxPackets> <tooLateRxPackets>
  Rows:   1.00001  0  0  0  0
          1.00465  16  16  0
  Col 0 = slot id (float, e.g. 1.00001)
  Col 2 = txPackets
  Col 3 = rxPackets
  Col 4 = tooLateRxPackets (late = congestion loss)

throughput-cell-N.dat: searched everywhere in data/ tree.
If missing, throughput estimated from txPackets * AVG_PKT_BYTES (1400 bytes).
"""

import os, re, csv, logging, glob

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
RAW_DIR   = os.path.join(BASE_DIR, "data")
CLEAN_DIR = os.path.join(RAW_DIR, "cleaned")
NUM_CELLS = 24

SLOT_DURATION_S    = 500e-6
AVG_PKT_BYTES      = 1400
SYMBOL_DURATION_US = 500 / 14


def ensure_dirs():
    os.makedirs(CLEAN_DIR, exist_ok=True)


def split_line(line):
    return re.split(r"[\s,;|]+", line.strip())


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
    Format: slot_float  slotStart  txPackets  rxPackets  tooLateRxPackets
    slot_float like 1.00001 → integer slot = round(1.00001) = 1
    """
    records = []
    with open(path, "r", errors="replace") as f:
        lines = f.readlines()

    for line in lines:
        if is_header(line):
            continue
        parts = split_line(line)
        if len(parts) < 4:
            continue
        slot_f = safe_float(parts[0])
        tx     = safe_int(parts[2]) if len(parts) > 2 else None
        rx     = safe_int(parts[3]) if len(parts) > 3 else None
        late   = safe_int(parts[4]) if len(parts) > 4 else 0

        if slot_f is None or tx is None or rx is None:
            continue

        slot_int = int(round(slot_f))
        lost     = max(0, tx - rx)

        records.append({
            "slot":          slot_int,
            "slot_raw":      round(slot_f, 5),
            "pkts_sent":     tx,
            "pkts_received": rx,
            "pkts_lost":     lost,
            "too_late":      late or 0,
            "loss_flag":     1 if (lost > 0 or (late or 0) > 0) else 0,
        })

    return records


def parse_throughput(path):
    records = []
    with open(path, "r", errors="replace") as f:
        lines = f.readlines()
    for line in lines:
        if is_header(line):
            continue
        parts = split_line(line)
        if len(parts) < 2:
            continue
        v0 = safe_float(parts[0])
        v1 = safe_float(parts[1])
        if v0 is None or v1 is None:
            continue
        if v0 > 1_000_000:
            time_us = v0
            symbol  = int(round(time_us / SYMBOL_DURATION_US))
        else:
            symbol  = int(v0)
            time_us = symbol * SYMBOL_DURATION_US
        slot = symbol // 14
        records.append({"symbol": symbol, "bytes_sent": int(v1), "slot": slot, "time_us": round(time_us, 3)})
    return records


def aggregate_tp_to_slots(records):
    slot_map = {}
    for r in records:
        slot_map[r["slot"]] = slot_map.get(r["slot"], 0) + r["bytes_sent"]
    result = []
    for slot, total_bytes in sorted(slot_map.items()):
        gbps = (total_bytes * 8 / SLOT_DURATION_S) / 1e9
        result.append({"slot": slot, "bytes_sent": total_bytes,
                        "time_s": round(slot * SLOT_DURATION_S, 6), "gbps": round(gbps, 6)})
    return result


def estimate_throughput_from_pkt_stats(pkt_records):
    """Estimate Gbps from txPackets * 1400 bytes per slot."""
    slot_map = {}
    for r in pkt_records:
        s = r["slot"]
        slot_map[s] = slot_map.get(s, 0) + r["pkts_sent"]
    result = []
    for slot, total_pkts in sorted(slot_map.items()):
        total_bytes = total_pkts * AVG_PKT_BYTES
        gbps = (total_bytes * 8 / SLOT_DURATION_S) / 1e9
        result.append({"slot": slot, "bytes_sent": total_bytes,
                        "time_s": round(slot * SLOT_DURATION_S, 6), "gbps": round(gbps, 6)})
    return result


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    logging.info(f"    → {os.path.basename(path)}  ({len(rows)} rows)")


def clean_all():
    ensure_dirs()
    found_tp = 0; found_pkt = 0

    for cell in range(1, NUM_CELLS + 1):
        logging.info(f"Cell {cell:2d}:")

        # pkt-stats
        pkt_path = find_file([f"pkt-stats-cell-{cell}.dat", f"pkt_stats_cell_{cell}.dat",
                               f"pkt-stats-cell{cell}.dat"])
        pkt_records = []
        if pkt_path:
            pkt_records = parse_pkt_stats(pkt_path)
            if pkt_records:
                write_csv(os.path.join(CLEAN_DIR, f"pkt_stats_cell{cell}.csv"),
                          pkt_records,
                          ["slot","slot_raw","pkts_sent","pkts_received","pkts_lost","too_late","loss_flag"])
                found_pkt += 1
        else:
            logging.warning(f"    pkt-stats-cell-{cell}.dat NOT FOUND")

        # throughput
        tp_path = find_file([f"throughput-cell-{cell}.dat", f"throughput_cell_{cell}.dat",
                              f"throughput-cell{cell}.dat"])
        if tp_path:
            raw = parse_throughput(tp_path)
            if raw:
                write_csv(os.path.join(CLEAN_DIR, f"throughput_symbol_cell{cell}.csv"),
                          raw, ["symbol","bytes_sent","slot","time_us"])
                slots = aggregate_tp_to_slots(raw)
                write_csv(os.path.join(CLEAN_DIR, f"throughput_slot_cell{cell}.csv"),
                          slots, ["slot","bytes_sent","time_s","gbps"])
                found_tp += 1
        else:
            if pkt_records:
                slots = estimate_throughput_from_pkt_stats(pkt_records)
                write_csv(os.path.join(CLEAN_DIR, f"throughput_slot_cell{cell}.csv"),
                          slots, ["slot","bytes_sent","time_s","gbps"])
                logging.info(f"    throughput ESTIMATED from pkt-stats ({len(slots)} slots)")

    logging.info(f"\nDone. pkt-stats={found_pkt}/24  throughput={found_tp}/24 (rest estimated)")
    return found_pkt, found_tp


if __name__ == "__main__":
    clean_all()