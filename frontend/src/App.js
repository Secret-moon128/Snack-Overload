import { useState, useEffect, useRef, useCallback } from "react";
import "./App.css";

const API = "http://localhost:5050/api";

async function get(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

async function post(path) {
  const r = await fetch(API + path, { method: "POST" });
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

const fmt2  = (n) => (typeof n === "number" ? n.toFixed(2) : "—");
const fmtT  = (n) => (typeof n === "number" ? n.toFixed(3) : "—");
const lClass = (n) => n === "Link1" ? "link1" : n === "Link2" ? "link2" : "link3";

// ─────────────────────────────────────────────────────────────────────────────
// NAV
// ─────────────────────────────────────────────────────────────────────────────
function Nav({ tab, setTab, running, lastRun }) {
  const tabs = ["Overview","Topology","Heatmap","Capacity","Graphs"];
  return (
    <nav className="nav">
      <div className="nav-brand">
        <span className="nav-pulse" />
        FH‑OPT
        <span style={{fontSize:11,color:"var(--text-mute)",fontWeight:400,marginLeft:4}}>
          Fronthaul Optimizer
        </span>
      </div>
      <div className="nav-tabs">
        {tabs.map(t => (
          <button key={t} className={tab===t?"active":""} onClick={()=>setTab(t)}>{t}</button>
        ))}
      </div>
      <div className="nav-right">
        {running && <span className="live-badge"><span className="live-dot"/>Analysing…</span>}
        {!running && lastRun && (
          <span style={{fontSize:11,color:"var(--text-mute)"}}>Last run {lastRun}</span>
        )}
      </div>
    </nav>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// STAT BOX
// ─────────────────────────────────────────────────────────────────────────────
function Stat({ label, value, unit, color }) {
  return (
    <div className={`stat-box ${color||""}`}>
      <div className="s-label">{label}</div>
      <div className="s-value">{value}</div>
      {unit && <div className="s-unit">{unit}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PIPELINE PROGRESS
// ─────────────────────────────────────────────────────────────────────────────
function PipelineProgress({ status }) {
  const steps = ["Clean data","Topology ID","Capacity est.","Aggregation"];
  const cur   = status?.step ?? 0;
  const pct   = Math.min(100, Math.round((cur / 4) * 100));

  return (
    <div className="progress-wrap">
      <div className="progress-title">
        <span>
          {status?.step_name === "error"
            ? "❌  Error during analysis"
            : cur === 5
            ? "✅  Analysis complete"
            : `Running: ${status?.step_name || "…"}`}
        </span>
        <span style={{color:"var(--accent)",fontFamily:"var(--mono)"}}>{pct}%</span>
      </div>
      <div style={{marginBottom:14}}>
        <div className="progress-bar-track">
          <div className="progress-bar-fill" style={{width:`${pct}%`}}/>
        </div>
      </div>
      <div className="progress-steps">
        {steps.map((s, i) => {
          const done   = cur > i + 1 || cur === 5;
          const active = cur === i + 1 && status?.running;
          return (
            <div key={s} className={`progress-step${done?" done":active?" active":""}`}>
              <div className="picon">{done ? "✓" : active ? "◌" : i+1}</div>
              <span>{s}</span>
              {done && <span style={{marginLeft:"auto",fontSize:11,color:"var(--green)"}}>done</span>}
              {active && <span style={{marginLeft:"auto",fontSize:11,color:"var(--accent)"}}>running…</span>}
            </div>
          );
        })}
      </div>
      {status?.error && (
        <div style={{marginTop:14,padding:"10px 14px",background:"rgba(239,68,68,.1)",
          border:"1px solid rgba(239,68,68,.2)",borderRadius:6,
          fontSize:12,color:"#fca5a5",fontFamily:"var(--mono)"}}>
          {status.error}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// OVERVIEW
// ─────────────────────────────────────────────────────────────────────────────
function Overview({ topology, capacity, status, onRun }) {
  const running = status?.running;
  const showProgress = running || (status?.step > 0 && status?.step < 5);
  const hasResults   = status?.has_results;

  if (!hasResults && !showProgress) {
    return (
      <div>
        <div className="page-header">
          <div className="page-title">Fronthaul Network Optimizer</div>
          <div className="page-sub">O-RAN TSN · 24 cells · 3 fronthaul links · Intelligent topology & capacity analysis</div>
        </div>

        <div className="hero">
          <div className="hero-icon">📡</div>
          <h2>Ready to Analyse</h2>
          <p>Run the full pipeline to identify network topology and estimate required link capacities from your historical traffic data.</p>

          <div className="hero-steps">
            {["Clean .dat files","Correlate packet loss","Estimate capacity","Build visualisations"].map((s,i) => (
              <div key={s} className="hero-step">
                <span className="snum">{i+1}</span>
                {s}
              </div>
            ))}
          </div>

          <button className="btn btn-primary" style={{fontSize:15,padding:"12px 32px"}} onClick={onRun} disabled={running}>
            {running ? "⏳  Running…" : "▶  Start Analysis"}
          </button>
          <div style={{marginTop:16,fontSize:12,color:"var(--text-mute)"}}>
            Make sure .dat files are in <code style={{fontFamily:"var(--mono)"}}>Backend/data/</code>
          </div>
        </div>
      </div>
    );
  }

  if (showProgress) {
    return (
      <div>
        <div className="page-header">
          <div className="page-title">Running Analysis…</div>
          <div className="page-sub">Processing 24 cells across all 4 pipeline stages</div>
        </div>
        <PipelineProgress status={status} />
      </div>
    );
  }

  // ── Results view ───────────────────────────────────────────────
  const links = topology ? Object.keys(topology.link_assignment) : [];
  const totalCells = links.reduce((s,l) => s + (topology?.link_assignment[l]?.length||0), 0);
  const maxCap = capacity
    ? Math.max(...links.map(l => capacity[l]?.required_capacity_no_buffer_gbps || 0))
    : 0;
  const maxCapBuf = capacity
    ? Math.max(...links.map(l => capacity[l]?.required_capacity_with_buffer_gbps || 0))
    : 0;

  return (
    <div>
      <div className="page-header" style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",flexWrap:"wrap",gap:12}}>
        <div>
          <div className="page-title">Fronthaul Network Overview</div>
          <div className="page-sub">O-RAN fronthaul TSN — {totalCells} cells across {links.length} links</div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onRun} disabled={running}>
          🔄  Re-run Analysis
        </button>
      </div>

      <div className="stat-grid">
        <Stat label="Total Cells"      value={totalCells}        color="blue"   />
        <Stat label="Links"            value={links.length}      color="purple" />
        <Stat label="Clusters Found"   value={topology?.clusters?.length ?? "—"} color="teal" />
        <Stat label="Peak Cap (no buf)" value={fmt2(maxCap)}     unit="Gbps"    color="red"   />
        <Stat label="Peak Cap (w/ buf)" value={fmt2(maxCapBuf)}  unit="Gbps"    color="green" />
        <Stat label="Buffer Saving"
          value={maxCap > 0 ? `${(((maxCap-maxCapBuf)/maxCap)*100).toFixed(1)}%` : "—"}
          color="yellow" />
      </div>

      <div className="link-grid">
        {links.map(link => {
          const cap   = capacity?.[link] || {};
          const cells = topology?.link_assignment[link] || [];
          return (
            <div key={link} className={`link-card ${lClass(link)}`}>
              <div className="lc-header">
                <div className="lc-name">{link}</div>
                <div className="lc-cell-count">{cells.length} cells</div>
              </div>
              <div className="cell-chips">
                {cells.map(c => <span key={c} className="cell-chip">Cell {c}</span>)}
              </div>
              <div className="lc-metrics">
                <div className="lc-metric">
                  <div className="mlabel">Avg rate</div>
                  <div className="mval">{fmt2(cap.average_gbps)} <span style={{fontSize:11,color:"var(--text-mute)"}}>Gbps</span></div>
                </div>
                <div className="lc-metric">
                  <div className="mlabel">Peak rate</div>
                  <div className="mval">{fmt2(cap.peak_gbps)} <span style={{fontSize:11,color:"var(--text-mute)"}}>Gbps</span></div>
                </div>
                <div className="lc-metric">
                  <div className="mlabel">Cap (no buffer)</div>
                  <div className="mval" style={{color:"#fca5a5"}}>{fmt2(cap.required_capacity_no_buffer_gbps)} <span style={{fontSize:11}}>Gbps</span></div>
                </div>
                <div className="lc-metric">
                  <div className="mlabel">Cap (4-sym buf)</div>
                  <div className="mval" style={{color:"#86efac"}}>{fmt2(cap.required_capacity_with_buffer_gbps)} <span style={{fontSize:11}}>Gbps</span></div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TOPOLOGY
// ─────────────────────────────────────────────────────────────────────────────
function Topology({ topology }) {
  if (!topology) return <div className="empty-state"><div className="spinner"/><p>Run analysis first</p></div>;
  const { link_assignment, clusters, similarity_matrix } = topology;
  const cells = Array.from({length:24},(_,i)=>i+1);
  const cellLink = {};
  for (const [link,cs] of Object.entries(link_assignment)) cs.forEach(c => cellLink[c]=link);

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Network Topology</div>
        <div className="page-sub">Cell → link assignment derived from correlated packet-loss events (Jaccard similarity clustering)</div>
      </div>

      <div className="link-grid" style={{marginBottom:24}}>
        {Object.entries(link_assignment).map(([link,cs]) => (
          <div key={link} className={`link-card ${lClass(link)}`}>
            <div className="lc-header">
              <div className="lc-name">{link}</div>
              <div className="lc-cell-count">{cs.length} cells</div>
            </div>
            <div className="cell-chips">
              {cs.map(c => <span key={c} className="cell-chip">Cell {c}</span>)}
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Cell → Link Table</div>
        <table className="data-table">
          <thead><tr><th>Cell</th><th>Assigned Link</th><th>Cluster #</th></tr></thead>
          <tbody>
            {cells.map(c => {
              const link = cellLink[c]||"—";
              const ci   = clusters.findIndex(cl=>cl.includes(c));
              return (
                <tr key={c}>
                  <td>Cell {c}</td>
                  <td><span className={`badge ${lClass(link)}`}>{link}</span></td>
                  <td style={{color:"var(--text-mute)"}}>Cluster {ci+1}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {similarity_matrix && (
        <div className="card">
          <div className="card-title">Jaccard Similarity Matrix — Loss Correlation</div>
          <p style={{fontSize:12,color:"var(--text-mute)",marginBottom:12}}>
            Darker blue = higher correlation. Cells on the same link cluster together in the bottom-right diagonal blocks.
          </p>
          <div className="sim-wrap">
            <table className="sim-table">
              <thead>
                <tr>
                  <th></th>
                  {cells.map(c=><th key={c}>C{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {cells.map(a=>(
                  <tr key={a}>
                    <td>C{a}</td>
                    {cells.map(b=>{
                      const v = similarity_matrix[a]?.[b]??0;
                      return (
                        <td key={b} title={`C${a}↔C${b}: ${v}`}
                          style={{background:`rgba(59,130,246,${v*0.9})`,
                            outline: a===b?"1px solid rgba(59,130,246,.3)":"none"}}/>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// HEATMAP
// ─────────────────────────────────────────────────────────────────────────────
function Heatmap({ topology }) {
  const [heatmap, setHeatmap]   = useState(null);
  const [slots, setSlots]       = useState(400);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    setLoading(true);
    get("/heatmap").then(d => { setHeatmap(d); setLoading(false); }).catch(()=>setLoading(false));
  }, []);

  if (loading) return <div className="empty-state"><div className="spinner"/><p>Loading heatmap…</p></div>;
  if (!heatmap) return <div className="empty-state"><p>Run analysis first to see the heatmap.</p></div>;

  const cells   = Array.from({length:24},(_,i)=>i+1);
  const slices  = heatmap.slice(0, slots);
  const cellLink={};
  if (topology) for (const [link,cs] of Object.entries(topology.link_assignment)) cs.forEach(c=>cellLink[c]=link);

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Traffic Pattern Heatmap</div>
        <div className="page-sub">Per-slot, per-cell view — identifies cells sharing a link by correlated red bursts</div>
      </div>

      <div className="controls-row">
        <span className="ctrl-label">Slots shown:</span>
        <select className="ctrl-sel" value={slots} onChange={e=>setSlots(Number(e.target.value))}>
          {[100,200,400,800,1500,2000].map(n=><option key={n} value={n}>{n}</option>)}
        </select>
        <span style={{fontSize:12,color:"var(--text-mute)"}}>of {heatmap.length} total slots</span>
      </div>

      <div className="card">
        <div className="heatmap-scroll">
          <div className="heatmap-rows">
            {cells.map(cell => (
              <div key={cell} className="heatmap-row">
                <div className="hm-label">
                  Cell {cell}
                  {cellLink[cell] && <div className="lk">{cellLink[cell]}</div>}
                </div>
                <div className="hm-cells">
                  {slices.map((row,i) => (
                    <div key={i}
                      className={`hm-cell v${row[`cell${cell}`]??0}`}
                      title={`Slot ${row.slot}: ${["no traffic","ok","loss"][row[`cell${cell}`]??0]}`}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="hm-legend">
          <div className="hm-legend-item"><div className="sq" style={{background:"#16a34a"}}/>Traffic — no loss</div>
          <div className="hm-legend-item"><div className="sq" style={{background:"#dc2626"}}/>Traffic — packet loss</div>
          <div className="hm-legend-item"><div className="sq" style={{background:"#1e293b",border:"1px solid #334155"}}/>No traffic</div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CAPACITY
// ─────────────────────────────────────────────────────────────────────────────
function Capacity({ capacity }) {
  if (!capacity) return <div className="empty-state"><p>Run analysis first.</p></div>;
  const links = Object.keys(capacity);

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Link Capacity Estimation</div>
        <div className="page-sub">Minimum required Ethernet rate · 1% packet-loss budget · 4-symbol buffer @ leaf switch</div>
      </div>

      <div className="link-grid">
        {links.map(link => {
          const c  = capacity[link];
          const nb = c.required_capacity_no_buffer_gbps;
          const wb = c.required_capacity_with_buffer_gbps;
          const saving = nb > 0 ? (((nb-wb)/nb)*100).toFixed(1) : "—";
          return (
            <div key={link} className={`link-card ${lClass(link)}`} style={{padding:"22px 24px"}}>
              <div className="lc-header">
                <div className="lc-name">{link}</div>
                <div className="lc-cell-count">cells: {c.cells?.join(", ")}</div>
              </div>
              <div className="lc-metrics" style={{gridTemplateColumns:"1fr 1fr",gap:14,marginTop:4}}>
                <div className="lc-metric">
                  <div className="mlabel">Average rate</div>
                  <div className="mval">{fmt2(c.average_gbps)} <small>Gbps</small></div>
                </div>
                <div className="lc-metric">
                  <div className="mlabel">Peak rate</div>
                  <div className="mval">{fmt2(c.peak_gbps)} <small>Gbps</small></div>
                </div>
                <div className="lc-metric">
                  <div className="mlabel">Required (no buffer)</div>
                  <div className="mval" style={{color:"#fca5a5",fontSize:20}}>{fmt2(nb)} <small>Gbps</small></div>
                </div>
                <div className="lc-metric">
                  <div className="mlabel">Required (4-sym buf)</div>
                  <div className="mval" style={{color:"#86efac",fontSize:20}}>{fmt2(wb)} <small>Gbps</small></div>
                </div>
              </div>
              <div style={{marginTop:14,paddingTop:14,borderTop:"1px solid var(--border)",
                display:"flex",alignItems:"center",justifyContent:"space-between"}}>
                <span style={{fontSize:12,color:"var(--text-mute)"}}>Buffer saving</span>
                <span style={{fontFamily:"var(--mono)",fontSize:15,fontWeight:700,color:"#fcd34d"}}>
                  {saving !== "—" ? `${saving}%` : "—"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="card">
        <div className="card-title">Full Comparison Table</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Link</th><th>Cells</th>
              <th>Avg (Gbps)</th><th>Peak (Gbps)</th>
              <th>Cap no-buf (Gbps)</th><th>Cap w/-buf (Gbps)</th><th>Saving</th>
            </tr>
          </thead>
          <tbody>
            {links.map(link => {
              const c  = capacity[link];
              const nb = c.required_capacity_no_buffer_gbps;
              const wb = c.required_capacity_with_buffer_gbps;
              return (
                <tr key={link}>
                  <td><span className={`badge ${lClass(link)}`}>{link}</span></td>
                  <td>{c.cells?.join(", ")}</td>
                  <td>{fmt2(c.average_gbps)}</td>
                  <td>{fmt2(c.peak_gbps)}</td>
                  <td style={{color:"#fca5a5"}}>{fmt2(nb)}</td>
                  <td style={{color:"#86efac"}}>{fmt2(wb)}</td>
                  <td style={{color:"#fcd34d"}}>{nb>0?`${(((nb-wb)/nb)*100).toFixed(1)}%`:"—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-title">Methodology</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:20}}>
          <div>
            <div style={{fontWeight:600,marginBottom:6,color:"var(--text)"}}>Without buffer</div>
            <p style={{fontSize:13,color:"var(--text-dim)",lineHeight:1.7}}>
              Link rate must absorb every burst with no smoothing. We take the <strong>99th-percentile</strong> of
              per-slot aggregate Gbps (1% loss budget = top 1% of traffic slots may be dropped).
            </p>
          </div>
          <div>
            <div style={{fontWeight:600,marginBottom:6,color:"var(--text)"}}>With 4-symbol buffer (143 µs)</div>
            <p style={{fontSize:13,color:"var(--text-dim)",lineHeight:1.7}}>
              Leaf-switch buffer absorbs short bursts via a <strong>leaky-bucket model</strong>.
              Excess bits per slot fill the buffer; a slot is a drop only when the buffer overflows.
              Binary-search finds the minimum rate keeping drops ≤ 1%.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CHART (Chart.js)
// ─────────────────────────────────────────────────────────────────────────────
function LinkChart({ link, capacity }) {
  const canvasRef = useRef(null);
  const chartRef  = useRef(null);
  const [data, setData]     = useState([]);
  const [loading,setLoading]= useState(true);

  useEffect(() => {
    setLoading(true);
    get(`/graph/${link}`).then(d=>{setData(d);setLoading(false);}).catch(()=>setLoading(false));
  }, [link]);

  useEffect(() => {
    if (!canvasRef.current || !data?.length) return;
    if (chartRef.current) chartRef.current.destroy();

    const COLOR = {Link1:"#3b82f6",Link2:"#8b5cf6",Link3:"#06b6d4"};
    const col   = COLOR[link]||"#3b82f6";
    const step  = Math.max(1, Math.floor(data.length/2000));
    const pts   = data.filter((_,i)=>i%step===0);
    const avg   = data.reduce((s,d)=>s+d.gbps,0)/data.length;
    const nb    = capacity?.[link]?.required_capacity_no_buffer_gbps;
    const wb    = capacity?.[link]?.required_capacity_with_buffer_gbps;

    chartRef.current = new window.Chart(canvasRef.current, {
      type: "bar",
      data: {
        labels: pts.map(d=>d.time_s.toFixed(2)),
        datasets: [{
          label:`${link} Gbps`,
          data: pts.map(d=>d.gbps),
          backgroundColor: col+"bb",
          borderWidth:0,
          barPercentage:1.0,
          categoryPercentage:1.0,
        }],
      },
      options: {
        responsive:true, maintainAspectRatio:false, animation:false,
        plugins:{ legend:{display:false} },
        scales:{
          x:{
            ticks:{color:"#475569",maxTicksLimit:12,font:{size:10,family:"monospace"}},
            grid:{color:"#1a2235"},
            title:{display:true,text:"Time [s]",color:"#64748b",font:{size:11}},
          },
          y:{
            ticks:{color:"#475569",font:{size:10,family:"monospace"}},
            grid:{color:"#1a2235"},
            title:{display:true,text:"Data rate [Gbps]",color:"#64748b",font:{size:11}},
          },
        },
      },
      plugins:[{
        id:"hlines",
        afterDraw(chart){
          const {ctx,scales:{x,y}}=chart;
          const line=(val,clr,lbl)=>{
            if(!val) return;
            const yp=y.getPixelForValue(val);
            ctx.save();
            ctx.setLineDash([7,4]);
            ctx.strokeStyle=clr; ctx.lineWidth=1.8;
            ctx.beginPath(); ctx.moveTo(x.left,yp); ctx.lineTo(x.right,yp); ctx.stroke();
            ctx.fillStyle=clr; ctx.font="bold 10px monospace";
            ctx.fillText(`${lbl}: ${val.toFixed(2)} Gbps`, x.left+8, yp-5);
            ctx.restore();
          };
          line(nb,"#ef4444","Cap (no buf)");
          line(wb,"#22c55e","Cap (w/ buf)");
          line(avg,"#f59e0b","Average");
        },
      }],
    });

    return () => chartRef.current?.destroy();
  }, [data, link, capacity]);

  if (loading) return <div className="empty-state"><div className="spinner"/>Loading graph…</div>;
  if (!data.length) return <div className="empty-state"><p>No graph data for {link}.</p></div>;

  return <canvas ref={canvasRef}/>;
}

// ─────────────────────────────────────────────────────────────────────────────
// GRAPHS
// ─────────────────────────────────────────────────────────────────────────────
function Graphs({ capacity }) {
  const [selLink, setSelLink] = useState("Link1");
  const links = capacity ? Object.keys(capacity) : ["Link1","Link2","Link3"];
  const cap   = capacity?.[selLink]||{};

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Aggregated Data Rate</div>
        <div className="page-sub">Per-slot Gbps over the full 60-second window · dashed lines show capacity thresholds</div>
      </div>

      <div className="controls-row">
        <span className="ctrl-label">Link:</span>
        {links.map(l=>(
          <button key={l}
            className={`btn btn-sm ${selLink===l?"btn-primary":"btn-ghost"}`}
            onClick={()=>setSelLink(l)}>
            {l}
          </button>
        ))}
      </div>

      <div className="card">
        <div className="chart-wrap">
          <LinkChart link={selLink} capacity={capacity}/>
        </div>
        <div style={{display:"flex",gap:20,marginTop:14,flexWrap:"wrap"}}>
          <span style={{fontSize:12,color:"#ef4444"}}>─ ─ Required cap (no buffer)</span>
          <span style={{fontSize:12,color:"#22c55e"}}>─ ─ Required cap (4-sym buffer)</span>
          <span style={{fontSize:12,color:"#f59e0b"}}>─ ─ Average data rate</span>
        </div>
      </div>

      <div className="stat-grid" style={{marginTop:16}}>
        <Stat label="Average"           value={fmt2(cap.average_gbps)}                       unit="Gbps" color="blue"  />
        <Stat label="Peak"              value={fmt2(cap.peak_gbps)}                          unit="Gbps" color="red"   />
        <Stat label="Req cap (no buf)"  value={fmt2(cap.required_capacity_no_buffer_gbps)}   unit="Gbps" color="red"   />
        <Stat label="Req cap (w/ buf)"  value={fmt2(cap.required_capacity_with_buffer_gbps)} unit="Gbps" color="green" />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ROOT APP
// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  const [tab,      setTab]     = useState("Overview");
  const [status,   setStatus]  = useState(null);
  const [topology, setTopo]    = useState(null);
  const [capacity, setCap]     = useState(null);
  const [apiErr,   setApiErr]  = useState(false);
  const pollRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await get("/status");
      setStatus(s);
      setApiErr(false);
      if (s.has_results) {
        if (!topology) get("/topology").then(setTopo).catch(()=>{});
        if (!capacity) get("/capacity").then(setCap).catch(()=>{});
      }
      // re-fetch results after analysis completes
      if (s.step === 5) {
        get("/topology").then(setTopo).catch(()=>{});
        get("/capacity").then(setCap).catch(()=>{});
      }
    } catch {
      setApiErr(true);
    }
  }, [topology, capacity]);

  // Poll every second
  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, 1000);
    return () => clearInterval(pollRef.current);
  }, [fetchStatus]);

  const handleRun = async () => {
    try {
      await post("/run");
      setTopo(null); setCap(null);
      fetchStatus();
    } catch(e) {
      alert("Could not start analysis. Is the backend server running?\n\ncd Backend && pip install flask flask-cors && python server.py");
    }
  };

  return (
    <>
      <Nav tab={tab} setTab={setTab} running={status?.running} lastRun={status?.last_run}/>

      <main className="page">
        {apiErr && (
          <div className="error-banner">
            <strong>Cannot reach the backend API.</strong>
            Start the server first:
            <code className="run-hint">cd Backend &amp;&amp; pip install flask flask-cors &amp;&amp; python server.py</code>
            <span style={{fontSize:11,color:"var(--text-mute)"}}>Then reload this page.</span>
          </div>
        )}

        {tab==="Overview"  && <Overview  topology={topology} capacity={capacity} status={status} onRun={handleRun}/>}
        {tab==="Topology"  && <Topology  topology={topology}/>}
        {tab==="Heatmap"   && <Heatmap   topology={topology}/>}
        {tab==="Capacity"  && <Capacity  capacity={capacity}/>}
        {tab==="Graphs"    && <Graphs    capacity={capacity}/>}
      </main>
    </>
  );
}