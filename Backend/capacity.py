"""
capacity.py
-----------
Estimates the required Ethernet link capacity for each identified link group.

Two cases as required by the problem statement:
  1. Without buffer  – capacity = peak aggregated throughput across all slots
                       (99th percentile to allow 1% packet loss tolerance)
  2. With buffer     – the switch can absorb bursts up to buffer_size bits;
                       capacity is reduced to the level where the buffer never
                       overflows for more than the allowed loss fraction.

Methodology
-----------
For each link:
  a) Aggregate per-slot throughput (Gbps) across all member cells.
  b) Compute the empirical CDF of per-slot data-rates.
  c) No-buffer capacity  = percentile(99) of per-slot Gbps   (1% loss allowed)
  d) With-buffer capacity:
       Simulate a leaky-bucket / token-bucket at varying link rates.
       The minimum rate at which the bucket (size = buffer_bits) never exceeds
       capacity AND slot-loss fraction ≤ max_loss_pct is the answer.
       We binary-search over candidate rates.

Units
-----
  Symbol duration = 500µs / 14 ≈ 35.71 µs
  Slot  duration  = 500 µs
  Buffer (4 symbols) = 4 × 35.71 µs ≈ 143 µs
"""

import logging
from typing import Dict, Any, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SYMBOLS_PER_SLOT   = 14
SLOT_DURATION_US   = 500.0          # µs
SYMBOL_DURATION_US = SLOT_DURATION_US / SYMBOLS_PER_SLOT
BITS_PER_BYTE      = 8


def _aggregate_link_gbps(
    cell_ids: List[str],
    throughput_data: Dict[str, pd.DataFrame],
) -> np.ndarray:
    """
    Aggregate per-slot Gbps for a list of cells.
    Returns a 1-D numpy array indexed by slot.
    """
    slot_totals: Dict[int, float] = {}

    for cell_id in cell_ids:
        df = throughput_data.get(cell_id)
        if df is None:
            logger.warning(f"No throughput data for cell {cell_id} – skipping.")
            continue

        # Sum bytes per slot, then convert to Gbps
        slot_bytes = df.groupby("slot_index")["bytes"].sum()
        for slot, b in slot_bytes.items():
            gbps = (b * BITS_PER_BYTE) / (SLOT_DURATION_US * 1e-6) / 1e9
            slot_totals[slot] = slot_totals.get(slot, 0.0) + gbps

    if not slot_totals:
        return np.array([0.0])

    max_slot = max(slot_totals.keys())
    ts = np.zeros(max_slot + 1)
    for slot, gbps in slot_totals.items():
        ts[slot] = gbps

    return ts


def _capacity_no_buffer(ts_gbps: np.ndarray, max_loss_pct: float) -> float:
    """
    No-buffer case: sort slot throughputs and pick the percentile
    that allows at most max_loss_pct % of slots to exceed capacity.
    Capacity = (100 - max_loss_pct)th percentile.
    """
    active = ts_gbps[ts_gbps > 0]
    if len(active) == 0:
        return 0.0
    percentile = 100.0 - max_loss_pct
    return float(np.percentile(active, percentile))


def _capacity_with_buffer(
    ts_gbps: np.ndarray,
    buffer_size_bits: float,
    max_loss_pct: float,
    link_rate_gbps: float,
) -> float:
    """
    With-buffer case: binary-search over candidate link rates.
    For each candidate rate, simulate a leaky bucket and measure what
    fraction of slots experience buffer overflow (≡ packet drops).
    Return the minimum rate whose loss fraction ≤ max_loss_pct.

    Parameters
    ----------
    ts_gbps          : per-slot aggregated throughput array (Gbps)
    buffer_size_bits : switch buffer in bits (= buffer_symbols × symbol_us × link_rate_bps)
                       NOTE: buffer_size_bits is given in absolute bits here (pre-computed)
    max_loss_pct     : acceptable packet-loss percentage (default 1.0)
    link_rate_gbps   : hint for the upper bound of binary search
    """
    def simulate_loss_fraction(rate_gbps: float) -> float:
        rate_bits_per_slot = rate_gbps * 1e9 * (SLOT_DURATION_US * 1e-6)
        buffer = 0.0
        loss_slots = 0

        for gbps in ts_gbps:
            if gbps == 0:
                # Drain buffer during idle slot
                buffer = max(0.0, buffer - rate_bits_per_slot)
                continue

            # Bits arriving this slot
            arriving = gbps * 1e9 * (SLOT_DURATION_US * 1e-6)
            # Drain buffer (departures)
            buffer = max(0.0, buffer - rate_bits_per_slot)
            # Add arrivals
            overflow = max(0.0, (buffer + arriving) - buffer_size_bits)
            buffer   = min(buffer + arriving, buffer_size_bits)

            if overflow > 0:
                loss_slots += 1

        active_slots = np.sum(ts_gbps > 0)
        if active_slots == 0:
            return 0.0
        return loss_slots / active_slots * 100.0

    # Binary search: low = average throughput, high = peak
    active = ts_gbps[ts_gbps > 0]
    if len(active) == 0:
        return 0.0

    low  = float(np.mean(active))
    high = float(np.max(active)) * 1.2   # 20% headroom above observed peak

    # Ensure high bound works
    if simulate_loss_fraction(high) > max_loss_pct:
        high *= 2.0

    for _ in range(50):   # 50 iterations → ~1e-15 precision in Gbps
        mid = (low + high) / 2.0
        if simulate_loss_fraction(mid) <= max_loss_pct:
            high = mid
        else:
            low = mid

    return float(high)


