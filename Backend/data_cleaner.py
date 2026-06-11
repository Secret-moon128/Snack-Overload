"""
data_cleaner.py
---------------
Handles reading and cleaning of the two CSV types produced by the O-RAN
fronthaul measurement framework:

  1. Throughput file  – one row per symbol, columns vary but always include
                        a timestamp/index and a payload-bytes or bits column.
  2. Packet-statistics file – one row per slot (RU-side capture), columns
                        include timestamp, total packets, lost packets.

Both files may:
  - Have comment lines starting with '#' or '%'
  - Use spaces, tabs, semicolons, or commas as delimiters
  - Have trailing whitespace / inconsistent quoting
  - Miss a header row entirely (positional parsing applied)
  - Have clock-drift offsets (packet-stats file – documented in problem statement)
"""

import io
import re
import logging
from typing import Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
SYMBOLS_PER_SLOT = 14
SLOT_DURATION_US = 500.0          # microseconds
SYMBOL_DURATION_US = SLOT_DURATION_US / SYMBOLS_PER_SLOT  # ≈35.71 µs
BITS_PER_BYTE = 8

# Column name aliases – maps messy source names to our canonical names
_THROUGHPUT_ALIASES = {
    "time":       ["time", "timestamp", "ts", "t", "time_us", "time_ns", "time_ms", "slot_index", "symbol_index", "index"],
    "bytes":      ["bytes", "payload_bytes", "byte_count", "data_bytes", "payload", "size", "length", "octets"],
    "bits":       ["bits", "bit_count", "payload_bits", "data_bits"],
}

_PKTSTATS_ALIASES = {
    "time":       ["time", "timestamp", "ts", "t", "slot_time", "time_us", "time_ms"],
    "tx_pkts":    ["tx_pkts", "total_tx", "sent", "transmitted", "pkts_sent", "num_pkts", "total_pkts"],
    "rx_pkts":    ["rx_pkts", "total_rx", "received", "pkts_rx", "rx"],
    "lost_pkts":  ["lost", "lost_pkts", "dropped", "drop", "loss", "pkt_loss"],
}


# ── Internal helpers ─────────────────────────────────────────────────────────

def _sniff_delimiter(sample: str) -> str:
    counts = {d: sample.count(d) for d in [",", "\t", ";", " "]}
    return max(counts, key=counts.get)


def _strip_comments(text: str) -> str:
    lines = [l for l in text.splitlines() if not l.strip().startswith(("#", "%", "//"))]
    return "\n".join(lines)


def _normalize_colname(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.strip().lower()).strip("_")


def _map_columns(df: pd.DataFrame, alias_map: dict) -> pd.DataFrame:
    """Rename columns to canonical names using the alias map."""
    rename = {}
    cols_lower = {_normalize_colname(c): c for c in df.columns}
    for canonical, aliases in alias_map.items():
        if canonical in df.columns:
            continue  # already there
        for alias in aliases:
            norm = _normalize_colname(alias)
            if norm in cols_lower:
                rename[cols_lower[norm]] = canonical
                break
    df = df.rename(columns=rename)
    return df


def _infer_positional_throughput(df: pd.DataFrame) -> pd.DataFrame:
    """When column names are absent/unrecognised, fall back to position."""
    ncols = df.shape[1]
    if ncols == 1:
        df.columns = ["bytes"]
        df.insert(0, "time", range(len(df)))
    elif ncols == 2:
        df.columns = ["time", "bytes"]
    elif ncols >= 3:
        # assume: time | bytes | possibly others
        cols = ["time", "bytes"] + [f"extra_{i}" for i in range(ncols - 2)]
        df.columns = cols
    return df


def _infer_positional_pktstats(df: pd.DataFrame) -> pd.DataFrame:
    ncols = df.shape[1]
    if ncols == 2:
        df.columns = ["time", "lost_pkts"]
        df["tx_pkts"] = np.nan
    elif ncols == 3:
        df.columns = ["time", "tx_pkts", "lost_pkts"]
    elif ncols >= 4:
        df.columns = ["time", "tx_pkts", "rx_pkts", "lost_pkts"] + \
                     [f"extra_{i}" for i in range(ncols - 4)]
    return df


