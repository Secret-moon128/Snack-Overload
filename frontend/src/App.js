/* app.js — Fronthaul Network Optimizer (FH-OPT)
   Pure React 18 via CDN (no build step needed).
   Reads JSON files from ../backend/data/ (relative to frontend/).
   Uses the native fetch() API — no axios needed.
*/

const { useState, useEffect, useRef, useCallback } = React;

// ── Data paths (adjust if your server serves from a different base) ────────
const DATA_BASE = "../backend/data";
const PATHS = {
  topology:  `${DATA_BASE}/topology_result.json`,
  capacity:  `${DATA_BASE}/capacity_result.json`,
  heatmap:   `${DATA_BASE}/heatmap_data.json`,
  graphData: `${DATA_BASE}/graph_data.json`,
  cellStats: `${DATA_BASE}/cell_stats.json`,
};

// ── Small helpers ──────────────────────────────────────────────────────────
const fmt2 = (n) => (typeof n === "number" ? n.toFixed(2) : "—");
const linkClass = (name) =>
  name === "Link1" ? "link1" : name === "Link2" ? "link2" : "link3";

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${url}`);
  return r.json();
}

// ── Top Navigation ─────────────────────────────────────────────────────────
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
          <button
            key={t}
            className={tab === t ? "active" : ""}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
    </nav>
  );
}

// ── Pipeline progress strip ─────────────────────────────────────────────────
function Pipeline({ loaded }) {
  const steps = [
    { n: 1, label: "Clean data" },
    { n: 2, label: "Topology ID" },
    { n: 3, label: "Capacity est." },
    { n: 4, label: "Aggregation" },
  ];
  const doneCount = Object.values(loaded).filter(Boolean).length;
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

// ── Stat box ───────────────────────────────────────────────────────────────
function StatBox({ label, value, unit, color }) {
  return (
    <div className={`stat-box ${color || ""}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {unit && <div className="unit">{unit}</div>}
    </div>
  );
}

