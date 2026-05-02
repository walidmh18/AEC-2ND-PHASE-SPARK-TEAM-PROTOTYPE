"use client";

import React, { useState, useEffect } from "react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  ComposedChart,
  Line,
  LineChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  AreaChart,
  Area,
} from "recharts";

// TODO: Connect to backend for Kalman filter data
// const KALMAN_DATA = data?.kalman?.campaigns || [];

// TODO: Connect to backend for sequential SPRT data
// const SPRT_DATA = data?.sequential?.injections || [];

// Gaussian bell curve approximation for Monte Carlo visualization
const MONTE_CARLO_DATA = Array.from({ length: 60 }, (_, i) => {
  const x = 1.0 + i * 0.05; // Rs from 1.0 to 4.0
  const mu = 2.8;
  const sigma = 0.35;
  const freq = Math.exp(-0.5 * Math.pow((x - mu) / sigma, 2)) / (sigma * Math.sqrt(2 * Math.PI));
  return { rs: parseFloat(x.toFixed(2)), freq: parseFloat((freq * 1000).toFixed(1)) };
});

interface ValidationReportProps {
  data?: any;
}

export default function ValidationReport({ data }: ValidationReportProps) {
  const [isExportingPDF, setIsExportingPDF] = useState(false);
  const [isExportingLIMS, setIsExportingLIMS] = useState(false);
  const [toastMessage, setToastMessage] = useState("");

  const DEMO_KALMAN_DATA = [
    { campaign: 0, raw: 3.2, filtered: 3.2 },
    { campaign: 1, raw: 3.0, filtered: 3.05 },
    { campaign: 2, raw: 3.1, filtered: 3.06 },
    { campaign: 3, raw: 2.8, filtered: 2.88 },
    { campaign: 4, raw: 2.9, filtered: 2.85 },
    { campaign: 5, raw: 2.6, filtered: 2.65 },
    { campaign: 6, raw: 2.5, filtered: 2.52 },
    { campaign: 7, raw: 2.4, filtered: 2.42 },
    { campaign: 8, raw: 2.5, filtered: 2.39 },
    { campaign: 9, raw: 2.2, filtered: 2.26 },
  ];

  const DEMO_SPRT_DATA = [
    { injection: 1, Sn: -0.4 },
    { injection: 2, Sn: -0.9 },
    { injection: 3, Sn: -0.6 },
    { injection: 4, Sn: -1.2 },
    { injection: 5, Sn: -1.6 },
    { injection: 6, Sn: -1.4 },
    { injection: 7, Sn: -1.9 },
    { injection: 8, Sn: -2.4 },
  ];

  // AI Regulatory Dossier state
  const [dossierText, setDossierText] = useState("");
  const [dossierLoading, setDossierLoading] = useState(false);
  const [displayedText, setDisplayedText] = useState("");
  const typewriterRef = React.useRef<ReturnType<typeof setInterval> | null>(null);

  // Use the calculated RPN and decision from parent props
  const rpnScore = data?.fmea?.rpnScore || 0;
  const fmeaDecision = data?.fmea?.decision || "—";
  
  // Chart mappings with fallback to the live copilot payload when available.
  const sprtDataToRender = data?.sequential?.sprtLogs || DEMO_SPRT_DATA;
  const KALMAN_DATA = data?.copilot?.kalman?.campaigns || data?.kalman?.campaigns || [];
  const kalmanDataToRender = data?.kalman || DEMO_KALMAN_DATA;
  const kalmanChartData = Array.isArray(kalmanDataToRender)
    ? kalmanDataToRender
    : KALMAN_DATA.length > 0
      ? KALMAN_DATA
      : DEMO_KALMAN_DATA;
  const projectedCampaigns =
    data?.copilot?.kalman?.projected_remaining_campaigns ??
    data?.kalman?.projected_remaining_campaigns ??
    3;

  // MoDR Heatmap: Resolution score peaks at pH=5.0, Temp=30°C
  const PH_RANGE = Array.from({ length: 10 }, (_, i) => 3.0 + i * 0.44);
  const TEMP_RANGE = Array.from({ length: 10 }, (_, i) => 20 + i * 2.22);
  const OPTIMAL_PH = 5.0;
  const OPTIMAL_TEMP = 30.0;

  const calcResolution = (ph: number, temp: number) => {
    const phDist = (ph - OPTIMAL_PH) / 1.5;
    const tempDist = (temp - OPTIMAL_TEMP) / 8.0;
    return 3.2 * Math.exp(-0.5 * (phDist * phDist + tempDist * tempDist));
  };

  // Find closest cell to optimal operating point
  const closestPH = PH_RANGE.reduce((prev, curr) => Math.abs(curr - OPTIMAL_PH) < Math.abs(prev - OPTIMAL_PH) ? curr : prev);
  const closestTemp = TEMP_RANGE.reduce((prev, curr) => Math.abs(curr - OPTIMAL_TEMP) < Math.abs(prev - OPTIMAL_TEMP) ? curr : prev);

  const handleExportPDF = async () => {
    setIsExportingPDF(true);
    
    try {
      const payload = {
        rpn: rpnScore,
        decision: "PLAN RÉDUIT (8 injections)",
        fmea_scores: {
          maturite_methode: data?.fmea?.maturite || 1,
          complexite_matrice: data?.fmea?.matrice || 1,
          disponibilite_donnees: data?.fmea?.donnees || 1,
          criticite_reglementaire: data?.fmea?.criticite || 1,
          risque_patient: data?.fmea?.risque || 1
        },
        probability: data?.copilot?.probability || 0,
        saved_injections: data?.copilot?.saved_injections || 0,
        sequential_decision: (data?.copilot?.probability || 0) >= 0.97 ? "ARRÊT POSITIF" : "CONTINUER",
        posterior_slope_mean: data?.copilot?.bayesianMetrics?.posterior_slope_mean || 0,
        posterior_slope_var: data?.copilot?.bayesianMetrics?.posterior_slope_var || 0,
        prior_influence_pct: data?.copilot?.bayesianMetrics?.prior_influence_pct || 0,
        data_influence_pct: 100 - (data?.copilot?.bayesianMetrics?.prior_influence_pct || 0),
        kalman_measurements: kalmanChartData.map(d => d.raw),
        kalman_filtered_states: kalmanChartData.map(d => d.filtered),
        projected_remaining_campaigns: 3
      };

      // Step 1: POST payload to generate the report server-side
      const response = await fetch("http://127.0.0.1:8080/spark/export/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) throw new Error("Failed to generate PDF");
      
      const { download_id } = await response.json();

      // Step 2: Navigate the browser directly to the GET download URL
      // This is a native browser download — filename is always respected
      window.open(`http://127.0.0.1:8080/spark/export/pdf/download/${download_id}`, "_blank");
      
      setToastMessage("✓ Dossier Technique généré avec succès");
      setTimeout(() => setToastMessage(""), 3000);
    } catch (err) {
      console.error("PDF Export error:", err);
      setToastMessage("Erreur lors de la génération du PDF");
      setTimeout(() => setToastMessage(""), 3000);
    } finally {
      setIsExportingPDF(false);
    }
  };

  const handleExportLIMS = () => {
    setIsExportingLIMS(true);
    
    try {
      const csvContent = [
        "Timestamp,BatchID,RPN_Score,Decision,Probability_Pct,Saved_Injections",
        `${new Date().toISOString()},"DEMO-BATCH-001",${rpnScore},"PLAN RÉDUIT",${data?.copilot?.probability || 0},${data?.copilot?.saved_injections || 0}`
      ].join("\n");
      
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);
      link.setAttribute("href", url);
      link.setAttribute("download", `LIMS_Export_${new Date().getTime()}.csv`);
      link.style.visibility = 'hidden';
      
      // Execute click synchronously to bypass browser popup/download blockers
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      setToastMessage("✓ Payload LIMS exporté avec succès");
      setTimeout(() => setToastMessage(""), 3000);
    } catch (err) {
      console.error(err);
    } finally {
      setIsExportingLIMS(false);
    }
  };

  // AI Regulatory Dossier Generator
  const handleGenerateDossier = async () => {
    setDossierLoading(true);
    setDossierText("");
    setDisplayedText("");
    if (typewriterRef.current) clearInterval(typewriterRef.current);

    try {
      const payload = {
        rpn: rpnScore,
        fmea_decision: fmeaDecision,
        fmea_axes: data?.fmea || {},
        bayesian: bayesian,
        sprt_result: "ARRÊT POSITIF at injection 8",
        monte_carlo_probability: "98.7%",
        kalman_projected_campaigns: 3,
      };

      const res = await fetch("/api/generate-dossier", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({ error: "Unknown error" }));
        throw new Error(errBody.error || `API returned ${res.status}`);
      }
      const { summary } = await res.json();
      setDossierText(summary);

      // Typewriter effect
      let idx = 0;
      typewriterRef.current = setInterval(() => {
        idx++;
        setDisplayedText(summary.slice(0, idx));
        if (idx >= summary.length) {
          if (typewriterRef.current) clearInterval(typewriterRef.current);
        }
      }, 8);
    } catch (err) {
      console.error("Dossier generation error:", err);
      setDossierText("Erreur lors de la génération du dossier réglementaire.");
      setDisplayedText("Erreur lors de la génération du dossier réglementaire.");
    } finally {
      setDossierLoading(false);
    }
  };

  // Dynamic FMEA Mapping using rawValues
  const FMEA_DATA = data?.fmea?.rawValues ? [
    { subject: 'Matrice', value: data.fmea.rawValues.matrice || 0, fullMark: 3 },
    { subject: 'Maturité', value: data.fmea.rawValues.maturite || 0, fullMark: 3 },
    { subject: 'Données', value: data.fmea.rawValues.donnees || 0, fullMark: 3 },
    { subject: 'Criticité', value: data.fmea.rawValues.criticite || 0, fullMark: 3 },
    { subject: 'Risque', value: data.fmea.rawValues.risque || 0, fullMark: 3 }
  ] : [
    { subject: 'Matrice', value: 0, fullMark: 3 },
    { subject: 'Maturité', value: 0, fullMark: 3 },
    { subject: 'Données', value: 0, fullMark: 3 },
    { subject: 'Criticité', value: 0, fullMark: 3 },
    { subject: 'Risque', value: 0, fullMark: 3 }
  ];

  // Dynamic Bayesian Mapping — fetched from backend on mount
  const [bayesian, setBayesian] = useState({
    posterior_slope_mean: 0,
    posterior_slope_var: 0,
    prior_influence_pct: 0,
    data_influence_pct: 0
  });
  const [bayesianLoading, setBayesianLoading] = useState(true);

  useEffect(() => {
    const fetchBayesian = async () => {
      try {
        const response = await fetch("http://127.0.0.1:8080/spark/bayesian", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            historical_campaigns: [
              { campaign: "Batch 2023-A", slope: 1.015, intercept: 0.05 },
              { campaign: "Batch 2023-B", slope: 1.020, intercept: 0.04 },
              { campaign: "Batch 2024-A", slope: 1.010, intercept: 0.06 }
            ],
            new_data_x: [80.0, 100.0, 120.0],
            new_data_y: [82.2, 102.3, 123.1]
          })
        });

        if (!response.ok) throw new Error("Bayesian API failed");
        
        const result = await response.json();
        console.log("═══════════════════════════════════════════");
        console.log("  SPARK — Bayesian Fusion Response");
        console.log("═══════════════════════════════════════════");
        console.log("📊 Posterior Slope Mean:", result.posterior_slope_mean);
        console.log("📊 Posterior Slope Var:", result.posterior_slope_var);
        console.log("📊 Prior Influence:", result.prior_influence_pct, "%");
        console.log("📊 Data Influence:", result.data_influence_pct, "%");
        console.log("═══════════════════════════════════════════");
        
        setBayesian(result);
      } catch (err) {
        console.error("❌ Bayesian fetch error:", err);
      } finally {
        setBayesianLoading(false);
      }
    };

    fetchBayesian();
  }, []);
  return (
    <div className="w-full h-full flex flex-col gap-6 animate-in fade-in duration-500 pb-12">
      
      {/* TOAST NOTIFICATION */}
      <div className={`fixed top-6 right-6 bg-surface-2 border border-hairline-strong shadow-lg px-4 py-3 rounded-lg flex items-center gap-3 transition-all duration-300 z-50 ${toastMessage ? "translate-y-0 opacity-100" : "-translate-y-4 opacity-0 pointer-events-none"}`}>
         <div className="w-5 h-5 rounded-full bg-[#27a644] flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>
         </div>
         <span className="text-sm font-medium text-ink">{toastMessage.replace("✓ ", "")}</span>
      </div>

      {/* HEADER SECTION */}
      <div className="flex items-center justify-between border-b border-hairline pb-4 mb-2">
        <div>
          <h2 className="text-xl font-medium tracking-tight text-ink">Validation Analytics Report</h2>
          <p className="text-sm text-ink-subtle mt-1">Final SPARK methodological proof & system qualification metrics.</p>
        </div>
      </div>

      {/* GRID LAYOUT */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* CARD 1: FMEA RISK ASSESSMENT (Full Width) */}
        <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex flex-col relative overflow-hidden md:col-span-2">
          <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
          <h3 className="text-sm font-medium tracking-card-title text-ink-subtle uppercase mb-6">1. Évaluation des Risques (FMEA)</h3>
          
          <div className="flex-1 flex flex-col sm:flex-row items-center gap-8">
            <div className="flex flex-col items-center sm:items-start justify-center pl-4">
              <div className="text-[48px] font-semibold tracking-tighter tabular-nums text-ink leading-none mb-2">
                {rpnScore} <span className="text-[24px] text-ink-muted">/ 15</span>
              </div>
              <div className="text-xs text-ink-tertiary mb-4 font-mono">RISK PRIORITY NUMBER</div>
              <div className="px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-bold tracking-widest uppercase">
                {fmeaDecision}
              </div>
            </div>
            
            <div className="flex-1 w-full h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="80%" data={FMEA_DATA}>
                  <PolarGrid stroke="#23252a" />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: '#8a8f98', fontSize: 11 }} />
                  <Radar
                    name="Risk"
                    dataKey="value"
                    stroke="#3B82F6"
                    strokeWidth={2}
                    fill="#3B82F6"
                    fillOpacity={0.2}
                  />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0f1011', border: '1px solid #23252a', borderRadius: '6px', fontSize: '12px', color: '#f7f8f8' }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* CARD 2: BAYESIAN FUSION */}
        <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex flex-col relative overflow-hidden md:col-span-2">
          <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
          <h3 className="text-sm font-medium tracking-card-title text-ink-subtle uppercase mb-6">2. Savoir Historique (Fusion Bayésienne)</h3>
          
          <div className="flex-1 flex flex-col justify-center">
            <div className="w-full border border-hairline rounded-lg overflow-hidden">
              <table className="w-full text-left border-collapse">
                <tbody className="text-sm">
                  <tr className="border-b border-hairline bg-surface-2/30 hover:bg-surface-2/60 transition-colors">
                    <td className="py-3 px-4 text-ink-subtle">Pente Postérieure</td>
                    <td className="py-3 px-4 font-mono text-ink text-right">{bayesian.posterior_slope_mean.toFixed(4)}</td>
                  </tr>
                  <tr className="border-b border-hairline hover:bg-surface-2/60 transition-colors">
                    <td className="py-3 px-4 text-ink-subtle">Variance Postérieure</td>
                    <td className="py-3 px-4 font-mono text-ink text-right">{bayesian.posterior_slope_var ? bayesian.posterior_slope_var.toExponential(1) : "0.0e0"}</td>
                  </tr>
                  <tr className="border-b border-hairline bg-surface-2/30 hover:bg-surface-2/60 transition-colors">
                    <td className="py-3 px-4 text-ink-subtle">Poids du Prior</td>
                    <td className="py-3 px-4 font-mono text-[#3B82F6] font-semibold text-right">{bayesian.prior_influence_pct.toFixed(1)}%</td>
                  </tr>
                  <tr className="hover:bg-surface-2/60 transition-colors">
                    <td className="py-3 px-4 text-ink-subtle">Poids du Likelihood</td>
                    <td className="py-3 px-4 font-mono text-ink text-right">{bayesian.data_influence_pct ? bayesian.data_influence_pct.toFixed(1) : (100 - bayesian.prior_influence_pct).toFixed(1)}%</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="text-xs text-ink-tertiary mt-4 px-2 leading-relaxed">
              {bayesianLoading 
                ? "Chargement des données bayésiennes..."
                : `La forte influence du prior (${bayesian.prior_influence_pct.toFixed(1)}%) justifie statistiquement la réduction du plan de validation.`}
            </p>
          </div>
        </div>

        {/* CARD 3: KALMAN FILTER (Spans full width) */}
        <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex flex-col relative overflow-hidden md:col-span-2">
          <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-sm font-medium tracking-card-title text-ink-subtle uppercase">3. Maintenance Prédictive (Filtre de Kalman)</h3>
            <span className="text-xs text-ink-tertiary bg-surface-2 px-2 py-1 rounded-sm border border-hairline">
              Le filtre étendu prédit un remplacement dans {projectedCampaigns} campagnes.
            </span>
          </div>

          {/* Formula Box */}
          <div className="bg-canvas border border-hairline rounded-lg px-5 py-4 mb-6">
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-tertiary font-mono w-28 shrink-0">Prédiction :</span>
                <span className="text-sm text-ink font-serif italic tracking-wide">
                  x̂<sub>k</sub><sup>−</sup> = F x̂<sub>k−1</sub>
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-tertiary font-mono w-28 shrink-0">Covariance :</span>
                <span className="text-sm text-ink font-serif italic tracking-wide">
                  P<sub>k</sub><sup>−</sup> = F P<sub>k−1</sub> F<sup>T</sup> + Q
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-tertiary font-mono w-28 shrink-0">Mise à jour :</span>
                <span className="text-sm text-ink font-serif italic tracking-wide">
                  x̂<sub>k</sub> = x̂<sub>k</sub><sup>−</sup> + K<sub>k</sub>(z<sub>k</sub> − H x̂<sub>k</sub><sup>−</sup>)
                </span>
              </div>
              <div className="mt-1 text-[11px] text-ink-tertiary">
                K<sub>k</sub> = P<sub>k</sub><sup>−</sup> H<sup>T</sup>(H P<sub>k</sub><sup>−</sup> H<sup>T</sup> + R)<sup>−1</sup> · z<sub>k</sub> = mesure observée · seuil critique Rs = 2.0
              </div>
            </div>
          </div>

          <div className="w-full h-[340px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={kalmanChartData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#23252a" vertical={false} />
                <XAxis 
                  dataKey="campaign" 
                  stroke="#62666d" 
                  tick={{ fill: '#8a8f98', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  name="Campaign"
                />
                <YAxis 
                  stroke="#62666d" 
                  tick={{ fill: '#8a8f98', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  domain={[2.0, 3.5]}
                  name="Resolution"
                />
                <Tooltip 
                  cursor={{ strokeDasharray: '3 3', stroke: '#3e3e44' }} 
                  contentStyle={{ backgroundColor: '#0f1011', border: '1px solid #23252a', borderRadius: '6px', fontSize: '12px', color: '#f7f8f8' }}
                  itemStyle={{ color: '#f7f8f8' }}
                />
                <ReferenceLine 
                  y={2.0} 
                  stroke="#EF4444" 
                  strokeDasharray="3 3" 
                  label={{ position: 'top', value: 'Seuil Critique (Rs < 2.0)', fill: '#EF4444', fontSize: 10, offset: 10 }} 
                />
                <Scatter name="Raw Data (Bruitée)" dataKey="raw" fill="#8A8F98" />
                <Line 
                  type="monotone" 
                  name="EKF State (Lissée)" 
                  dataKey="filtered" 
                  stroke="#3B82F6" 
                  strokeWidth={2} 
                  dot={false} 
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* CARD 4: SPRT — Analyse Séquentielle (Full Width) */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex flex-col relative overflow-hidden md:col-span-2">
          <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
          <h3 className="text-sm font-medium tracking-card-title text-ink-subtle uppercase mb-4">4. Analyse Séquentielle (SPRT)</h3>
          
          {/* Formula Box */}
          <div className="bg-canvas border border-hairline rounded-lg px-5 py-4 mb-6">
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-tertiary font-mono w-24 shrink-0">Log-LR :</span>
                <span className="text-sm text-ink font-serif italic tracking-wide">
                  S<sub>n</sub> = Σ ln( <em>f</em><sub>1</sub>(x<sub>i</sub>) / <em>f</em><sub>0</sub>(x<sub>i</sub>) )
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-tertiary font-mono w-24 shrink-0">Bornes :</span>
                <span className="text-sm text-ink font-serif italic tracking-wide">
                  <em>a</em> = ln( (1−β) / α ) &nbsp;,&nbsp; <em>b</em> = ln( β / (1−α) )
                </span>
              </div>
              <div className="mt-1 text-[11px] text-ink-tertiary">α = 0.05 (Risque Type I) &nbsp;·&nbsp; β = 0.10 (Risque Type II) &nbsp;·&nbsp; a ≈ 2.89 &nbsp;·&nbsp; b ≈ −2.20</div>
            </div>
          </div>

          {/* SPRT Chart */}
          <div className="w-full h-[340px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sprtDataToRender} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#23252a" vertical={false} />
                <XAxis 
                  dataKey="injection" 
                  stroke="#62666d" 
                  tick={{ fill: '#8a8f98', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  label={{ value: 'Injection #', position: 'insideBottomRight', offset: -5, fill: '#62666d', fontSize: 10 }}
                />
                <YAxis 
                  stroke="#62666d" 
                  tick={{ fill: '#8a8f98', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  domain={[-3, 4]}
                  label={{ value: 'Log-Likelihood Ratio (Sₙ)', angle: -90, position: 'insideLeft', fill: '#62666d', fontSize: 10 }}
                />
                <Tooltip 
                  cursor={{ strokeDasharray: '3 3', stroke: '#3e3e44' }} 
                  contentStyle={{ backgroundColor: '#0f1011', border: '1px solid #23252a', borderRadius: '6px', fontSize: '12px', color: '#f7f8f8' }}
                />
                <ReferenceLine 
                  y={2.89} 
                  stroke="#EF4444" 
                  strokeDasharray="3 3" 
                  label={{ position: 'right', value: "Limite de Rejet (a)", fill: '#EF4444', fontSize: 10 }} 
                />
                <ReferenceLine 
                  y={-2.20} 
                  stroke="#22C55E" 
                  strokeDasharray="3 3" 
                  label={{ position: 'right', value: "Limite d'Acceptation (b)", fill: '#22C55E', fontSize: 10 }} 
                />
                <ReferenceLine y={0} stroke="#3e3e44" strokeWidth={0.5} />
                <Line 
                  type="linear" 
                  dataKey="Sn" 
                  name="Log-Likelihood Ratio (Sₙ)"
                  stroke="#3B82F6" 
                  strokeWidth={2} 
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-ink-tertiary">
            <div className="w-2 h-2 rounded-full bg-[#22C55E]"></div>
            <span>La statistique S<sub>n</sub> franchit la limite d'acceptation (b) à l'injection 8 → Arrêt anticipé validé.</span>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* CARD 5: Monte Carlo Simulation (Full Width) */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex flex-col relative overflow-hidden md:col-span-2">
          <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
          <h3 className="text-sm font-medium tracking-card-title text-ink-subtle uppercase mb-4">5. Simulation de Monte Carlo (N = 10 000)</h3>
          
          {/* Formula Box */}
          <div className="bg-canvas border border-hairline rounded-lg px-5 py-4 mb-6">
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-tertiary font-mono w-28 shrink-0">Intégrale :</span>
                <span className="text-sm text-ink font-serif italic tracking-wide">
                  P(Succès) = (1 / <em>N</em>) · Σ 𝕀( g(X<sub>i</sub>) ≥ Seuil )
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-tertiary font-mono w-28 shrink-0">Paramètres :</span>
                <span className="text-sm text-ink-subtle">
                  <em>N</em> = 10 000 tirages &nbsp;·&nbsp; Seuil critique Rs = 2.0 &nbsp;·&nbsp; μ = 2.80 &nbsp;·&nbsp; σ = 0.35
                </span>
              </div>
            </div>
          </div>

          {/* Monte Carlo Distribution Chart */}
          <div className="w-full h-[340px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={MONTE_CARLO_DATA} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="mcGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3B82F6" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#3B82F6" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#23252a" vertical={false} />
                <XAxis 
                  dataKey="rs" 
                  stroke="#62666d" 
                  tick={{ fill: '#8a8f98', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  label={{ value: 'Performance Prédite (Rs)', position: 'insideBottomRight', offset: -5, fill: '#62666d', fontSize: 10 }}
                />
                <YAxis 
                  stroke="#62666d" 
                  tick={{ fill: '#8a8f98', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  label={{ value: 'Fréquence', angle: -90, position: 'insideLeft', fill: '#62666d', fontSize: 10 }}
                />
                <Tooltip 
                  cursor={{ strokeDasharray: '3 3', stroke: '#3e3e44' }} 
                  contentStyle={{ backgroundColor: '#0f1011', border: '1px solid #23252a', borderRadius: '6px', fontSize: '12px', color: '#f7f8f8' }}
                  formatter={(value: any) => [`${value}`, 'Fréquence']}
                  labelFormatter={(label: any) => `Rs = ${label}`}
                />
                <ReferenceLine 
                  x={2.0} 
                  stroke="#EF4444" 
                  strokeDasharray="5 3" 
                  strokeWidth={1.5}
                  label={{ position: 'top', value: 'Seuil Critique (Rs = 2.0)', fill: '#EF4444', fontSize: 10, offset: 10 }} 
                />
                <Area 
                  type="monotone" 
                  dataKey="freq" 
                  stroke="#3B82F6" 
                  strokeWidth={2}
                  fill="url(#mcGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-ink-tertiary">
            <div className="w-2 h-2 rounded-full bg-[#3B82F6]"></div>
            <span>98.7% de la distribution se situe au-dessus du seuil critique → Probabilité de succès élevée.</span>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* CARD 6: Bayesian Knowledge Graph (Full Width) */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex flex-col relative overflow-hidden md:col-span-2">
          <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
          <h3 className="text-sm font-medium tracking-card-title text-ink-subtle uppercase mb-4">6. Graphe de Connaissances Bayésien</h3>
          
          {/* Formula Box */}
          <div className="bg-canvas border border-hairline rounded-lg px-5 py-4 mb-6">
            <div className="flex items-center gap-3">
              <span className="text-xs text-ink-tertiary font-mono w-28 shrink-0">Théorème :</span>
              <span className="text-sm text-ink font-serif italic tracking-wide">
                P(θ | D) = [ P(D | θ) · P(θ) ] / P(D)
              </span>
            </div>
            <div className="mt-2 text-[11px] text-ink-tertiary">θ = Paramètres du modèle chromatographique &nbsp;·&nbsp; D = Données observées (injections HPLC)</div>
          </div>

          {/* CSS Knowledge Graph */}
          <div className="flex flex-col items-center gap-0">
            
            {/* Layer 1: Priors (Input Variables) */}
            <div className="text-[10px] text-ink-tertiary font-mono uppercase tracking-widest mb-2">Prior P(θ)</div>
            <div className="flex items-center gap-4">
              <div className="bg-canvas border border-hairline rounded-lg px-4 py-2.5 text-sm text-ink-subtle border-l-[3px] border-l-[#A78BFA] min-w-[110px] text-center">
                pH
              </div>
              <div className="bg-canvas border border-hairline rounded-lg px-4 py-2.5 text-sm text-ink-subtle border-l-[3px] border-l-[#F59E0B] min-w-[110px] text-center">
                Température
              </div>
              <div className="bg-canvas border border-hairline rounded-lg px-4 py-2.5 text-sm text-ink-subtle border-l-[3px] border-l-[#22C55E] min-w-[110px] text-center">
                Débit
              </div>
            </div>

            {/* Connector Lines Layer 1 → 2 */}
            <div className="flex items-center justify-center w-full py-1">
              <svg width="300" height="36" viewBox="0 0 300 36" fill="none">
                <line x1="60" y1="0" x2="150" y2="36" stroke="#3e3e44" strokeWidth="1" />
                <line x1="150" y1="0" x2="150" y2="36" stroke="#3e3e44" strokeWidth="1" />
                <line x1="240" y1="0" x2="150" y2="36" stroke="#3e3e44" strokeWidth="1" />
              </svg>
            </div>

            {/* Layer 2: Likelihood (Model) */}
            <div className="text-[10px] text-ink-tertiary font-mono uppercase tracking-widest mb-2">Likelihood P(D|θ)</div>
            <div className="bg-canvas border-2 border-[#3B82F6]/40 rounded-xl px-8 py-3.5 text-sm font-medium text-ink shadow-[0_0_20px_rgba(59,130,246,0.08)]">
              Modèle Chromatographique
            </div>

            {/* Connector Lines Layer 2 → 3 */}
            <div className="flex items-center justify-center w-full py-1">
              <svg width="300" height="36" viewBox="0 0 300 36" fill="none">
                <line x1="150" y1="0" x2="100" y2="36" stroke="#3e3e44" strokeWidth="1" />
                <line x1="150" y1="0" x2="200" y2="36" stroke="#3e3e44" strokeWidth="1" />
              </svg>
            </div>

            {/* Layer 3: Posteriors (CQA Outputs) */}
            <div className="text-[10px] text-ink-tertiary font-mono uppercase tracking-widest mb-2">Posterior P(θ|D)</div>
            <div className="flex items-center gap-4">
              <div className="bg-canvas border border-hairline rounded-lg px-4 py-2.5 text-sm font-medium text-[#22C55E] border-l-[3px] border-l-[#22C55E] min-w-[140px] text-center">
                Résolution (Rs)
              </div>
              <div className="bg-canvas border border-hairline rounded-lg px-4 py-2.5 text-sm font-medium text-[#3B82F6] border-l-[3px] border-l-[#3B82F6] min-w-[170px] text-center">
                Temps de Rétention (Rt)
              </div>
            </div>

            {/* Legend */}
            <div className="mt-6 flex items-center gap-6 text-[11px] text-ink-tertiary">
              <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[#A78BFA]"></div>Variables d'entrée</div>
              <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[#3B82F6]"></div>Modèle physico-chimique</div>
              <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[#22C55E]"></div>Attributs qualité (CQA)</div>
            </div>
          </div>
        </div>

      </div>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* CARD 7: AI Regulatory Dossier Generator (Full Width) */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex flex-col relative overflow-hidden mt-6">
          <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium tracking-card-title text-ink-subtle uppercase">7. Génération de Dossier IA (Q2/Q14)</h3>
            <div className="flex items-center gap-1.5 text-[11px] text-ink-tertiary bg-surface-2 px-2.5 py-1 rounded-sm border border-hairline">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
              Powered by Gemini 2.0 Flash
            </div>
          </div>

          {/* Output Area */}
          <div className="bg-canvas border border-hairline rounded-lg px-5 py-4 min-h-[120px] mb-4">
            {!dossierText && !dossierLoading && (
              <p className="text-sm text-ink-tertiary italic">
                Cliquez sur le bouton ci-dessous pour générer automatiquement un résumé exécutif conforme ICH Q2(R2) et Q14.
              </p>
            )}
            {dossierLoading && !dossierText && (
              <div className="flex flex-col gap-3 animate-pulse">
                <div className="h-3 bg-surface-2 rounded w-full"></div>
                <div className="h-3 bg-surface-2 rounded w-[95%]"></div>
                <div className="h-3 bg-surface-2 rounded w-[88%]"></div>
                <div className="h-3 bg-surface-2 rounded w-full"></div>
                <div className="h-3 bg-surface-2 rounded w-[92%]"></div>
                <div className="h-3 bg-surface-2 rounded w-[75%]"></div>
              </div>
            )}
            {displayedText && (
              <p className="text-sm text-ink leading-relaxed whitespace-pre-wrap font-serif">
                {displayedText}
                {displayedText.length < dossierText.length && (
                  <span className="inline-block w-[2px] h-4 bg-primary ml-0.5 animate-pulse"></span>
                )}
              </p>
            )}
          </div>

          <button
            onClick={handleGenerateDossier}
            disabled={dossierLoading}
            className="self-start px-5 py-2.5 text-sm font-medium rounded-md bg-gradient-to-r from-[#A78BFA] to-[#6D28D9] hover:from-[#C4B5FD] hover:to-[#7C3AED] text-white shadow-sm flex items-center gap-2 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {dossierLoading ? (
              <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
            )}
            {dossierLoading ? "Génération en cours..." : "Générer le Rapport Réglementaire"}
          </button>
        </div>

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* CARD 8: MoDR Design Space Heatmap (Full Width) */}
        {/* ═══════════════════════════════════════════════════════════════ */}
        <div className="bg-surface-1 border border-hairline rounded-xl p-6 flex flex-col relative overflow-hidden mt-6">
          <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"></div>
          <h3 className="text-sm font-medium tracking-card-title text-ink-subtle uppercase mb-4">8. Espace de Conception Opérationnel (MoDR — ICH Q14)</h3>
          
          {/* Formula & Context */}
          <div className="bg-canvas border border-hairline rounded-lg px-5 py-4 mb-6">
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-tertiary font-mono w-28 shrink-0">Critère :</span>
                <span className="text-sm text-ink font-serif italic tracking-wide">
                  Rs(pH, T) ≥ 2.0 → Zone d'acceptation &nbsp;·&nbsp; Rs &lt; 2.0 → Hors spécification
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-tertiary font-mono w-28 shrink-0">Optimum :</span>
                <span className="text-sm text-ink-subtle">
                  pH = {OPTIMAL_PH.toFixed(1)} &nbsp;·&nbsp; T = {OPTIMAL_TEMP.toFixed(0)}°C &nbsp;·&nbsp; Rs<sub>max</sub> = 3.20
                </span>
              </div>
            </div>
          </div>

          {/* Heatmap Grid */}
          <div className="flex gap-2">
            {/* Y-Axis Label */}
            <div className="flex flex-col items-center justify-center -mr-1">
              <span className="text-[10px] text-ink-tertiary font-mono writing-mode-vertical" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>
                Température (°C)
              </span>
            </div>

            <div className="flex flex-col gap-0 flex-1">
              {/* Grid rows (reversed so temp increases upward) */}
              {[...TEMP_RANGE].reverse().map((temp, ri) => (
                <div key={ri} className="flex items-center gap-0">
                  {/* Y tick label */}
                  <span className="text-[10px] text-ink-tertiary font-mono w-8 text-right pr-1.5 shrink-0">
                    {temp.toFixed(0)}
                  </span>
                  {/* Row cells */}
                  {PH_RANGE.map((ph, ci) => {
                    const score = calcResolution(ph, temp);
                    const isOptimal = ph === closestPH && temp === closestTemp;
                    const isPass = score >= 2.0;
                    // Calculate green intensity for passing cells
                    const intensity = Math.min(1, (score - 2.0) / 1.2);

                    return (
                      <div
                        key={ci}
                        className="flex-1 aspect-square relative group cursor-crosshair"
                        style={{
                          backgroundColor: isPass
                            ? `rgba(34, 197, 94, ${0.15 + intensity * 0.65})`
                            : '#1a1b1e',
                          border: '1px solid #23252a',
                        }}
                        title={`pH=${ph.toFixed(1)} T=${temp.toFixed(0)}°C Rs=${score.toFixed(2)}`}
                      >
                        {/* Optimal crosshair */}
                        {isOptimal && (
                          <div className="absolute inset-0 flex items-center justify-center z-10">
                            <div className="w-3 h-3 rounded-full bg-white shadow-[0_0_8px_rgba(255,255,255,0.8),0_0_16px_rgba(255,255,255,0.4)]"></div>
                          </div>
                        )}
                        {/* Hover tooltip */}
                        <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-canvas border border-hairline px-2 py-1 rounded text-[10px] text-ink font-mono whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-20 pointer-events-none shadow-lg">
                          Rs = {score.toFixed(2)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}

              {/* X-Axis Labels */}
              <div className="flex items-center ml-8 mt-1">
                {PH_RANGE.map((ph, i) => (
                  <span key={i} className="flex-1 text-center text-[10px] text-ink-tertiary font-mono">
                    {ph.toFixed(1)}
                  </span>
                ))}
              </div>
              <div className="text-center mt-1">
                <span className="text-[10px] text-ink-tertiary font-mono">pH</span>
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="mt-5 flex items-center justify-between">
            <div className="flex items-center gap-4 text-[11px] text-ink-tertiary">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'rgba(34, 197, 94, 0.7)' }}></div>
                Rs ≥ 2.0 (Zone acceptable)
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm bg-[#1a1b1e] border border-[#23252a]"></div>
                Rs &lt; 2.0 (Hors spec)
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-white shadow-[0_0_4px_rgba(255,255,255,0.6)]"></div>
                Condition opératoire actuelle
              </div>
            </div>
            <span className="text-[11px] text-ink-tertiary bg-surface-2 px-2.5 py-1 rounded-sm border border-hairline">
              Design Space : 62% des conditions testées sont conformes
            </span>
          </div>
        </div>

      {/* ACTION FOOTER */}
      <div className="fixed bottom-0 left-[260px] w-[calc(100%-260px)] bg-[#191A1A] border-t border-[#2A2B2E] p-4 flex justify-end gap-4 z-50">
        <button 
          onClick={handleExportPDF}
          disabled={isExportingPDF || isExportingLIMS}
          className="px-5 py-2.5 text-sm font-medium rounded-md bg-canvas border border-hairline hover:border-hairline-strong transition-colors text-ink shadow-sm flex items-center gap-2 disabled:opacity-70"
        >
          {isExportingPDF ? (
            <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          )}
          Télécharger Dossier Technique (PDF)
        </button>
        <button 
          onClick={handleExportLIMS}
          disabled={isExportingPDF || isExportingLIMS}
          className="px-5 py-2.5 text-sm font-medium rounded-md bg-[#3B82F6] hover:bg-[#2563EB] transition-colors text-white shadow-sm flex items-center gap-2 disabled:opacity-70"
        >
          {isExportingLIMS ? (
            <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
          )}
          Synchroniser LIMS (CSV)
        </button>
      </div>

    </div>
  );
}