def estimate_link_capacity(
    topology: Dict[str, Any],
    throughput_data: Dict[str, pd.DataFrame],
    link_rate_gbps: float = 25.0,
    buffer_symbols: int   = 4,
    symbol_us: float      = SYMBOL_DURATION_US,
    max_loss_pct: float   = 1.0,
) -> Dict[str, Any]:
    """
    Estimate capacity for all links in the topology.

    Returns
    -------
    {
      "links": {
        "link2": {
          "cells": [...],
          "avg_gbps":             float,
          "peak_gbps":            float,
          "capacity_no_buffer":   float,
          "capacity_with_buffer": float,
          "buffer_size_bits":     float,
          "buffer_size_mbits":    float,
        },
        ...
      },
      "buffer_symbols":  int,
      "buffer_us":       float,
      "max_loss_pct":    float,
    }
    """
    link_cells = topology.get("link_cells", {})

    # Buffer size depends on the link rate (iterative – start with hint)
    # The problem states: buffer_bits = buffer_us × link_rate_bps
    buffer_us        = buffer_symbols * symbol_us
    buffer_bits_hint = buffer_us * 1e-6 * link_rate_gbps * 1e9

    results = {}

    for link_id, cell_ids in link_cells.items():
        ts = _aggregate_link_gbps(cell_ids, throughput_data)

        active = ts[ts > 0]
        avg_gbps  = float(np.mean(active)) if len(active) > 0 else 0.0
        peak_gbps = float(np.max(active))  if len(active) > 0 else 0.0

        cap_no_buf = _capacity_no_buffer(ts, max_loss_pct)

        # For the buffer case, buffer size is defined at the (unknown) optimal
        # rate. We converge in two passes:
        #   pass 1: use cap_no_buf as rate estimate for buffer size
        #   pass 2: re-compute buffer size at the answer from pass 1
        buf_bits_1 = buffer_us * 1e-6 * cap_no_buf * 1e9
        cap_buf_1  = _capacity_with_buffer(ts, buf_bits_1, max_loss_pct, link_rate_gbps)

        buf_bits_2 = buffer_us * 1e-6 * cap_buf_1 * 1e9
        cap_buf    = _capacity_with_buffer(ts, buf_bits_2, max_loss_pct, link_rate_gbps)

        # Final buffer size at the determined capacity
        buffer_size_bits  = buffer_us * 1e-6 * cap_buf * 1e9
        buffer_size_mbits = buffer_size_bits / 1e6

        logger.info(
            f"[{link_id}] cells={cell_ids}  "
            f"avg={avg_gbps:.3f} Gbps  peak={peak_gbps:.3f} Gbps  "
            f"cap_no_buf={cap_no_buf:.3f} Gbps  cap_buf={cap_buf:.3f} Gbps"
        )

        results[link_id] = {
            "cells":                  cell_ids,
            "n_cells":                len(cell_ids),
            "avg_gbps":               round(avg_gbps, 4),
            "peak_gbps":              round(peak_gbps, 4),
            "capacity_no_buffer":     round(cap_no_buf, 4),
            "capacity_with_buffer":   round(cap_buf, 4),
            "buffer_size_bits":       round(buffer_size_bits, 2),
            "buffer_size_mbits":      round(buffer_size_mbits, 4),
        }

    return {
        "links":           results,
        "buffer_symbols":  buffer_symbols,
        "buffer_us":       round(buffer_us, 2),
        "max_loss_pct":    max_loss_pct,
    }