// ── Overview tab ───────────────────────────────────────────────────────────
function OverviewTab({ topology, capacity, cellStats }) {
  if (!topology || !capacity) {
    return (
      <div className="loading-msg">
        <div className="loading-spinner" />
        <p>Run the backend pipeline first, then reload.</p>
        <p style={{ fontSize: 12, marginTop: 8, color: "var(--muted)" }}>
          cd backend &amp;&amp; python main.py
        </p>
      </div>
    );
  }

  const links = Object.keys(capacity);
  const totalCells = links.reduce((s, l) => s + topology.link_assignment[l].length, 0);
  const maxCapNoBuffer = Math.max(
    ...links.map((l) => capacity[l].required_capacity_no_buffer_gbps)
  );

  return (
    <div>
      <div className="page-title">Fronthaul Network Overview</div>
      <div className="page-sub">
        O-RAN fronthaul TSN — 24 cells across 3 links
      </div>

      <Pipeline loaded={{ clean: true, topology: true, capacity: true, agg: !!cellStats }} />

      <div className="stat-grid">
        <StatBox label="Total Cells" value={totalCells} color="blue" />
        <StatBox label="Links" value={links.length} color="purple" />
        <StatBox
          label="Peak Capacity Needed"
          value={fmt2(maxCapNoBuffer)}
          unit="Gbps (no buffer)"
          color="red"
        />
        <StatBox
          label="Clusters Found"
          value={topology.clusters.length}
          color="teal"
        />
      </div>

      <div className="link-grid">
        {links.map((link) => {
          const cap = capacity[link];
          return (
            <div key={link} className={`link-card ${linkClass(link)}`}>
              <div className="link-card-name">{link}</div>
              <div className="link-cell-list">
                {topology.link_assignment[link].map((c) => (
                  <span key={c} className="cell-chip">
                    Cell {c}
                  </span>
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

// ── Topology tab ────────────────────────────────────────────────────────────
function TopologyTab({ topology }) {
  if (!topology) return <div className="loading-msg"><div className="loading-spinner" /><p>Loading…</p></div>;

  const { link_assignment, clusters, similarity_matrix } = topology;
  const cells = Array.from({ length: 24 }, (_, i) => i + 1);

  // Color cells by link
  const cellLink = {};
  for (const [link, cs] of Object.entries(link_assignment)) {
    cs.forEach((c) => (cellLink[c] = link));
  }

  const bgForLink = { Link1: "#1e3a8a", Link2: "#3b0764", Link3: "#164e63" };
  const borderForLink = { Link1: "#2563eb", Link2: "#7c3aed", Link3: "#0891b2" };

  return (
    <div>
      <div className="page-title">Network Topology</div>
      <div className="page-sub">
        Link assignment inferred from correlated packet-loss events
      </div>

      <div className="card">
        <div className="card-title">Cell → Link assignment</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Cell</th>
              <th>Link</th>
              <th>Cluster</th>
            </tr>
          </thead>
          <tbody>
            {cells.map((c) => {
              const link = cellLink[c] || "—";
              const clusterIdx = clusters.findIndex((cl) => cl.includes(c));
              return (
                <tr key={c}>
                  <td>Cell {c}</td>
                  <td>
                    <span className={`badge ${linkClass(link)}`}>{link}</span>
                  </td>
                  <td style={{ color: "var(--muted)" }}>
                    Cluster {clusterIdx + 1}
                  </td>
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
                          style={{
                            background: `rgba(37,99,235,${alpha / 255})`,
                            color: val > 0.5 ? "#fff" : "transparent",
                          }}
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

// ── Heatmap tab ─────────────────────────────────────────────────────────────
function HeatmapTab({ heatmapData, topology }) {
  const [displaySlots, setDisplaySlots] = useState(300);

  if (!heatmapData) return <div className="loading-msg"><div className="loading-spinner" /><p>Loading heatmap…</p></div>;

  const cells = Array.from({ length: 24 }, (_, i) => i + 1);
  const slices = heatmapData.slice(0, displaySlots);

  // Group cells by link for labeling
  const cellLink = {};
  if (topology) {
    for (const [link, cs] of Object.entries(topology.link_assignment)) {
      cs.forEach((c) => (cellLink[c] = link));
    }
  }

  return (
    <div>
      <div className="page-title">Traffic Pattern Heatmap</div>
      <div className="page-sub">
        Per-slot, per-cell view — green = traffic OK, red = packet loss, dark = no traffic
      </div>

      <div className="controls-row">
        <label style={{ color: "var(--muted)", fontSize: 12 }}>Show slots:</label>
        <select
          className="ctrl-select"
          value={displaySlots}
          onChange={(e) => setDisplaySlots(Number(e.target.value))}
        >
          {[100, 300, 500, 1000, 2000].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>
          Total: {heatmapData.length} slots
        </span>
      </div>

      <div className="card">
        <div className="heatmap-wrap">
          <div className="heatmap-inner">
            {cells.map((cell) => (
              <div key={cell} className="heatmap-row">
                <div className="heatmap-label">
                  Cell {cell}
                  {cellLink[cell] && (
                    <span style={{ fontSize: 9, display: "block", color: "var(--muted)" }}>
                      {cellLink[cell]}
                    </span>
                  )}
                </div>
                <div className="heatmap-cells">
                  {slices.map((row, i) => (
                    <div
                      key={i}
                      className={`heatmap-cell v${row[`cell${cell}`] ?? 0}`}
                      title={`Slot ${row.slot}: ${["no traffic", "ok", "loss"][row[`cell${cell}`] ?? 0]}`}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="heatmap-legend">
          <div className="heatmap-legend-item">
            <div className="dot" style={{ background: "#16a34a" }} />
            Traffic, no loss
          </div>
          <div className="heatmap-legend-item">
            <div className="dot" style={{ background: "#dc2626" }} />
            Traffic with loss
          </div>
          <div className="heatmap-legend-item">
            <div className="dot" style={{ background: "#21262d", border: "1px solid #30363d" }} />
            No traffic
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Capacity tab ─────────────────────────────────────────────────────────────
function CapacityTab({ capacity, topology }) {
  if (!capacity) return <div className="loading-msg"><div className="loading-spinner" /><p>Loading…</p></div>;

  const links = Object.keys(capacity);
  const BUFFER_SAVING_PCT = (cap) => {
    const nb = cap.required_capacity_no_buffer_gbps;
    const wb = cap.required_capacity_with_buffer_gbps;
    if (!nb || !wb) return "—";
    return `${(((nb - wb) / nb) * 100).toFixed(1)}%`;
  };

  return (
    <div>
      <div className="page-title">Link Capacity Estimation</div>
      <div className="page-sub">
        Required Gbps for optimum network · 1% packet-loss budget · 4-symbol buffer @ leaf switch
      </div>

      <div className="card">
        <div className="card-title">Results summary</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Link</th>
              <th>Cells</th>
              <th>Avg rate</th>
              <th>Peak rate</th>
              <th>Required (no buf)</th>
              <th>Required (4-sym buf)</th>
              <th>Buffer saving</th>
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
                  <td style={{ color: "#facc15" }}>{BUFFER_SAVING_PCT(c)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">How the estimate works</div>
        <p style={{ color: "var(--text-dim)", fontSize: 13, lineHeight: 1.7 }}>
          <strong style={{ color: "var(--text)" }}>Without buffer</strong> — link rate must absorb
          every burst. We take the 99th-percentile per-slot aggregate data rate across all cells on
          the link (1% loss budget means the top 1% of slots can be dropped).
        </p>
        <br />
        <p style={{ color: "var(--text-dim)", fontSize: 13, lineHeight: 1.7 }}>
          <strong style={{ color: "var(--text)" }}>With 4-symbol buffer</strong> — the leaf switch
          buffer (143 µs = 4 × 35.7 µs) absorbs short bursts. We simulate a leaky-bucket model:
          for each slot, excess bits beyond the link rate flow into the buffer. A slot is a drop
          only when the buffer saturates. We binary-search the minimum link rate that keeps drops
          ≤ 1% of traffic-carrying slots.
        </p>
      </div>
    </div>
  );
}

// ── Line chart component using Chart.js ──────────────────────────────────────
function LineChart({ data, linkName, capacityNoBuffer, capacityWithBuffer }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current || !data?.length) return;

    if (chartRef.current) chartRef.current.destroy();

    const COLOR_MAP = {
      Link1: "#2563eb",
      Link2: "#7c3aed",
      Link3: "#0891b2",
    };
    const color = COLOR_MAP[linkName] || "#60a5fa";

    // Downsample to at most 2000 points for performance
    const step = Math.max(1, Math.floor(data.length / 2000));
    const sampled = data.filter((_, i) => i % step === 0);

    chartRef.current = new Chart(canvasRef.current, {
      type: "bar",
      data: {
        labels: sampled.map((d) => d.time_s.toFixed(2)),
        datasets: [
          {
            label: `${linkName} data rate`,
            data: sampled.map((d) => d.gbps),
            backgroundColor: color + "cc",
            borderWidth: 0,
            barPercentage: 1.0,
            categoryPercentage: 1.0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: "index",
            callbacks: {
              label: (ctx) => ` ${ctx.parsed.y.toFixed(3)} Gbps`,
            },
          },
          annotation: {},
        },
        scales: {
          x: {
            ticks: {
              color: "#8b949e",
              maxTicksLimit: 12,
              font: { size: 10, family: "monospace" },
            },
            grid: { color: "#21262d" },
            title: {
              display: true,
              text: "Time [s]",
              color: "#8b949e",
              font: { size: 11 },
            },
          },
          y: {
            ticks: {
              color: "#8b949e",
              font: { size: 10, family: "monospace" },
            },
            grid: { color: "#21262d" },
            title: {
              display: true,
              text: "Data rate [Gbps]",
              color: "#8b949e",
              font: { size: 11 },
            },
          },
        },
      },
      plugins: [
        {
          id: "hlines",
          afterDraw(chart) {
            const { ctx, scales } = chart;
            const { x, y } = scales;

            const drawHLine = (value, color, label) => {
              if (!value) return;
              const yPos = y.getPixelForValue(value);
              ctx.save();
              ctx.setLineDash([6, 4]);
              ctx.strokeStyle = color;
              ctx.lineWidth = 1.5;
              ctx.beginPath();
              ctx.moveTo(x.left, yPos);
              ctx.lineTo(x.right, yPos);
              ctx.stroke();
              ctx.fillStyle = color;
              ctx.font = "10px monospace";
              ctx.fillText(`${label}: ${value.toFixed(2)} Gbps`, x.left + 6, yPos - 4);
              ctx.restore();
            };

            drawHLine(capacityNoBuffer, "#dc2626", "Cap (no buf)");
            drawHLine(capacityWithBuffer, "#16a34a", "Cap (w/ buf)");

            // Average
            const avg = data.reduce((s, d) => s + d.gbps, 0) / data.length;
            drawHLine(avg, "#facc15", "Avg");
          },
        },
      ],
    });

    return () => chartRef.current?.destroy();
  }, [data, linkName, capacityNoBuffer, capacityWithBuffer]);

  return <canvas ref={canvasRef} />;
}

// ── Graphs tab ──────────────────────────────────────────────────────────────
function GraphsTab({ graphData, capacity }) {
  const [selectedLink, setSelectedLink] = useState("Link1");

  if (!graphData || !capacity) {
    return <div className="loading-msg"><div className="loading-spinner" /><p>Loading graph data…</p></div>;
  }

  const links = Object.keys(graphData);
  const data = graphData[selectedLink] || [];
  const cap = capacity[selectedLink] || {};

  return (
    <div>
      <div className="page-title">Aggregated Data Rate Graphs</div>
      <div className="page-sub">
        Per-slot Gbps · dashed lines show required capacity and average rate
      </div>

      <div className="controls-row">
        <label style={{ color: "var(--muted)", fontSize: 12 }}>Link:</label>
        <select
          className="ctrl-select"
          value={selectedLink}
          onChange={(e) => setSelectedLink(e.target.value)}
        >
          {links.map((l) => <option key={l}>{l}</option>)}
        </select>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>
          {data.length} slots ·{" "}
          {data.length > 0
            ? `${data[data.length - 1].time_s.toFixed(1)}s`
            : "—"}
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
          <span style={{ fontSize: 12, color: "#dc2626" }}>
            ─ ─ Required FH capacity (no buffer)
          </span>
          <span style={{ fontSize: 12, color: "#16a34a" }}>
            ─ ─ Required FH capacity (4-sym buffer)
          </span>
          <span style={{ fontSize: 12, color: "#facc15" }}>
            ─ ─ Average data rate
          </span>
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

// ── Root App ──────────────────────────────────────────────────────────────────
function App() {
  const [tab, setTab] = useState("Overview");

  const [topology, setTopology] = useState(null);
  const [capacity, setCapacity] = useState(null);
  const [heatmapData, setHeatmapData] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [cellStats, setCellStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Load data files on mount. Missing files = backend not run yet, show instructions.
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

      // Non-critical loads
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
          <div
            style={{
              background: "rgba(220,38,38,.1)",
              border: "1px solid rgba(220,38,38,.3)",
              borderRadius: 6,
              padding: "12px 16px",
              marginBottom: 20,
              fontSize: 13,
              color: "#fca5a5",
            }}
          >
            <strong>Data not found.</strong> Run the backend pipeline first:
            <br />
            <code
              style={{
                display: "block",
                marginTop: 6,
                fontFamily: "monospace",
                color: "#e2e8f0",
              }}
            >
              cd backend &amp;&amp; python main.py
            </code>
            <span style={{ color: "var(--muted)", fontSize: 11, marginTop: 4, display: "block" }}>
              ({error})
            </span>
          </div>
        )}

        {tab === "Overview" && (
          <OverviewTab topology={topology} capacity={capacity} cellStats={cellStats} />
        )}
        {tab === "Topology" && <TopologyTab topology={topology} />}
        {tab === "Heatmap" && (
          <HeatmapTab heatmapData={heatmapData} topology={topology} />
        )}
        {tab === "Capacity" && (
          <CapacityTab capacity={capacity} topology={topology} />
        )}
        {tab === "Graphs" && (
          <GraphsTab graphData={graphData} capacity={capacity} />
        )}
      </main>
    </>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);