import { useState, useEffect, useRef } from "react";
import "./App.css";

// ── Data paths — goes up to backend/data from src/
const DATA_BASE = process.env.PUBLIC_URL
  ? `${process.env.PUBLIC_URL}/data`
  : "http://localhost:8000/data";

// Override this if you serve backend data differently:
// const DATA_BASE = "http://localhost:5000/data";

const PATHS = {
  topology:  `${DATA_BASE}/topology_result.json`,
  capacity:  `${DATA_BASE}/capacity_result.json`,
  heatmap:   `${DATA_BASE}/heatmap_data.json`,
  graphData: `${DATA_BASE}/graph_data.json`,
  cellStats: `${DATA_BASE}/cell_stats.json`,
};

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} — ${url}`);
  return r.json();
}

const fmt2 = (n) => (typeof n === "number" ? n.toFixed(2) : "—");
const linkClass = (name) =>
  name === "Link1" ? "link1" : name === "Link2" ? "link2" : "link3";

// ── Top Nav ────────────────────────────────────────────────────────────────
function TopNav({ tab, setTab }) {
  const tabs = ["Overview", "Topology", "Heatmap", "Capacity", "Graphs"];
  return (
    <nav className="topnav">
      <div className="topnav-brand">
        <span className="dot" />
        FH-OPT
      </div>
      <div className="topnav-tabs">
        {tabs.map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
    </nav>
  );
}

// ── Pipeline strip ─────────────────────────────────────────────────────────
function Pipeline({ doneCount }) {
  const steps = [
    { n: 1, label: "Clean data" },
    { n: 2, label: "Topology ID" },
    { n: 3, label: "Capacity est." },
    { n: 4, label: "Aggregation" },
  ];
  return (
    <div className="pipeline">
      {steps.map((s, i) => (
        <div
          key={s.n}
          className={`pipeline-step ${i < doneCount ? "done" : i === doneCount ? "active" : ""}`}
        >
          <span className="step-num">{i < doneCount ? "✓" : s.n}</span>
          {s.label}
        </div>
      ))}
    </div>
  );
}

function StatBox({ label, value, unit, color }) {
  return (
    <div className={`stat-box ${color || ""}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {unit && <div className="unit">{unit}</div>}
    </div>
  );
}

