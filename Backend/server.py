"""
server.py  v3  —  Flask API for FH-OPT
Serves on http://localhost:5050
"""

import os, json, threading, time, importlib, math
from flask import Flask, jsonify
from flask_cors import CORS

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.chdir(BASE)

app   = Flask(__name__)
CORS(app)

state = {
    "running":   False,
    "step":      0,
    "step_name": "idle",
    "error":     None,
    "last_run":  None,
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
        state.update(running=True, error=None, step=0)

    steps = [
        (1, "Cleaning .dat files",    "data_cleaner", "clean_all"),
        (2, "Identifying topology",   "topology",     "run_topology"),
        (3, "Estimating capacity",    "capacity",     "run_capacity"),
        (4, "Building heatmap data",  "aggregator",   "run_aggregator"),
    ]

    try:
        for num, name, mod_name, fn_name in steps:
            with lock:
                state.update(step=num, step_name=name)
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
            getattr(mod, fn_name)()

        with lock:
            state.update(step=5, step_name="done", last_run=time.strftime("%H:%M:%S"))

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        with lock:
            state.update(error=f"{e}\n{tb}", step_name="error")
    finally:
        with lock:
            state["running"] = False


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
    threading.Thread(target=run_pipeline, daemon=True).start()
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
    if not d: return ("Not found", 404)
    return jsonify(d.get(link, []))


@app.route("/api/heatmap")
def api_heatmap():
    d = read_json("heatmap_data.json")
    return jsonify(d) if d else ("Not found", 404)


@app.route("/api/cell_stats")
def api_cell_stats():
    d = read_json("cell_stats.json")
    return jsonify(d) if d else ("Not found", 404)


# ── Debug endpoint: show first 5 rows of cleaned CSV ──────────────
@app.route("/api/debug/cell/<int:cell>")
def api_debug_cell(cell):
    import csv as csv_mod
    result = {}
    for kind in ["pkt_stats", "throughput_slot"]:
        path = os.path.join(DATA, "cleaned", f"{kind}_cell{cell}.csv")
        if os.path.isfile(path):
            with open(path, newline="") as f:
                rows = list(csv_mod.DictReader(f))
            result[kind] = {
                "total_rows": len(rows),
                "first_5": rows[:5],
                "last_2":  rows[-2:] if len(rows) >= 2 else rows,
            }
        else:
            result[kind] = "FILE NOT FOUND"
    return jsonify(result)


if __name__ == "__main__":
    print("FH-OPT API  →  http://localhost:5050")
    app.run(port=5050, debug=False, threaded=True)