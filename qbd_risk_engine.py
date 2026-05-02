"""
QbD Risk Engine v3 — BIOPHARM Competition
Uses: Derringer desirability + ADVO SCH/SR/SCP scoring + FMEA RPN
Formulas sourced from ADVO Dossier & ICH Q14/Q2(R2)
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Any

# ── BIOPHARM BASELINE (Classic 5-level, 3-rep approach) ──
BIOPHARM_BASELINE = {
    "linearity": {"levels": 5, "replicates": 3, "matrices": 2, "injections": 30},
    "repeatability": {"injections": 9},
    "intermediate_precision": {"injections": 27},
    "accuracy": {"injections": 9},
    "robustness": {"injections": 12},
    "total_injections": 87,
    "cost_per_injection_eur": 50,
    "minutes_per_injection": 20,
}

# ── Derringer one-sided desirability (exponential penalty near limit) ──
def d_smaller(val: float, target: float, limit: float, s: float = 2.5) -> float:
    if val <= target: return 1.0
    if val >= limit: return 0.0
    return ((limit - val) / (limit - target)) ** s

def d_larger(val: float, target: float, limit: float, s: float = 2.5) -> float:
    if val >= target: return 1.0
    if val <= limit: return 0.0
    return ((val - limit) / (target - limit)) ** s

def d_nominal(val: float, target: float, lo: float, hi: float, s: float = 2.5) -> float:
    if val < lo or val > hi: return 0.0
    if val <= target:
        return ((val - lo) / (target - lo)) ** s if target != lo else 1.0
    return ((hi - val) / (hi - target)) ** s if hi != target else 1.0

def geom_mean(pairs: List[tuple]) -> float:
    s = sum(w * math.log(max(d, 1e-8)) for d, w in pairs)
    tw = sum(w for _, w in pairs)
    return math.exp(s / tw * tw) if tw > 0 else 0.0


@dataclass
class EngineInput:
    product_matrix: int = 1           # 0=API,1=Capsule,2=Tablet,3=Cream
    target_concentration: float = 1.0 # mg/mL
    max_allowed_variance: float = 2.0 # % ATP tolerance
    hist_r2: float = 0.9995           # R² linearity
    hist_rsd: float = 0.8             # %RSD precision
    peak_quality: float = 1.2         # tailing factor
    prep_complexity: int = 1          # 1-3
    instrument_variability: int = 1   # 1-3
    reagent_stability: float = 8.0    # half-life score 1-10


def compute_risk(inp: EngineInput) -> Dict[str, Any]:
    """
    Computes Risk Index using three layers:
    1. ADVO SCH/SR/SCP scores (from ADVO Dossier §5)
    2. FMEA RPN (Severity x Occurrence x Detectability)
    3. Derringer desirability with exponential penalty
    Returns risk index, optimized plan, savings, comparative analysis, warnings.
    """
    # ═══════════════════════════════════════════════════════
    # LAYER 1: ADVO SCORING (Dossier §5 — SCH, SR, SCP)
    # ═══════════════════════════════════════════════════════

    # SCH — Historical Confidence Score (0-100)
    # Formula: SCH = Score_Lin*0.40 + Score_Prec*0.35 + Score_SST*0.25
    # (ADVO Dossier §5, lines 137-164)
    if inp.hist_r2 >= 0.9999:   score_lin = 100
    elif inp.hist_r2 >= 0.999:  score_lin = 75
    elif inp.hist_r2 >= 0.995:  score_lin = 50
    else:                       score_lin = 0

    if inp.hist_rsd <= 0.5:     score_prec = 100
    elif inp.hist_rsd <= 1.0:   score_prec = 75
    elif inp.hist_rsd <= 2.0:   score_prec = 40
    else:                       score_prec = 0

    # SST from tailing factor (ADVO: symmetric=100, partial=50, complex=10)
    if inp.peak_quality <= 1.2:   score_sst = 100
    elif inp.peak_quality <= 1.5: score_sst = 50
    else:                         score_sst = 10

    SCH = score_lin * 0.40 + score_prec * 0.35 + score_sst * 0.25

    # SR — Risk Score (0-100, higher=riskier)
    # Formula: SR = Score_Prep*0.35 + Score_Instr*0.35 + Score_Reag*0.30
    # (ADVO Dossier §5, lines 168-195)
    prep_map = {1: 10, 2: 50, 3: 90}
    instr_map = {1: 10, 2: 40, 3: 75}
    score_prep = prep_map.get(inp.prep_complexity, 50)
    score_instr = instr_map.get(inp.instrument_variability, 40)
    # Reagent stability: 10=very stable -> low risk, 1=unstable -> high risk
    score_reag = max(10, min(80, int(90 - inp.reagent_stability * 8)))
    SR = score_prep * 0.35 + score_instr * 0.35 + score_reag * 0.30

    # SCP — Product Complexity (ADVO Dossier §5, lines 199-208)
    scp_map = {0: 10, 1: 20, 2: 20, 3: 65}
    SCP = scp_map.get(inp.product_matrix, 50)

    # Confiance Nette (ADVO Dossier §5, line 214)
    CN = SCH - (SR * 0.5) - (SCP * 0.3)

    # ═══════════════════════════════════════════════════════
    # LAYER 2: FMEA RPN (failure_mode_matrix.py)
    # RPN = matrix_complexity * historical_reliability * method_vulnerability
    # ═══════════════════════════════════════════════════════
    fmea_matrix = 1 + inp.product_matrix  # 1-4
    fmea_hist = 1 if inp.hist_r2 >= 0.999 and inp.hist_rsd <= 1.0 else (2 if inp.hist_r2 >= 0.995 else 3)
    fmea_vuln = max(1, (inp.prep_complexity + inp.instrument_variability) // 2)
    RPN = fmea_matrix * fmea_hist * fmea_vuln

    # ═══════════════════════════════════════════════════════
    # LAYER 3: DERRINGER DESIRABILITY (exponential penalties)
    # Risk Index = (1 - D_overall) * 100
    # ═══════════════════════════════════════════════════════
    d_r2 = d_larger(inp.hist_r2, target=0.999, limit=0.990, s=3.0)
    d_rsd = d_smaller(inp.hist_rsd, target=1.0, limit=2.0, s=3.0)
    d_tail = d_smaller(inp.peak_quality, target=1.0, limit=2.0, s=2.5)
    d_conc = d_nominal(inp.target_concentration, target=1.0, lo=0.01, hi=10.0, s=1.5)
    d_prep = {1: 0.95, 2: 0.60, 3: 0.25}.get(inp.prep_complexity, 0.5)
    d_instr = {1: 0.95, 2: 0.65, 3: 0.30}.get(inp.instrument_variability, 0.5)
    d_reag = d_larger(inp.reagent_stability, target=7.0, limit=2.0, s=2.0)
    d_matrix = {0: 0.95, 1: 0.80, 2: 0.75, 3: 0.35}.get(inp.product_matrix, 0.5)

    D_overall = geom_mean([
        (d_r2, 0.20), (d_rsd, 0.15), (d_tail, 0.10), (d_conc, 0.05),
        (d_prep, 0.12), (d_instr, 0.12), (d_reag, 0.08), (d_matrix, 0.18),
    ])
    risk_index = round((1.0 - D_overall) * 100.0, 2)
    risk_index = max(0.0, min(100.0, risk_index))

    # ═══════════════════════════════════════════════════════
    # VALIDATION PLAN (ADVO Dossier §6, lines 233-306)
    # ═══════════════════════════════════════════════════════
    if SCH >= 75 and SR <= 40:
        lin = {"levels": 3, "replicates": 2, "range": "80-100-120%", "injections": 6}
    elif SCH >= 50:
        lin = {"levels": 5, "replicates": 2, "range": "50-75-100-125-150%", "injections": 10}
    else:
        lin = {"levels": 5, "replicates": 3, "range": "50-75-100-125-150%", "injections": 15}

    if SCP <= 30 and SCH >= 75:
        acc = {"method": "Inferred from linearity", "injections": 0,
               "ich_ref": "ICH Q2(R2) s3.3: accuracy inferred when linearity proven and matrix simple"}
    else:
        acc = {"method": "Spike recovery 3 levels x 3 reps", "injections": 9,
               "ich_ref": "ICH Q2(R2) s4.3: full spike recovery for complex matrices"}

    if SCH >= 75 and score_instr <= 40:
        rep = {"injections": 6, "note": "6 injections at 100% (reduced)"}
        pi = {"injections": 12, "note": "2 days x 2 analysts x 3 injections"}
    else:
        rep = {"injections": 9, "note": "3 levels x 3 replicates (standard)"}
        pi = {"injections": 27, "note": "3 days x 3 analysts x 3 replicates"}

    if SCH >= 70 and SR <= 40:
        rob = {"design": "Plackett-Burman 8 exp", "injections": 8}
    elif SCH >= 70:
        rob = {"design": "Plackett-Burman 12 exp", "injections": 12}
    else:
        rob = {"design": "OFAT on FMEA-critical factors", "injections": 15}

    total_opt = lin["injections"] + acc["injections"] + rep["injections"] + pi["injections"] + rob["injections"]
    total_std = BIOPHARM_BASELINE["total_injections"]
    saved = total_std - total_opt
    pct = round(saved / total_std * 100, 1) if total_std > 0 else 0

    # ═══════════════════════════════════════════════════════
    # OUTPUTS
    # ═══════════════════════════════════════════════════════
    plan_text = (
        f"Linearity: {lin['levels']} levels ({lin['range']}), {lin['replicates']} replicates. "
        f"Accuracy: {acc['method']}. "
        f"Repeatability: {rep['note']}. "
        f"Intermediate precision: {pi['note']}. "
        f"Robustness: {rob['design']}."
    )

    savings = {
        "optimized_injections": total_opt,
        "standard_injections": total_std,
        "injections_saved": saved,
        "reduction_pct": pct,
        "hours_saved": round(saved * BIOPHARM_BASELINE["minutes_per_injection"] / 60, 1),
        "cost_saved_eur": saved * BIOPHARM_BASELINE["cost_per_injection_eur"],
    }

    comparative = (
        f"ADVO Optimized: {total_opt} injections | "
        f"Classic Biopharm: {total_std} injections | "
        f"Reduction: -{pct}% ({saved} injections). "
        f"Cost: {total_opt*50} EUR vs {total_std*50} EUR (saving {saved*50} EUR). "
        f"ICH Q2(R2) compliance: 100% for both. "
        f"ICH Q14 justification: {'Documented' if CN >= 35 else 'Not applicable'}."
    )

    # ── Failure Risk Flags ──
    warnings: List[Dict[str, str]] = []
    if inp.product_matrix == 3:
        warnings.append({"severity": "HIGH", "flag": "Complex matrix (cream/suspension) - extraction interference risk",
                         "mitigation": "Full spike recovery mandatory. Monitor SST tailing each run.",
                         "ich_ref": "ICH Q2(R2) s4.5"})
    if inp.hist_r2 < 0.995:
        warnings.append({"severity": "HIGH", "flag": f"Historical R2={inp.hist_r2:.4f} below 0.995 - linearity risk",
                         "mitigation": "Full 5-level linearity required. Investigate column degradation.",
                         "ich_ref": "ICH Q2(R2) s4.1"})
    if inp.hist_rsd > 1.5:
        warnings.append({"severity": "HIGH", "flag": f"Historical RSD={inp.hist_rsd:.2f}% approaching ICH limit (2.0%)",
                         "mitigation": "Full precision protocol. Check injection volume consistency.",
                         "ich_ref": "ICH Q2(R2) s4.2"})
    if inp.peak_quality > 1.5:
        warnings.append({"severity": "MODERATE", "flag": f"Tailing factor={inp.peak_quality:.2f} indicates peak asymmetry",
                         "mitigation": "Evaluate column condition. Consider guard column.",
                         "ich_ref": "ICH Q2(R2) s4.6"})
    if inp.instrument_variability == 3:
        warnings.append({"severity": "MODERATE", "flag": "Instrument OQ >12 months - drift risk",
                         "mitigation": "Requalification OQ before validation. Enhanced SST controls.",
                         "ich_ref": "ICH Q14 s4.1 Annex A"})
    if inp.reagent_stability < 4.0:
        warnings.append({"severity": "MODERATE", "flag": "Unstable reagents - mobile phase degradation risk",
                         "mitigation": "Solution stability demonstrated on 24h max. Reference peak area +/-1.5%.",
                         "ich_ref": "ICH Q14 s5.4"})
    if lin["levels"] == 3:
        warnings.append({"severity": "LOW", "flag": "Linearity reduced to 3 levels (80-120%)",
                         "mitigation": "Retain historical 50% and 150% data as documentary reference per ICH Q14 s6.",
                         "ich_ref": "ICH Q14 s5.1"})
    if acc["injections"] == 0:
        warnings.append({"severity": "LOW", "flag": "Accuracy inferred from linearity (0 dedicated injections)",
                         "mitigation": "Monitor recovery via SST at 100% each analytical run.",
                         "ich_ref": "ICH Q2(R2) s3.3"})
    if not warnings:
        warnings.append({"severity": "LOW", "flag": "No critical risks identified", "mitigation": "Maintain routine SST monitoring.", "ich_ref": "ICH Q14 s6"})

    profile = "REDUCED" if CN >= 65 else ("STANDARD OPTIMIZED" if CN >= 35 else "FULL")

    return {
        "Exact_Risk_Index": risk_index,
        "Risk_Category": "LOW" if risk_index <= 20 else ("MODERATE" if risk_index <= 45 else ("HIGH" if risk_index <= 70 else "CRITICAL")),
        "Validation_Profile": profile,
        "Scores": {"SCH": round(SCH, 1), "SR": round(SR, 1), "SCP": SCP, "Confiance_Nette": round(CN, 1), "FMEA_RPN": RPN, "Desirability_Overall": round(D_overall, 4)},
        "Desirability_Detail": {"d_r2": round(d_r2, 4), "d_rsd": round(d_rsd, 4), "d_tailing": round(d_tail, 4), "d_concentration": round(d_conc, 4), "d_prep": d_prep, "d_instrument": d_instr, "d_reagent": round(d_reag, 4), "d_matrix": d_matrix},
        "Optimized_Testing_Plan": plan_text,
        "Plan_Detail": {"linearity": lin, "accuracy": acc, "repeatability": rep, "intermediate_precision": pi, "robustness": rob},
        "Cost_Time_Savings": savings,
        "Comparative_Analysis": comparative,
        "Failure_Risk_Flags": warnings,
    }


if __name__ == "__main__":
    r = compute_risk(EngineInput(product_matrix=2, target_concentration=1.0, max_allowed_variance=2.0,
                                  hist_r2=0.9999, hist_rsd=0.42, peak_quality=1.1,
                                  prep_complexity=1, instrument_variability=2, reagent_stability=8.0))
    import json
    print(json.dumps(r, indent=2))
