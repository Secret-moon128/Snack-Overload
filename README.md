# FH-OPT — Fronthaul Network Optimizer

Hackathon solution for "Intelligent Fronthaul Network Optimization:
Topology Identification and Link Capacity Estimation" (O-RAN / TSN).

---

## Project layout

```
snack-overload/
├── backend/
│   ├── data/                        ← put your .dat files here
│   │   └── cleaned/                 ← auto-created by data_cleaner.py
│   ├── data_cleaner.py
│   ├── topology.py
│   ├── capacity.py
│   ├── aggregator.py
│   ├── main.py
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── style.css
    └── app.js
```

---

## Step 1 — Download the dataset

Download the ZIP from the hackathon link (https://tinyurl.com/52xbe4n9)
and extract it so the files land like this:

```
backend/data/throughput-cell-1.dat
backend/data/throughput-cell-2.dat
...
backend/data/throughput-cell-24.dat
backend/data/pkt-stats-cell-1.dat
...
backend/data/pkt-stats-cell-24.dat
```

The `.dat` files are plain-text space-separated files.
No CSV conversion needed — the cleaner handles that.

---

## Step 2 — Run the backend

Requires **Python 3.10+** (no third-party packages needed).

```bash
cd backend
python main.py
```

This runs four steps in order:

| Step | Script           | Output |
|------|------------------|--------|
| 1    | data_cleaner.py  | `data/cleaned/throughput_slot_cellN.csv` etc. |
| 2    | topology.py      | `data/topology_result.json` |
| 3    | capacity.py      | `data/capacity_result.json`, `data/graph_data.json` |
| 4    | aggregator.py    | `data/heatmap_data.json`, `data/cell_stats.json` |

To run just one step:

```bash
python main.py --step topology   # clean | topology | capacity | aggregate
```

---

## Step 3 — Open the frontend

The frontend reads the JSON files from `../backend/data/` using the
native `fetch()` API (no server required for local dev on most browsers,
but some browsers block `file://` fetches).

### Option A — Python simple server (recommended)

```bash
# From the project root:
python -m http.server 8080
```

Then open: http://localhost:8080/frontend/

### Option B — VS Code Live Server

Install the "Live Server" extension, right-click `frontend/index.html`,
choose "Open with Live Server".

### Option C — Any static file server

```bash
# npm's http-server (if you have Node):
npx http-server . -p 8080
```

---

## Frontend libraries used (CDN, no install needed)

| Library | Version | Source | Purpose |
|---------|---------|--------|---------|
| React   | 18      | unpkg.com | UI framework |
| ReactDOM | 18    | unpkg.com | DOM rendering |
| Babel Standalone | latest | unpkg.com | JSX transpilation |
| Chart.js | 4.4.3 | unpkg.com | Data rate graphs |

**unpkg.com** is the official CDN for npm packages.
It is widely used, audited, and maintained by npm/Cloudflare.
No axios, no lodash, no unknown packages.

---

## How the algorithms work

### Topology identification

1. Load per-cell packet-statistics CSVs.
2. Build a *loss vector* per cell: set of slot indices where `pkts_lost > 0`.
3. Compute pairwise **Jaccard similarity** on loss events:
   `J(A,B) = |A∩B| / |A∪B|`
4. Single-linkage clustering with threshold `J ≥ 0.25`.
5. Apply seed constraints (Cell1 → Link2, Cell2 → Link3) to label clusters.
6. Remaining cluster → Link1.

### Link capacity estimation

**Without buffer**
- Aggregate per-slot Gbps across all cells on the link.
- Sort values; take the 99th percentile (1% loss budget means top 1% of
  traffic-carrying slots can exceed the link rate without problem).

**With 4-symbol buffer (143 µs)**
- Simulate a leaky-bucket: excess bits per slot flow into the buffer;
  buffer drains at the link rate; if buffer overflows, that slot is a drop.
- Binary-search the minimum link rate keeping drops ≤ 1% of
  traffic-carrying slots.

---

## Output files

| File | Description |
|------|-------------|
| `topology_result.json` | `link_assignment`, `clusters`, Jaccard `similarity_matrix` |
| `capacity_result.json` | Per-link: avg/peak Gbps, req. capacity with/without buffer |
| `graph_data.json` | Per-link slot-level time series (slot, time_s, gbps) |
| `heatmap_data.json` | Per-slot, per-cell traffic/loss flags for heatmap |
| `cell_stats.json` | Per-cell avg/peak Gbps, active slot count |