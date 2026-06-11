# Fronthaul Network Optimizer

Intelligent Fronthaul Network Optimization — Topology Identification & Link
Capacity Estimation for the O-RAN hackathon problem statement.

---

## Project layout

```
fronthaul/
│
├── backend/                    ← FastAPI Python server
│   ├── main.py                 ← App entry point, all REST endpoints
│   ├── data_cleaner.py         ← CSV parsing & cleaning (throughput + packet stats)
│   ├── topology.py             ← Correlation-based link clustering
│   ├── capacity.py             ← Link capacity estimation (w/ and w/o buffer)
│   ├── aggregator.py           ← Per-link Gbps time-series builder
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                   ← React + Vite SPA
│   ├── src/
│   │   ├── main.jsx            ← React entry point
│   │   ├── App.jsx             ← Routing shell + sidebar
│   │   ├── styles/
│   │   │   ├── global.css      ← Design tokens, shared utilities
│   │   │   └── App.css         ← Layout: sidebar, main content, shared components
│   │   ├── utils/
│   │   │   └── api.js          ← Axios API client
│   │   ├── pages/
│   │   │   ├── UploadPage.jsx  ← Drag-and-drop CSV upload, upload log
│   │   │   ├── UploadPage.css
│   │   │   ├── TopologyPage.jsx← Topology identification controls + results
│   │   │   ├── TopologyPage.css
│   │   │   ├── CapacityPage.jsx← Capacity estimation controls + results
│   │   │   ├── CapacityPage.css
│   │   │   ├── TimeSeriesPage.jsx ← Traffic graph (Figure 3 equivalent)
│   │   │   └── TimeSeriesPage.css
│   │   └── components/
│   │       ├── CorrelationHeatmap.jsx ← SVG heatmap of cell cross-correlations
│   │       └── LossPatternGrid.jsx    ← Figure 1 style slot-loss pattern grid
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   ├── Dockerfile
│   └── nginx.conf
│
├── scripts/
│   └── batch_upload.py         ← Bulk-upload all 24 cell CSVs in one shot
│
└── docker-compose.yml
```

---

## Quick start

### Option A — Docker Compose (recommended)

```bash
docker-compose up --build
```

Frontend: http://localhost:5173  
Backend API: http://localhost:8000  
API docs: http://localhost:8000/docs

### Option B — Local development

**Backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

---

## Loading data

### Via the UI
1. Open http://localhost:5173
2. Enter a cell ID (e.g. `cell_01`)
3. Drag the throughput CSV into the left drop zone
4. Drag the packet-statistics CSV into the right drop zone
5. Repeat for all 24 cells

### Via batch upload script
```bash
# Flat layout
python scripts/batch_upload.py --data-dir ./data --api http://localhost:8000

# Sub-directory layout (cell_01/throughput.csv, cell_01/packet_stats.csv, …)
python scripts/batch_upload.py --data-dir ./data
```

The script auto-detects cell IDs and file types from filename patterns.

---

## Workflow

1. **Upload** — load all 24 cells' CSV files  
2. **Topology** — click "Identify topology"; optionally provide seed hints  
   (`cell1:link2, cell2:link3`) and number of expected links  
3. **Capacity** — set link rate, buffer size, loss tolerance; click "Estimate capacity"  
4. **Traffic Graph** — select a link tab to fetch and display the 60-second Gbps time-series

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + loaded cells |
| POST | `/upload/throughput/{cell_id}` | Upload throughput CSV for a cell |
| POST | `/upload/packet_stats/{cell_id}` | Upload packet-stats CSV for a cell |
| GET | `/cells` | List loaded cells |
| POST | `/topology/identify` | Run topology identification |
| GET | `/topology` | Get last topology result |
| POST | `/capacity/estimate` | Run capacity estimation |
| GET | `/capacity` | Get last capacity result |
| GET | `/timeseries/{link_id}` | Per-slot Gbps series for a link |
| DELETE | `/reset` | Clear all loaded data |

---

## Data cleaning — what the code handles

**Throughput file**
- Comment lines (`#`, `%`, `//`) stripped
- Delimiter auto-detected (comma / tab / semicolon / space)
- Timestamp units detected (ns → µs, ms → µs)
- Bits vs bytes column auto-normalised
- Negative / absurdly large values discarded
- Symbol index → slot index derivation (÷14)
- Instantaneous Gbps computed per symbol

**Packet Statistics file**
- Same delimiter / comment handling
- Clock drift vs DU corrected (Hint 3 in problem statement)
- `lost_pkts` derived from `tx_pkts - rx_pkts` if column absent
- `loss_flag` boolean added per slot

---

## Algorithm notes

### Topology identification
Cells on the same link share congestion events, producing correlated
`loss_flag` series. The code:
1. Builds a binary loss vector per cell (1 = loss occurred this slot)
2. Computes pairwise Pearson correlation
3. Converts to distance (1 − |ρ|) and runs agglomerative clustering
4. Seeds cluster labels from known `cell:link` hints

### Capacity estimation
- **Without buffer**: 99th-percentile of per-slot aggregated Gbps  
  (allows 1% loss tolerance)
- **With buffer**: binary-search over candidate link rates; simulates a
  leaky-bucket model; finds minimum rate where buffer overflow (packet drop)
  fraction ≤ 1% of active slots

Buffer size: `4 symbols × 35.71 µs/symbol × link_rate_bps`  
(converged iteratively since buffer size depends on the answer)