// ── Overview ───────────────────────────────────────────────────────────────
function OverviewTab({ topology, capacity, cellStats }) {
  if (!topology || !capacity) {
    return (
      <div className="loading-msg">
        <div className="loading-spinner" />
        <p>Run the backend pipeline first, then reload.</p>
        <code className="run-hint">cd Backend &amp;&amp; python main.py</code>
      </div>
    );
  }

  const links = Object.keys(capacity);
  const totalCells = links.reduce((s, l) => s + topology.link_assignment[l].length, 0);
  const maxCap = Math.max(...links.map((l) => capacity[l].required_capacity_no_buffer_gbps));

  return (
    <div>
      <div className="page-title">Fronthaul Network Overview</div>
      <div className="page-sub">O-RAN fronthaul TSN — 24 cells across 3 links</div>
      <Pipeline doneCount={cellStats ? 4 : 3} />
      <div className="stat-grid">
        <StatBox label="Total Cells" value={totalCells} color="blue" />
        <StatBox label="Links" value={links.length} color="purple" />
        <StatBox label="Peak Cap Needed" value={fmt2(maxCap)} unit="Gbps (no buffer)" color="red" />
        <StatBox label="Clusters Found" value={topology.clusters.length} color="teal" />
      </div>
      <div className="link-grid">
        {links.map((link) => {
          const cap = capacity[link];
          return (
            <div key={link} className={`link-card ${linkClass(link)}`}>
              <div className="link-card-name">{link}</div>
              <div className="link-cell-list">
                {topology.link_assignment[link].map((c) => (
                  <span key={c} className="cell-chip">Cell {c}</span>
                ))}
              </div>
              <div className="link-metrics">
                <div className="link-metric-item">
                  <div className="mlabel">Avg rate</div>
                  <div className="mval">{fmt2(cap.average_gbps)} Gbps</div>
                </div>
                <div className="link-metric-item">
                  <div className="mlabel">Peak rate</div>
                  <div className="mval">{fmt2(cap.peak_gbps)} Gbps</div>
                </div>
                <div className="link-metric-item">
                  <div className="mlabel">Cap (no buffer)</div>
                  <div className="mval">{fmt2(cap.required_capacity_no_buffer_gbps)} Gbps</div>
                </div>
                <div className="link-metric-item">
                  <div className="mlabel">Cap (4-sym buf)</div>
                  <div className="mval">{fmt2(cap.required_capacity_with_buffer_gbps)} Gbps</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Topology ───────────────────────────────────────────────────────────────
function TopologyTab({ topology }) {
  if (!topology) return <div className="loading-msg"><div className="loading-spinner" /><p>Loading…</p></div>;

  const { link_assignment, clusters, similarity_matrix } = topology;
  const cells = Array.from({ length: 24 }, (_, i) => i + 1);
  const cellLink = {};
  for (const [link, cs] of Object.entries(link_assignment)) {
    cs.forEach((c) => (cellLink[c] = link));
  }

  return (
    <div>
      <div className="page-title">Network Topology</div>
      <div className="page-sub">Link assignment inferred from correlated packet-loss events</div>
      <div className="card">
        <div className="card-title">Cell → Link assignment</div>
        <table className="data-table">
          <thead>
            <tr><th>Cell</th><th>Link</th><th>Cluster</th></tr>
          </thead>
          <tbody>
            {cells.map((c) => {
              const link = cellLink[c] || "—";
              const clusterIdx = clusters.findIndex((cl) => cl.includes(c));
              return (
                <tr key={c}>
                  <td>Cell {c}</td>
                  <td><span className={`badge ${linkClass(link)}`}>{link}</span></td>
                  <td style={{ color: "var(--muted)" }}>Cluster {clusterIdx + 1}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {similarity_matrix && (
        <div className="card">
          <div className="card-title">Jaccard similarity matrix (loss correlation)</div>
          <div className="sim-matrix-wrap">
            <table className="sim-matrix">
              <thead>
                <tr>
                  <th></th>
                  {cells.map((c) => <th key={c}>C{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {cells.map((a) => (
                  <tr key={a}>
                    <th>C{a}</th>
                    {cells.map((b) => {
                      const val = similarity_matrix[a]?.[b] ?? 0;
                      const alpha = Math.round(val * 200);
                      return (
                        <td
                          key={b}
                          title={`C${a}↔C${b}: ${val}`}
                          style={{ background: `rgba(37,99,235,${alpha / 255})` }}
                        />
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ marginTop: 10, fontSize: 11, color: "var(--muted)" }}>
            Darker blue = higher correlation. Cells sharing a link cluster together.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Heatmap ────────────────────────────────────────────────────────────────
function HeatmapTab({ heatmapData, topology }) {
  const [displaySlots, setDisplaySlots] = useState(300);
  if (!heatmapData) return <div className="loading-msg"><div className="loading-spinner" /><p>Loading heatmap…</p></div>;

  const cells = Array.from({ length: 24 }, (_, i) => i + 1);
  const slices = heatmapData.slice(0, displaySlots);
  const cellLink = {};
  if (topology) {
    for (const [link, cs] of Object.entries(topology.link_assignment)) {
      cs.forEach((c) => (cellLink[c] = link));
    }
  }

  return (
    <div>
      <div className="page-title">Traffic Pattern Heatmap</div>
      <div className="page-sub">Per-slot, per-cell — green = OK, red = loss, dark = no traffic</div>
      <div className="controls-row">
        <label style={{ color: "var(--muted)", fontSize: 12 }}>Show slots:</label>
        <select className="ctrl-select" value={displaySlots} onChange={(e) => setDisplaySlots(Number(e.target.value))}>
          {[100, 300, 500, 1000, 2000].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>Total: {heatmapData.length} slots</span>
      </div>
      <div className="card">
        <div className="heatmap-wrap">
          <div className="heatmap-inner">
            {cells.map((cell) => (
              <div key={cell} className="heatmap-row">
                <div className="heatmap-label">
                  Cell {cell}
                  {cellLink[cell] && <span style={{ fontSize: 9, display: "block", color: "var(--muted)" }}>{cellLink[cell]}</span>}
                </div>
                <div className="heatmap-cells">
                  {slices.map((row, i) => (
                    <div
                      key={i}
                      className={`heatmap-cell v${row[`cell${cell}`] ?? 0}`}
                      title={`Slot ${row.slot}: ${["no traffic","ok","loss"][row[`cell${cell}`] ?? 0]}`}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="heatmap-legend">
          <div className="heatmap-legend-item"><div className="dot" style={{ background: "#16a34a" }} />Traffic, no loss</div>
          <div className="heatmap-legend-item"><div className="dot" style={{ background: "#dc2626" }} />Traffic with loss</div>
          <div className="heatmap-legend-item"><div className="dot" style={{ background: "#21262d", border: "1px solid #30363d" }} />No traffic</div>
        </div>
      </div>
    </div>
  );
}

// ── Capacity ───────────────────────────────────────────────────────────────
function CapacityTab({ capacity }) {
  if (!capacity) return <div className="loading-msg"><div className="loading-spinner" /><p>Loading…</p></div>;
  const links = Object.keys(capacity);
  const savingPct = (cap) => {
    const nb = cap.required_capacity_no_buffer_gbps;
    const wb = cap.required_capacity_with_buffer_gbps;
    return nb && wb ? `${(((nb - wb) / nb) * 100).toFixed(1)}%` : "—";
  };

  return (
    <div>
      <div className="page-title">Link Capacity Estimation</div>
      <div className="page-sub">Required Gbps · 1% loss budget · 4-symbol buffer @ leaf switch</div>
      <div className="card">
        <div className="card-title">Results summary</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Link</th><th>Cells</th><th>Avg rate</th><th>Peak rate</th>
              <th>Required (no buf)</th><th>Required (4-sym buf)</th><th>Buffer saving</th>
            </tr>
          </thead>
          <tbody>
            {links.map((link) => {
              const c = capacity[link];
              return (
                <tr key={link}>
                  <td><span className={`badge ${linkClass(link)}`}>{link}</span></td>
                  <td>{c.cells.join(", ")}</td>
                  <td>{fmt2(c.average_gbps)} Gbps</td>
                  <td>{fmt2(c.peak_gbps)} Gbps</td>
                  <td style={{ color: "#f87171" }}>{fmt2(c.required_capacity_no_buffer_gbps)} Gbps</td>
                  <td style={{ color: "#4ade80" }}>{fmt2(c.required_capacity_with_buffer_gbps)} Gbps</td>
                  <td style={{ color: "#facc15" }}>{savingPct(c)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">How the estimate works</div>
        <p style={{ color: "var(--text-dim)", fontSize: 13, lineHeight: 1.7 }}>
          <strong style={{ color: "var(--text)" }}>Without buffer</strong> — 99th-percentile of per-slot aggregate Gbps across all cells on the link (1% of slots allowed to exceed capacity).
        </p>
        <br />
        <p style={{ color: "var(--text-dim)", fontSize: 13, lineHeight: 1.7 }}>
          <strong style={{ color: "var(--text)" }}>With 4-symbol buffer (143 µs)</strong> — leaky-bucket simulation. Excess bits fill the buffer; overflow = drop. Binary-search for minimum rate keeping drops ≤ 1% of traffic slots.
        </p>
      </div>
    </div>
  );
}

// ── Chart.js line chart ────────────────────────────────────────────────────
function LineChart({ data, linkName, capacityNoBuffer, capacityWithBuffer }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current || !data?.length) return;
    if (chartRef.current) chartRef.current.destroy();

    const COLOR_MAP = { Link1: "#2563eb", Link2: "#7c3aed", Link3: "#0891b2" };
    const color = COLOR_MAP[linkName] || "#60a5fa";
    const step = Math.max(1, Math.floor(data.length / 2000));
    const sampled = data.filter((_, i) => i % step === 0);
    const avg = data.reduce((s, d) => s + d.gbps, 0) / data.length;

    chartRef.current = new window.Chart(canvasRef.current, {
      type: "bar",
      data: {
        labels: sampled.map((d) => d.time_s.toFixed(2)),
        datasets: [{
          label: `${linkName} data rate`,
          data: sampled.map((d) => d.gbps),
          backgroundColor: color + "cc",
          borderWidth: 0,
          barPercentage: 1.0,
          categoryPercentage: 1.0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ticks: { color: "#8b949e", maxTicksLimit: 12, font: { size: 10, family: "monospace" } },
            grid: { color: "#21262d" },
            title: { display: true, text: "Time [s]", color: "#8b949e", font: { size: 11 } },
          },
          y: {
            ticks: { color: "#8b949e", font: { size: 10, family: "monospace" } },
            grid: { color: "#21262d" },
            title: { display: true, text: "Data rate [Gbps]", color: "#8b949e", font: { size: 11 } },
          },
        },
      },
      plugins: [{
        id: "hlines",
        afterDraw(chart) {
          const { ctx, scales: { x, y } } = chart;
          const drawLine = (val, clr, lbl) => {
            if (!val) return;
            const yp = y.getPixelForValue(val);
            ctx.save();
            ctx.setLineDash([6, 4]);
            ctx.strokeStyle = clr;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(x.left, yp);
            ctx.lineTo(x.right, yp);
            ctx.stroke();
            ctx.fillStyle = clr;
            ctx.font = "10px monospace";
            ctx.fillText(`${lbl}: ${val.toFixed(2)} Gbps`, x.left + 6, yp - 4);
            ctx.restore();
          };
          drawLine(capacityNoBuffer, "#dc2626", "Cap (no buf)");
          drawLine(capacityWithBuffer, "#16a34a", "Cap (w/ buf)");
          drawLine(avg, "#facc15", "Avg");
        },
      }],
    });

    return () => chartRef.current?.destroy();
  }, [data, linkName, capacityNoBuffer, capacityWithBuffer]);

  return <canvas ref={canvasRef} />;
}

// ── Graphs ─────────────────────────────────────────────────────────────────
function GraphsTab({ graphData, capacity }) {
  const [selectedLink, setSelectedLink] = useState("Link1");
  if (!graphData || !capacity) return <div className="loading-msg"><div className="loading-spinner" /><p>Loading…</p></div>;

  const links = Object.keys(graphData);
  const data = graphData[selectedLink] || [];
  const cap = capacity[selectedLink] || {};

  return (
    <div>
      <div className="page-title">Aggregated Data Rate Graphs</div>
      <div className="page-sub">Per-slot Gbps · dashed lines show required capacity and average</div>
      <div className="controls-row">
        <label style={{ color: "var(--muted)", fontSize: 12 }}>Link:</label>
        <select className="ctrl-select" value={selectedLink} onChange={(e) => setSelectedLink(e.target.value)}>
          {links.map((l) => <option key={l}>{l}</option>)}
        </select>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>
          {data.length} slots · {data.length > 0 ? `${data[data.length - 1].time_s.toFixed(1)}s` : "—"}
        </span>
      </div>
      <div className="card">
        <div className="chart-wrap">
          <LineChart
            data={data}
            linkName={selectedLink}
            capacityNoBuffer={cap.required_capacity_no_buffer_gbps}
            capacityWithBuffer={cap.required_capacity_with_buffer_gbps}
          />
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 20, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, color: "#dc2626" }}>─ ─ Required cap (no buffer)</span>
          <span style={{ fontSize: 12, color: "#16a34a" }}>─ ─ Required cap (4-sym buffer)</span>
          <span style={{ fontSize: 12, color: "#facc15" }}>─ ─ Average data rate</span>
        </div>
      </div>
      <div className="stat-grid" style={{ marginTop: 16 }}>
        <StatBox label="Average" value={fmt2(cap.average_gbps)} unit="Gbps" color="blue" />
        <StatBox label="Peak" value={fmt2(cap.peak_gbps)} unit="Gbps" color="red" />
        <StatBox label="Req. cap (no buf)" value={fmt2(cap.required_capacity_no_buffer_gbps)} unit="Gbps" color="red" />
        <StatBox label="Req. cap (w/ buf)" value={fmt2(cap.required_capacity_with_buffer_gbps)} unit="Gbps" color="green" />
      </div>
    </div>
  );
}

// ── Root ───────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState("Overview");
  const [topology, setTopology] = useState(null);
  const [capacity, setCapacity] = useState(null);
  const [heatmapData, setHeatmapData] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [cellStats, setCellStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [topo, cap] = await Promise.all([
          fetchJSON(PATHS.topology),
          fetchJSON(PATHS.capacity),
        ]);
        setTopology(topo);
        setCapacity(cap);
      } catch (e) {
        setError(e.message);
      }
      fetchJSON(PATHS.heatmap).then(setHeatmapData).catch(() => {});
      fetchJSON(PATHS.graphData).then(setGraphData).catch(() => {});
      fetchJSON(PATHS.cellStats).then(setCellStats).catch(() => {});
    };
    load();
  }, []);

  return (
    <>
      <TopNav tab={tab} setTab={setTab} />
      <main className="page">
        {error && (
          <div className="error-banner">
            <strong>Data not found.</strong> Run the backend pipeline first:
            <code className="run-hint">cd Backend &amp;&amp; python main.py</code>
            <span style={{ color: "var(--muted)", fontSize: 11 }}>({error})</span>
          </div>
        )}
        {tab === "Overview"  && <OverviewTab topology={topology} capacity={capacity} cellStats={cellStats} />}
        {tab === "Topology"  && <TopologyTab topology={topology} />}
        {tab === "Heatmap"   && <HeatmapTab heatmapData={heatmapData} topology={topology} />}
        {tab === "Capacity"  && <CapacityTab capacity={capacity} topology={topology} />}
        {tab === "Graphs"    && <GraphsTab graphData={graphData} capacity={capacity} />}
      </main>
    </>
  );
}