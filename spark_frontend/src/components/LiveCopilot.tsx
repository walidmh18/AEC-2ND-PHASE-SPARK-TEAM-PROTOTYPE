"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

// --- API UTILS ---
export const fetchFMEA = async (data: any) => {
  const res = await fetch("http://127.0.0.1:8080/spark/fmea", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("FMEA fetch failed");
  return res.json();
};

export const fetchSequential = async (x_array: number[], y_array: number[]) => {
  const res = await fetch("http://127.0.0.1:8080/spark/sequential", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current_x: x_array,
      current_y: y_array,
      total_target_points: 15,
    }),
  });
  if (!res.ok) throw new Error("Sequential fetch failed");
  return res.json();
};

export const fetchBayesian = async (x_array: number[], y_array: number[]) => {
  const res = await fetch("http://127.0.0.1:8080/spark/bayesian", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      historical_campaigns: [
        { campaign: "Batch 2023-A", slope: 1.015, intercept: 0.05 },
        { campaign: "Batch 2023-B", slope: 1.020, intercept: 0.04 },
        { campaign: "Batch 2024-A", slope: 1.010, intercept: 0.06 },
      ],
      new_data_x: x_array,
      new_data_y: y_array,
    }),
  });
  if (!res.ok) throw new Error("Bayesian fetch failed");
  return res.json();
};