def _parse_raw(raw: Union[bytes, io.BytesIO]) -> pd.DataFrame:
    if isinstance(raw, io.BytesIO):
        text = raw.read().decode("utf-8", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")

    text = _strip_comments(text)
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("File appears empty after stripping comments.")

    delim = _sniff_delimiter(lines[0])
    df = pd.read_csv(
        io.StringIO("\n".join(lines)),
        sep=delim,
        engine="python",
        skipinitialspace=True,
        on_bad_lines="warn",
    )
    # Normalise column names
    df.columns = [_normalize_colname(c) for c in df.columns]
    return df


# ── Public API ───────────────────────────────────────────────────────────────

def clean_throughput_file(raw: Union[bytes, io.BytesIO], cell_id: str) -> pd.DataFrame:
    """
    Parse and clean a symbol-level throughput file.

    Returns a DataFrame with columns:
      - symbol_index  : sequential integer index of the symbol
      - slot_index    : symbol_index // 14
      - time_us       : elapsed time in microseconds (derived if not present)
      - bytes         : payload bytes for this symbol
      - gbps          : instantaneous data rate in Gbps for this symbol
    """
    df = _parse_raw(raw)

    # Try alias mapping, then positional
    df = _map_columns(df, _THROUGHPUT_ALIASES)
    if "bytes" not in df.columns and "bits" not in df.columns:
        logger.warning(f"[{cell_id}] No bytes/bits column found — attempting positional parse.")
        df = _infer_positional_throughput(df)

    # If we have bits but not bytes
    if "bits" in df.columns and "bytes" not in df.columns:
        df["bytes"] = df["bits"] / BITS_PER_BYTE

    # Ensure numeric
    df["bytes"] = pd.to_numeric(df["bytes"], errors="coerce").fillna(0.0)

    # Build or normalise time column
    if "time" in df.columns:
        df["time"] = pd.to_numeric(df["time"], errors="coerce").ffill()
        # Detect unit: if max value looks like nanoseconds scale it
        t_max = df["time"].max()
        if t_max > 1e9:
            df["time_us"] = df["time"] / 1e3      # ns → µs
        elif t_max > 1e6:
            df["time_us"] = df["time"] / 1e3      # ms → µs?  heuristic
        else:
            df["time_us"] = df["time"]             # assume µs already
    else:
        # No time column – synthesise from symbol index
        df["time_us"] = np.arange(len(df)) * SYMBOL_DURATION_US

    df["symbol_index"] = np.arange(len(df))
    df["slot_index"]   = df["symbol_index"] // SYMBOLS_PER_SLOT

    # Instantaneous data rate (Gbps) per symbol
    df["gbps"] = (df["bytes"] * BITS_PER_BYTE) / (SYMBOL_DURATION_US * 1e-6) / 1e9

    # Drop outliers: negative bytes or impossibly large values (> 1 Tbps)
    df = df[(df["bytes"] >= 0) & (df["gbps"] < 1000)].copy()
    df.reset_index(drop=True, inplace=True)

    df["cell_id"] = cell_id
    logger.info(f"[{cell_id}] Throughput cleaned: {len(df)} symbols → "
                f"{df['slot_index'].nunique()} slots")
    return df[["cell_id", "symbol_index", "slot_index", "time_us", "bytes", "gbps"]]


def clean_packet_stats_file(raw: Union[bytes, io.BytesIO], cell_id: str) -> pd.DataFrame:
    """
    Parse and clean a slot-level packet-statistics file (captured at RU side).

    Returns a DataFrame with columns:
      - slot_index     : sequential slot number (integer, re-indexed from 0)
      - time_us        : RU-side timestamp in microseconds
      - tx_pkts        : packets sent (DU side, may be NaN if unavailable)
      - lost_pkts      : packets lost (dropped by switch or never received)
      - loss_flag      : bool – True if any packet loss in this slot
    """
    df = _parse_raw(raw)

    df = _map_columns(df, _PKTSTATS_ALIASES)
    if "lost_pkts" not in df.columns:
        logger.warning(f"[{cell_id}] No lost_pkts column found — attempting positional parse.")
        df = _infer_positional_pktstats(df)

    # Numeric coercion
    for col in ["tx_pkts", "lost_pkts", "rx_pkts"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).clip(lower=0)

    if "lost_pkts" not in df.columns:
        if "tx_pkts" in df.columns and "rx_pkts" in df.columns:
            df["lost_pkts"] = (df["tx_pkts"] - df["rx_pkts"]).clip(lower=0)
        else:
            df["lost_pkts"] = 0.0

    # Timestamp
    if "time" in df.columns:
        df["time"] = pd.to_numeric(df["time"], errors="coerce").ffill()
        t_max = df["time"].max()
        if t_max > 1e9:
            df["time_us"] = df["time"] / 1e3
        elif t_max > 1e6:
            df["time_us"] = df["time"]
        else:
            df["time_us"] = df["time"] * 1e3   # assume ms → µs
    else:
        df["time_us"] = np.arange(len(df)) * SLOT_DURATION_US

    df["slot_index"] = np.arange(len(df))

    # ── Clock-drift correction (hint 3 in problem statement) ──────────────
    # The RU-side clock may be shifted relative to DU by a constant offset.
    # We detect and strip any monotonically-offset prefix by anchoring to slot 0.
    if "time_us" in df.columns:
        expected_start = 0.0
        actual_start   = df["time_us"].iloc[0]
        drift_offset   = actual_start - expected_start
        if abs(drift_offset) > SLOT_DURATION_US:
            logger.info(f"[{cell_id}] Clock drift detected: {drift_offset:.1f} µs — correcting.")
            df["time_us"] = df["time_us"] - drift_offset

    df["loss_flag"] = df["lost_pkts"] > 0
    df["cell_id"]   = cell_id

    # Drop rows with impossible timestamps
    df = df[df["time_us"] >= 0].copy()
    df.reset_index(drop=True, inplace=True)

    logger.info(f"[{cell_id}] PacketStats cleaned: {len(df)} slots, "
                f"loss slots: {df['loss_flag'].sum()}")

    cols = ["cell_id", "slot_index", "time_us", "lost_pkts", "loss_flag"]
    if "tx_pkts" in df.columns:
        cols.insert(3, "tx_pkts")
    return df[cols]