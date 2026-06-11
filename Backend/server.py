"""
server.py  —  Flask API for FH-OPT
Endpoints:
  GET  /api/status          — pipeline status + last results
  POST /api/run             — trigger full pipeline
  GET  /api/topology        — topology_result.json
  GET  /api/capacity        — capacity_result.json
  GET  /api/graph/<link>    — graph data for one link
  GET  /api/heatmap         — heatmap data
  GET  /api/cell_stats      — cell stats
"""

import os, json, threading, time, subprocess, sys
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")

app = Flask(__name__)
CORS(app)

# ── Pipeline state ───────────────────────────────────────────────
state = {
    "running": False,
    "step": 0,          # 0=idle 1=clean 2=topology 3=capacity 4=aggregate 5=done
    "step_name": "idle",
    "error": None,
    "last_run": None,
}
lock = threading.Lock()


def read_json(filename):
    path = os.path.join(DATA, filename)
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)


def run_pipeline():
    with lock:
        state["running"] = True
        state["error"]   = None
        state["step"]    = 0

    steps = [
        (1, "Cleaning data",          "data_cleaner", "clean_all"),
        (2, "Identifying topology",   "topology",     "run_topology"),
        (3, "Estimating capacity",    "capacity",     "run_capacity"),
        (4, "Building frontend data", "aggregator",   "run_aggregator"),
    ]

    try:
        for step_num, step_name, module_name, fn_name in steps:
            with lock:
                state["step"]      = step_num
                state["step_name"] = step_name

            # dynamic import so we always get fresh module
            import importlib
            mod = importlib.import_module(module_name)
            importlib.reload(mod)
            fn = getattr(mod, fn_name)
            fn()

        with lock:
            state["step"]      = 5
            state["step_name"] = "done"
            state["last_run"]  = time.strftime("%H:%M:%S")

    except Exception as e:
        with lock:
            state["error"]     = str(e)
            state["step_name"] = "error"
    finally:
        with lock:
            state["running"] = False


# ── Routes ────────────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    with lock:
        s = dict(state)
    s["has_results"] = os.path.isfile(os.path.join(DATA, "capacity_result.json"))
    return jsonify(s)


@app.route("/api/run", methods=["POST"])
def api_run():
    with lock:
        if state["running"]:
            return jsonify({"ok": False, "msg": "Already running"}), 409
    t = threading.Thread(target=run_pipeline, daemon=True)
    t.start()
    return jsonify({"ok": True})


@app.route("/api/topology")
def api_topology():
    d = read_json("topology_result.json")
    return jsonify(d) if d else ("Not found", 404)


@app.route("/api/capacity")
def api_capacity():
    d = read_json("capacity_result.json")
    return jsonify(d) if d else ("Not found", 404)


@app.route("/api/graph/<link>")
def api_graph(link):
    d = read_json("graph_data.json")
    if not d:
        return ("Not found", 404)
    return jsonify(d.get(link, []))


@app.route("/api/heatmap")
def api_heatmap():
    d = read_json("heatmap_data.json")
    return jsonify(d) if d else ("Not found", 404)


@app.route("/api/cell_stats")
def api_cell_stats():
    d = read_json("cell_stats.json")
    return jsonify(d) if d else ("Not found", 404)


if __name__ == "__main__":
    os.chdir(BASE)
    print("FH-OPT API  →  http://localhost:5050")
    app.run(port=5050, debug=False)
