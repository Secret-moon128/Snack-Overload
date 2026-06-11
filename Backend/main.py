"""
Fronthaul Network Optimization - Backend API
FastAPI server exposing endpoints for:
  - CSV upload & data cleaning
  - Topology identification (correlation-based clustering)
  - Link capacity estimation (with/without buffer)
  - Aggregated throughput time-series per link
"""

import os
import io
import json
import logging
import traceback
from typing import List, Optional, Dict, Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from data_cleaner import clean_throughput_file, clean_packet_stats_file
from topology import identify_topology
from capacity import estimate_link_capacity
from aggregator import aggregate_per_link

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fronthaul Optimizer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store: keyed by cell_id -> {"throughput": df, "packet_stats": df}
store: Dict[str, Dict[str, pd.DataFrame]] = {}
topology_result: Dict[str, Any] = {}
capacity_result: Dict[str, Any] = {}
aggregated_result: Dict[str, Any] = {}


# ── Models ───────────────────────────────────────────────────────────────────

class TopologyRequest(BaseModel):
    seed_hints: Optional[Dict[str, str]] = None  # e.g. {"cell1": "link2", "cell2": "link3"}
    n_links: int = 3


class CapacityRequest(BaseModel):
    link_rate_gbps: float = 25.0
    buffer_symbols: int = 4
    symbol_us: float = 35.7
    max_loss_pct: float = 1.0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _df_to_json(df: pd.DataFrame) -> list:
    return json.loads(df.to_json(orient="records"))


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "cells_loaded": list(store.keys())}


@app.post("/upload/throughput/{cell_id}")
async def upload_throughput(cell_id: str, file: UploadFile = File(...)):
    """Accept a CSV throughput file for one cell, clean it, store it."""
    raw = await file.read()
    try:
        df_clean = clean_throughput_file(io.BytesIO(raw), cell_id)
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=422, detail=f"Throughput parse error: {e}")

    if cell_id not in store:
        store[cell_id] = {}
    store[cell_id]["throughput"] = df_clean

    return {
        "cell_id": cell_id,
        "rows": len(df_clean),
        "columns": list(df_clean.columns),
        "sample": _df_to_json(df_clean.head(3)),
    }


@app.post("/upload/packet_stats/{cell_id}")
async def upload_packet_stats(cell_id: str, file: UploadFile = File(...)):
    """Accept a CSV packet-statistics file for one cell, clean it, store it."""
    raw = await file.read()
    try:
        df_clean = clean_packet_stats_file(io.BytesIO(raw), cell_id)
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=422, detail=f"Packet-stats parse error: {e}")

    if cell_id not in store:
        store[cell_id] = {}
    store[cell_id]["packet_stats"] = df_clean

    return {
        "cell_id": cell_id,
        "rows": len(df_clean),
        "columns": list(df_clean.columns),
        "sample": _df_to_json(df_clean.head(3)),
    }


@app.get("/cells")
def list_cells():
    summary = {}
    for cell_id, data in store.items():
        summary[cell_id] = {
            "has_throughput": "throughput" in data,
            "has_packet_stats": "packet_stats" in data,
        }
    return summary


@app.post("/topology/identify")
def run_topology(req: TopologyRequest):
    global topology_result
    if not store:
        raise HTTPException(status_code=400, detail="No cell data loaded. Upload files first.")

    # Build packet-loss matrix for cells that have packet_stats
    ps_data = {
        cid: d["packet_stats"]
        for cid, d in store.items()
        if "packet_stats" in d
    }
    if len(ps_data) < 2:
        raise HTTPException(
            status_code=400,
            detail="Need at least 2 cells with packet_stats to identify topology."
        )

    try:
        topology_result = identify_topology(ps_data, req.seed_hints, req.n_links)
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

    return topology_result


@app.get("/topology")
def get_topology():
    if not topology_result:
        raise HTTPException(status_code=404, detail="Topology not yet computed. POST /topology/identify first.")
    return topology_result


@app.post("/capacity/estimate")
def run_capacity(req: CapacityRequest):
    global capacity_result
    if not topology_result:
        raise HTTPException(status_code=400, detail="Topology not identified. Run /topology/identify first.")

    tp_data = {
        cid: d["throughput"]
        for cid, d in store.items()
        if "throughput" in d
    }
    if not tp_data:
        raise HTTPException(status_code=400, detail="No throughput data loaded.")

    try:
        capacity_result = estimate_link_capacity(
            topology=topology_result,
            throughput_data=tp_data,
            link_rate_gbps=req.link_rate_gbps,
            buffer_symbols=req.buffer_symbols,
            symbol_us=req.symbol_us,
            max_loss_pct=req.max_loss_pct,
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

    return capacity_result


@app.get("/capacity")
def get_capacity():
    if not capacity_result:
        raise HTTPException(status_code=404, detail="Capacity not yet estimated. POST /capacity/estimate first.")
    return capacity_result


@app.get("/timeseries/{link_id}")
def get_timeseries(link_id: str):
    """Return per-slot aggregated Gbps for a given link."""
    if not topology_result:
        raise HTTPException(status_code=400, detail="Topology not identified.")

    tp_data = {
        cid: d["throughput"]
        for cid, d in store.items()
        if "throughput" in d
    }
    link_cells = topology_result.get("link_cells", {}).get(link_id)
    if not link_cells:
        raise HTTPException(status_code=404, detail=f"Link {link_id} not found in topology result.")

    try:
        ts = aggregate_per_link(link_cells, tp_data)
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

    return {"link_id": link_id, "slots": ts}


@app.delete("/reset")
def reset():
    store.clear()
    topology_result.clear()
    capacity_result.clear()
    aggregated_result.clear()
    return {"status": "cleared"}