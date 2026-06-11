"""
aggregator.py
-------------
Produces per-link, per-slot Gbps time-series used by the frontend
to render the traffic graph (Figure 3 in the problem statement).

Time resolution: one slot = 500 µs
Period: up to 60 seconds = 120,000 slots
"""

import logging
from typing import Dict, List, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SLOT_DURATION_US  = 500.0
BITS_PER_BYTE     = 8
SLOTS_PER_SECOND  = int(1e6 / SLOT_DURATION_US)   # 2000 slots/s


def aggregate_per_link(
    cell_ids: List[str],
    throughput_data: Dict[str, pd.DataFrame],
    duration_seconds: float = 60.0,
) -> List[Dict[str, Any]]:
    """
    Aggregate throughput across all cells on a link, at slot resolution.

    Returns a list of dicts:
      [{"slot": 0, "time_s": 0.0, "gbps": 1.23}, ...]
    """
    max_slots = int(duration_seconds * SLOTS_PER_SECOND)
    total_gbps = np.zeros(max_slots)

    for cell_id in cell_ids:
        df = throughput_data.get(cell_id)
        if df is None:
            continue

        slot_bytes = df.groupby("slot_index")["bytes"].sum()
        for slot, b in slot_bytes.items():
            if slot < max_slots:
                total_gbps[slot] += (b * BITS_PER_BYTE) / (SLOT_DURATION_US * 1e-6) / 1e9

    output = []
    for i, gbps in enumerate(total_gbps):
        output.append({
            "slot":   i,
            "time_s": round(i * SLOT_DURATION_US / 1e6, 6),
            "gbps":   round(float(gbps), 6),
        })

    return output