export const fetchLIMSExport = async (payload: any) => {
  const res = await fetch("http://127.0.0.1:8080/spark/export/lims", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("LIMS export failed");
  return res.blob();
};

// --- COMPONENT ---

interface DataRow {
  id: number;
  x: string;
  y: string;
  locked: boolean;
}

interface LiveCopilotProps {
  onComplete?: (data: any) => void;
}

export default function LiveCopilot({ onComplete }: LiveCopilotProps) {
  const [rows, setRows] = useState<DataRow[]>([
    { id: 1, x: "", y: "", locked: false }
  ]);
  const [probability, setProbability] = useState(0);
  const [isCalculating, setIsCalculating] = useState(false);
  const isStop = probability >= 97.0;
  
  // Bayesian state
  const [bayesianMetrics, setBayesianMetrics] = useState<any>(null);
  const [isBayesianLoading, setIsBayesianLoading] = useState(false);
  
  // LIMS Export state
  const [isLimsSyncing, setIsLimsSyncing] = useState(false);
  const [showToast, setShowToast] = useState(false);

  const activeXInputRef = useRef<HTMLInputElement>(null);
  const lockedRows = rows.filter((r) => r.locked);

  // Focus empty input on row change
  useEffect(() => {
    // Only focus when a new row is spawned (length changes), not on every keystroke.
    if (isStop) return;
    activeXInputRef.current?.focus();
  }, [rows.length, isStop]);

  const runSequentialCheck = async (currentLocked: DataRow[]) => {
    const xArr = currentLocked.map((r) => parseFloat(r.x)).filter((v) => !isNaN(v));
    const yArr = currentLocked.map((r) => parseFloat(r.y)).filter((v) => !isNaN(v));
    
    // Only fetch if there are at least 4 rows to prevent instant 100% on 1 point
    if (xArr.length < 4) return;

    setIsCalculating(true);
    try {
      const result = await fetchSequential(xArr, yArr);
      const prob = result.probability * 100;
      setProbability(prob);

      // Trigger Bayesian handover if threshold met
      if (prob >= 97.0 && !bayesianMetrics) {
        setIsBayesianLoading(true);
        const bayesianResult = await fetchBayesian(xArr, yArr);
        setBayesianMetrics(bayesianResult);
        setIsBayesianLoading(false);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsCalculating(false);
    }
  };

  const handleInputChange = (id: number, field: "x" | "y", value: string) => {
    setRows((prev) =>
      prev.map((row) => (row.id === id ? { ...row, [field]: value } : row))
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, id: number) => {
    if (e.key === "Enter") {
      const targetRow = rows.find((r) => r.id === id);
      if (!targetRow || !targetRow.x || !targetRow.y) return; // Don't lock if empty

      const newRows = rows.map((row) =>
        row.id === id ? { ...row, locked: true } : row
      );
      // Spawn new empty row
      newRows.push({ id: rows.length + 1, x: "", y: "", locked: false });
      
      setRows(newRows);
      runSequentialCheck(newRows.filter((r) => r.locked));
    }
  };

  const handleLimsExport = async () => {
    setIsLimsSyncing(true);
    try {
      const payload = {
        batch_id: "DEMO-BATCH-001",
        analyst_id: "AEC-USER",
        rpn_score: 10,
        fmea_decision: "PLAN RÉDUIT",
        monte_carlo_probability: probability,
        saved_injections: 15 - lockedRows.length,
        bayesian_posterior_slope: bayesianMetrics?.posterior_slope_mean || 1.0,
        bayesian_prior_weight_pct: bayesianMetrics?.prior_influence_pct || 0.0
      };
      
      const blob = await fetchLIMSExport(payload);
      
      // Show Toast
      setShowToast(true);
      setTimeout(() => setShowToast(false), 3000);
      
      // Auto download the CSV
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "lims_export_DEMO-BATCH-001.csv";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLimsSyncing(false);
    }
  };

  const handleComplete = () => {
    if (onComplete) {
      onComplete({
        lockedRows,
        probability,
        bayesianMetrics,
        saved_injections: 15 - lockedRows.length
      });
    }
  };

  // Scatter data prep
  const scatterData = lockedRows
    .map((r) => ({ x: parseFloat(r.x), y: parseFloat(r.y) }))
    .filter((d) => !isNaN(d.x) && !isNaN(d.y));

  return (
    <div className="flex flex-col w-full max-w-[1200px] relative pb-24">
      
      {/* Toast Notification */}
      <div className={`fixed top-6 right-6 bg-surface-2 border border-hairline-strong shadow-lg px-4 py-3 rounded-lg flex items-center gap-3 transition-all duration-300 z-50 ${showToast ? "translate-y-0 opacity-100" : "-translate-y-4 opacity-0 pointer-events-none"}`}>
         <div className="w-5 h-5 rounded-full bg-semantic-success flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
         </div>
         <span className="text-sm font-medium text-ink">Payload delivered to LIMS</span>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 w-full">
        {/* LEFT COLUMN: DATA GRID */}
        <div className="flex-1 bg-surface-1 border border-hairline rounded-xl flex flex-col overflow-hidden max-h-[600px]">
          <div className="p-4 border-b border-hairline bg-surface-2/50 flex items-center justify-between">
            <h2 className="text-sm font-medium tracking-card-title text-ink">Live Telemetry</h2>
            <div className="flex items-center gap-3">
              {isCalculating && <span className="w-2 h-2 rounded-full bg-primary animate-ping"></span>}
              <span className="text-xs font-mono text-ink-subtle">{lockedRows.length} points logged</span>
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto p-0">
            <table className="w-full text-left border-collapse">
              <thead className="text-xs text-ink-subtle sticky top-0 bg-surface-1 border-b border-hairline z-10">
                <tr>
                  <th className="font-medium py-3 px-4 w-[80px]">Inj #</th>
                  <th className="font-medium py-3 px-4">Concentration (X)</th>
                  <th className="font-medium py-3 px-4">Area (Y)</th>
                  <th className="font-medium py-3 px-4 w-[60px]">Status</th>
                </tr>
              </thead>
              <tbody className="text-sm">
                {rows.map((row, idx) => (
                  <tr 
                    key={row.id} 
                    className={`border-b border-hairline-strong/50 tabular-nums ${row.locked ? "text-ink-muted bg-canvas/30" : "bg-surface-2/20"}`}
                  >
                    <td className="py-2.5 px-4 font-mono text-xs">{String(row.id).padStart(3, "0")}</td>
                    <td className="py-2.5 px-4">
                      {row.locked ? (
                        row.x
                      ) : (
                        <input
                          ref={idx === rows.length - 1 ? activeXInputRef : null}
                          type="text"
                          value={row.x}
                          onChange={(e) => handleInputChange(row.id, "x", e.target.value)}
                          onKeyDown={(e) => handleKeyDown(e, row.id)}
                          placeholder="0.0"
                          disabled={isStop}
                          className="bg-canvas border border-hairline-strong focus:border-primary-focus outline-none px-2 py-1 rounded-sm w-[100px] text-ink disabled:opacity-50"
                        />
                      )}
                    </td>
                    <td className="py-2.5 px-4">
                      {row.locked ? (
                        row.y
                      ) : (
                        <input
                          type="text"
                          value={row.y}
                          onChange={(e) => handleInputChange(row.id, "y", e.target.value)}
                          onKeyDown={(e) => handleKeyDown(e, row.id)}
                          placeholder="0.0"
                          disabled={isStop}
                          className="bg-canvas border border-hairline-strong focus:border-primary-focus outline-none px-2 py-1 rounded-sm w-[100px] text-ink disabled:opacity-50"
                        />
                      )}
                    </td>
                    <td className="py-2.5 px-4 flex items-center h-full">
                      {row.locked ? (
                        <svg className="w-4 h-4 text-ink-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
                      ) : (
                        <span className={`w-2 h-2 rounded-full animate-pulse ${isStop ? 'bg-semantic-success' : 'bg-primary'}`}></span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            
            <div className="p-4 text-xs text-ink-subtle font-mono">
              Press &lt;Enter&gt; on active row to lock and transmit
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: ANALYTICS DASHBOARD */}
        <div className="flex-1 flex flex-col gap-6">
          
          {/* The Gauge Card */}
          <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex flex-col items-center justify-center relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
            <h2 className="text-sm font-medium tracking-card-title text-ink-subtle mb-6 self-start">Monte Carlo Copilot</h2>
            
            {/* Custom SVG Half-Circle Gauge */}
            <div className="relative w-[240px] h-[120px] overflow-hidden flex items-end justify-center mb-6">
              {/* Background Track */}
              <div className="absolute w-[240px] h-[240px] rounded-full border-[16px] border-surface-3 top-0"></div>
              
              {/* Value Fill (rotated) */}
              <div 
                className="absolute w-[240px] h-[240px] rounded-full border-[16px] border-b-transparent border-r-transparent top-0 transition-transform duration-700 ease-out"
                style={{ 
                  transform: `rotate(${((probability / 100) * 180) - 45}deg)`,
                  borderColor: isStop ? "#27a644" : "#5e6ad2" // green vs primary lavender
                }}
              ></div>

              {/* Threshold Line at 97% */}
              <div 
                className="absolute w-full h-full top-0 left-0"
                style={{ transform: `rotate(${(0.97 * 180)}deg)` }}
              >
                <div className="absolute top-1/2 left-0 w-[20px] h-[2px] bg-ink-subtle -translate-y-1/2"></div>
              </div>

              {/* Readout */}
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 flex flex-col items-center z-10 pb-2">
                <span className="text-[32px] font-semibold tabular-nums tracking-tighter" style={{ color: isStop ? "#27a644" : "#f7f8f8" }}>
                  {probability.toFixed(1)}%
                </span>
              </div>
            </div>

            {/* Status Pill */}
            <div className="flex flex-col items-center">
              <div 
                className={`
                  px-4 py-1.5 rounded-pill font-bold tracking-widest text-xs uppercase shadow-sm transition-all duration-300 mb-3
                  ${isStop 
                    ? "bg-[#27a644]/20 text-[#27a644] border border-[#27a644]/50 shadow-[0_0_15px_rgba(39,166,68,0.3)]" 
                    : "bg-yellow-500/10 text-yellow-500/90 border border-yellow-500/20"}
                `}
              >
                {isStop ? "Arrêt Positif" : "Continuer"}
              </div>

              {/* Dynamic Injections Metric */}
              <div className="h-6 flex items-center justify-center">
                {isStop ? (
                  <span className="text-[#27a644] font-semibold text-sm tracking-tight shadow-sm drop-shadow-[0_0_8px_rgba(39,166,68,0.4)]">
                    Économie : +{15 - lockedRows.length} Injections
                  </span>
                ) : (
                  <span className="text-ink-subtle text-sm tracking-tight font-medium">
                    Injections effectuées : <span className="text-ink tabular-nums">{lockedRows.length}</span> / 15
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* The Scatter Plot Card */}
          <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex-1 flex flex-col min-h-[250px] relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
            <h2 className="text-sm font-medium tracking-card-title text-ink-subtle mb-4">Linearity Regression</h2>
            
            <div className="flex-1 w-full relative -ml-4">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#23252a" vertical={false} />
                  <XAxis 
                    type="number" 
                    dataKey="x" 
                    name="Concentration" 
                    stroke="#62666d" 
                    tick={{ fill: '#8a8f98', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    domain={['dataMin - 10', 'dataMax + 10']}
                  />
                  <YAxis 
                    type="number" 
                    dataKey="y" 
                    name="Area" 
                    stroke="#62666d" 
                    tick={{ fill: '#8a8f98', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    domain={['dataMin - 10', 'dataMax + 10']}
                  />
                  <Tooltip 
                    cursor={{ strokeDasharray: '3 3', stroke: '#3e3e44' }} 
                    contentStyle={{ backgroundColor: '#0f1011', border: '1px solid #23252a', borderRadius: '6px', fontSize: '12px', color: '#f7f8f8' }}
                    itemStyle={{ color: '#5e6ad2' }}
                  />
                  <Scatter name="Injections" data={scatterData} fill="#5e6ad2" />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* 3. THE HANDOVER UI (Only visible on ARRÊT POSITIF) */}
      {isStop && (
        <div className="mt-8 animate-in fade-in slide-in-from-bottom-4 duration-500 fill-mode-both">
          <div className="flex items-center gap-4 mb-6">
            <div className="h-[1px] flex-1 bg-hairline-strong"></div>
            <h2 className="text-sm font-medium tracking-card-title text-ink-subtle uppercase tracking-widest">Savoir Historique</h2>
            <div className="h-[1px] flex-1 bg-hairline-strong"></div>
          </div>

          {isBayesianLoading ? (
            <div className="flex gap-6 mb-8">
              <div className="h-[100px] flex-1 bg-surface-2/50 animate-pulse rounded-xl border border-hairline"></div>
              <div className="h-[100px] flex-1 bg-surface-2/50 animate-pulse rounded-xl border border-hairline"></div>
            </div>
          ) : bayesianMetrics ? (
            <div className="flex gap-6 mb-8">
              <div className="flex-1 bg-surface-1 border border-hairline rounded-xl p-5 relative overflow-hidden">
                <div className="absolute top-0 left-0 w-1 h-full bg-primary"></div>
                <div className="text-xs text-ink-subtle mb-1">Posterior Slope Mean (Fused)</div>
                <div className="text-[28px] text-ink font-semibold tabular-nums tracking-tight">
                  {bayesianMetrics.posterior_slope_mean.toFixed(4)}
                </div>
              </div>
              <div className="flex-1 bg-surface-1 border border-hairline rounded-xl p-5 relative overflow-hidden">
                <div className="absolute top-0 left-0 w-1 h-full bg-[#27a644]"></div>
                <div className="text-xs text-ink-subtle mb-1">Historical Prior Influence</div>
                <div className="text-[28px] text-ink font-semibold tabular-nums tracking-tight">
                  {bayesianMetrics.prior_influence_pct.toFixed(1)}%
                </div>
              </div>
            </div>
          ) : null}

          {/* Sticky Footer Area */}
          <div className="fixed bottom-6 left-1/2 -translate-x-1/2 w-[calc(100%-48px)] max-w-[1200px] ml-[130px] bg-surface-2/90 backdrop-blur-md border border-hairline-strong rounded-xl p-4 flex items-center justify-between shadow-[0_8px_30px_rgb(0,0,0,0.5)] z-40">
            <div className="flex items-center gap-3">
               <div className="w-8 h-8 rounded-full bg-semantic-success/20 flex items-center justify-center border border-semantic-success/30">
                  <svg className="w-4 h-4 text-semantic-success" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
               </div>
               <div>
                 <div className="text-sm font-medium text-ink">Validation Criteria Met</div>
                 <div className="text-xs text-ink-subtle">Method successfully qualified. Ready for production release.</div>
               </div>
            </div>
            
            <div className="flex items-center gap-3">
              <button 
                onClick={handleLimsExport}
                disabled={isLimsSyncing}
                className="px-4 py-2 text-sm font-medium rounded-md bg-canvas border border-hairline hover:border-hairline-strong transition-colors text-ink shadow-sm flex items-center gap-2 disabled:opacity-70"
              >
                {isLimsSyncing ? (
                   <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                ) : (
                   <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
                )}
                {isLimsSyncing ? "Syncing LIMS..." : "Sync to LIMS"}
              </button>
              <button 
                onClick={handleComplete}
                className="px-5 py-2 text-sm font-medium rounded-md bg-primary hover:bg-primary-hover transition-colors text-white shadow-sm flex items-center gap-2"
              >
                Generate Final Report
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
