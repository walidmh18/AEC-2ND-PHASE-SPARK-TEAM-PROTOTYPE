"""
AQbD Risk Assessment — Pydantic Schema Definitions
====================================================
Canonical data contract for the backend API endpoint.
Covers all ICH Q2(R2) / Q14 critical parameters for HPLC
validation risk assessment and plan optimization.

Author:  BIOPHARM Competition Team
Version: 2.1.0

ICH References:
  - ICH Q2(R2): Validation of Analytical Procedures (2023)
  - ICH Q14: Analytical Procedure Development (2022)
"""

from __future__ import annotations

from enum import IntEnum, Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
#  ENUMERATIONS
# ─────────────────────────────────────────────────────────────────────────────

class ProductMatrix(IntEnum):
    """
    Product matrix complexity classification per ICH Q14 §4.1 Annex A.
    Higher values → more complex sample preparation → higher risk.
    """
    API_POWDER = 0        # Pure API, simple dissolution
    SOLID_ORAL = 1        # Tablets, capsules — standard extraction
    SEMI_SOLID = 2        # Creams, ointments — requires SPE/LLE
    COMPLEX_LIQUID = 3    # Suspensions, biologics — multi-step prep


class ElutionType(str, Enum):
    """Chromatographic elution mode — gradient adds baseline drift risk."""
    ISOCRATIC = "isocratic"
    GRADIENT = "gradient"


class PrepComplexity(IntEnum):
    """
    Sample preparation complexity per FMEA risk matrix.
    Maps to number and type of extraction steps.
    """
    SIMPLE = 1       # Direct dissolution, dilute-and-shoot
    MODERATE = 2     # Filtration + sonication, or single SPE
    COMPLEX = 3      # Multi-step SPE, LLE, derivatization


class InstrumentVariability(IntEnum):
    """
    Instrument qualification status and drift risk.
    Based on time since last OQ/PQ and maintenance history.
    """
    LOW = 1          # OQ < 6 months, well-maintained
    MODERATE = 2     # OQ 6-12 months, standard maintenance
    HIGH = 3         # OQ > 12 months, or known drift issues


# ─────────────────────────────────────────────────────────────────────────────
#  INPUT SCHEMA — API Request
# ─────────────────────────────────────────────────────────────────────────────

class RiskAssessmentInput(BaseModel):
    """
    Complete input schema for AQbD risk assessment.
    
    Integrates all Critical Method Parameters (CMPs) required by
    ICH Q14 §4.1 Annex A for a lifecycle-aware HPLC method risk
    evaluation. Parameters are grouped into three risk categories:
    
    - Category A: Product & Matrix Complexity (M_c)
    - Category B: Historical Method Performance (from R&D data)
    - Category C: Method Execution Vulnerability
    
    This serves as the canonical data contract for the /predict_risk
    API endpoint and the Random Forest training pipeline.
    """

    # ── Category A: Product & Matrix Complexity ──────────────────────────

    product_matrix: ProductMatrix = Field(
        default=ProductMatrix.SOLID_ORAL,
        description=(
            "Dosage form complexity category per ICH Q14 §4.1 Annex A. "
            "0=API Powder, 1=Solid Oral (tablet/capsule), "
            "2=Semi-Solid (cream/ointment), 3=Complex Liquid (suspension/biologic)"
        ),
    )

    target_concentration: float = Field(
        default=1.0,
        gt=0.0,
        le=100.0,
        description=(
            "Nominal working concentration in mg/mL. Extreme values "
            "(< 0.01 or > 50) increase detection/linearity risk. "
            "Ref: ICH Q2(R2) §4.1 — defines the analytical range."
        ),
    )

    api_stability_score: float = Field(
        default=3.0,
        ge=1.0,
        le=10.0,
        description=(
            "API degradation susceptibility rating (1=very stable, "
            "10=highly labile under heat/light/humidity). Derived from "
            "forced degradation studies per ICH Q1A/Q1B. Higher values "
            "increase risk of in-process degradation artifacts."
        ),
    )

    prep_complexity: PrepComplexity = Field(
        default=PrepComplexity.SIMPLE,
        description=(
            "Sample preparation complexity per FMEA risk matrix. "
            "1=Simple (dilute-and-shoot), 2=Moderate (filtration+sonication), "
            "3=Complex (SPE/LLE/derivatization). Ref: ICH Q14 §4.1."
        ),
    )

    # ── Category B: Historical Method Performance ────────────────────────

    hist_r2_linearity: float = Field(
        default=0.9995,
        ge=0.900,
        le=1.0,
        description=(
            "Historical correlation coefficient (R²) from linearity studies. "
            "ICH Q2(R2) §4.1: Target > 0.999, Regulatory Limit = 0.990. "
            "Values below 0.995 trigger exponential risk penalty."
        ),
    )

    hist_rsd_precision: float = Field(
        default=0.8,
        ge=0.0,
        le=10.0,
        description=(
            "Historical Relative Standard Deviation (%%RSD) from precision "
            "studies. ICH Q2(R2) §4.2: Target < 1.0%%, Limit = 2.0%%. "
            "Represents repeatability variance of the method."
        ),
    )

    hist_recovery_accuracy: float = Field(
        default=99.5,
        ge=80.0,
        le=120.0,
        description=(
            "Mean historical recovery (%%) from accuracy/spike-recovery studies. "
            "ICH Q2(R2) §4.3: Target = 100.0%%, Limits = 98.0-102.0%%. "
            "CRITICAL: Missing from original schema — accuracy is a mandatory "
            "ICH Q2(R2) validation parameter. Cannot assess risk without it."
        ),
    )

    max_allowed_variance: float = Field(
        default=2.0,
        gt=0.0,
        le=10.0,
        description=(
            "Analytical Target Profile (ATP) tolerance in %%. Defines the "
            "maximum acceptable total variance for the method result. "
            "Ref: ICH Q14 §3 — ATP is the foundation of the AQbD approach."
        ),
    )

    peak_quality_tailing: float = Field(
        default=1.2,
        ge=0.5,
        le=5.0,
        description=(
            "System Suitability Test (SST) — tailing factor (asymmetry). "
            "ICH Q2(R2) §4.6: Target = 1.0, Limit = 2.0. "
            "Values > 1.5 indicate potential co-elution or column degradation."
        ),
    )

    peak_quality_resolution: float = Field(
        default=2.5,
        ge=0.5,
        le=15.0,
        description=(
            "SST — Resolution (Rs) between API peak and nearest impurity. "
            "ICH Q2(R2) §4.6: Target > 2.0, Limit = 1.5. "
            "CRITICAL: Missing from original schema — resolution is mandatory "
            "for specificity/selectivity assessment per ICH Q2(R2) §4.5."
        ),
    )

    n_historical_campaigns: int = Field(
        default=2,
        ge=0,
        le=50,
        description=(
            "Number of prior validated campaigns/batches with available data. "
            "ICH Q14 §5.1: 'Prior knowledge' strength directly determines "
            "the extent of permissible validation reduction. "
            ">=3 campaigns with consistent data = strong prior knowledge."
        ),
    )

    # ── Category C: Method Execution Vulnerability ───────────────────────

    instrument_variability: InstrumentVariability = Field(
        default=InstrumentVariability.LOW,
        description=(
            "Instrument qualification status and historical drift. "
            "1=Low (recent OQ), 2=Moderate (6-12mo), 3=High (>12mo or drift). "
            "Ref: ICH Q14 §4.1 Annex A — equipment-related risk factors."
        ),
    )

    reagent_stability: float = Field(
        default=8.0,
        ge=1.0,
        le=10.0,
        description=(
            "Mobile phase / reagent stability rating (1=unstable buffer, "
            "10=very stable organic solvent). Lower values increase risk "
            "of in-run degradation. Ref: ICH Q14 §5.4 robustness."
        ),
    )

    elution_type: ElutionType = Field(
        default=ElutionType.ISOCRATIC,
        description=(
            "Chromatographic elution mode. Gradient elution increases "
            "baseline drift risk, re-equilibration time, and run-to-run "
            "variability. Ref: ICH Q14 §5.4 — critical robustness factor."
        ),
    )

    run_time_minutes: float = Field(
        default=10.0,
        ge=1.0,
        le=120.0,
        description=(
            "Total HPLC method run time in minutes. Longer runs increase "
            "system drift probability, column degradation, and mobile "
            "phase consumption. Values > 30 min add significant risk."
        ),
    )

    @model_validator(mode="after")
    def validate_ich_consistency(self) -> "RiskAssessmentInput":
        """Cross-field validation for ICH regulatory consistency."""
        # ATP tolerance must be ≥ historical RSD
        if self.max_allowed_variance < self.hist_rsd_precision:
            raise ValueError(
                f"ATP tolerance ({self.max_allowed_variance}%) cannot be "
                f"narrower than historical RSD ({self.hist_rsd_precision}%). "
                f"The method cannot meet its own ATP."
            )
        return self


# ─────────────────────────────────────────────────────────────────────────────
#  OUTPUT SCHEMA — API Response
# ─────────────────────────────────────────────────────────────────────────────

class DesirabilityBreakdown(BaseModel):
    """Per-parameter Derringer desirability values (0.0 to 1.0)."""
    d_product_matrix: float = Field(description="Dosage form desirability")
    d_target_concentration: float = Field(description="Concentration desirability")
    d_api_stability: float = Field(description="API stability desirability")
    d_prep_complexity: float = Field(description="Prep complexity desirability")
    d_r2_linearity: float = Field(description="R² desirability")
    d_rsd_precision: float = Field(description="RSD precision desirability")
    d_recovery_accuracy: float = Field(description="Recovery accuracy desirability")
    d_tailing_factor: float = Field(description="Tailing factor desirability")
    d_resolution: float = Field(description="Resolution Rs desirability")
    d_instrument_variability: float = Field(description="Instrument desirability")
    d_reagent_stability: float = Field(description="Reagent stability desirability")
    d_elution_type: float = Field(description="Elution type desirability")
    d_run_time: float = Field(description="Run time desirability")
    D_matrix_complexity: float = Field(description="Category A aggregate")
    D_historical_performance: float = Field(description="Category B aggregate")
    D_execution_vulnerability: float = Field(description="Category C aggregate")
    D_overall: float = Field(description="Overall desirability (geometric mean)")


class TestingPlanDetail(BaseModel):
    """Detailed plan for a single ICH validation parameter."""
    parameter_name: str = Field(description="ICH parameter (e.g., 'Linearity')")
    ich_reference: str = Field(description="ICH section reference")
    levels: int = Field(description="Number of concentration levels")
    replicates: int = Field(description="Replicates per level")
    range_pct: str = Field(description="Concentration range (e.g., '80-100-120%')")
    optimized_injections: int = Field(description="ADVO-optimized injection count")
    standard_injections: int = Field(description="Classic Biopharm injection count")
    reduction_pct: float = Field(description="Percentage reduction achieved")
    rationale: str = Field(description="ICH-compliant scientific rationale")


class CostTimeSavings(BaseModel):
    """Quantified resource savings from validation optimization."""
    total_injections_optimized: int
    total_injections_standard: int
    injections_saved: int
    reduction_percentage: float = Field(description="Overall %% reduction")
    estimated_hours_saved: float = Field(
        description="Lab hours saved (assuming 20 min/injection average)"
    )
    estimated_cost_saved_eur: float = Field(
        description="Cost savings in EUR (assuming 50 EUR/injection)"
    )


class ComparativeAnalysis(BaseModel):
    """Side-by-side comparison: ADVO-optimized vs Classic Biopharm method."""
    optimized_plan: List[TestingPlanDetail]
    classic_plan: List[TestingPlanDetail]
    savings: CostTimeSavings
    ich_compliance_optimized: str = Field(
        default="100%",
        description="ICH Q2(R2) compliance level of optimized plan"
    )
    ich_compliance_classic: str = Field(
        default="100%",
        description="ICH Q2(R2) compliance level of classic plan"
    )
    q14_justification_documented: bool = Field(
        default=True,
        description="Whether ICH Q14 enhanced approach justification is provided"
    )


class RiskWarning(BaseModel):
    """Individual risk/failure warning with mitigation strategy."""
    severity: str = Field(description="LOW / MODERATE / HIGH / CRITICAL")
    parameter: str = Field(description="Affected ICH parameter")
    description: str = Field(description="Nature of the risk")
    trigger_condition: str = Field(
        description="Condition that would trigger re-validation"
    )
    mitigation: str = Field(description="Recommended mitigation action")
    ich_reference: str = Field(description="Relevant ICH guideline section")


class MLPrediction(BaseModel):
    """Machine learning model prediction details."""
    model_name: str = Field(description="Model used (e.g., 'GradientBoosting')")
    prediction: int = Field(
        description="0 = Safe to Optimize, 1 = Full Validation Required"
    )
    prediction_label: str = Field(
        description="Human-readable prediction label"
    )
    probability_full_validation: float = Field(
        description="Probability that full validation is required (0.0 to 1.0)"
    )
    model_auc: float = Field(
        description="Model test ROC-AUC for confidence context"
    )
    top_risk_drivers: Dict[str, float] = Field(
        description="Top 5 feature importances driving this prediction"
    )


class RiskAssessmentOutput(BaseModel):
    """
    Complete output schema for the AQbD risk assessment endpoint.
    
    Provides:
    1. Continuous Risk Index with full desirability breakdown
    2. ML model prediction with confidence metrics
    3. Optimized testing plan with ICH justifications
    4. Cost/time savings quantification
    5. Comparative analysis (ADVO vs Classic Biopharm)
    6. Risk warnings with mitigation strategies
    7. Regulatory justification text
    """

    # ── Risk Scores ──
    exact_risk_index: float = Field(
        description="Continuous risk index (0.00%% to 100.00%%)"
    )
    risk_category: str = Field(
        description="LOW (≤20%%) / MODERATE (≤45%%) / HIGH (≤70%%) / CRITICAL (>70%%)"
    )
    desirability_breakdown: DesirabilityBreakdown

    # ── ML Prediction ──
    ml_prediction: MLPrediction

    # ── Optimized Testing Plan ──
    optimized_testing_plan: List[TestingPlanDetail] = Field(
        description="ADVO-optimized validation plan per ICH parameter"
    )

    # ── Cost/Time Savings ──
    savings: CostTimeSavings

    # ── Comparative Analysis ──
    comparative_analysis: ComparativeAnalysis

    # ── Risk Warnings ──
    risk_warnings: List[RiskWarning] = Field(
        description="Active risk warnings with mitigation strategies"
    )

    # ── Regulatory Justification ──
    ich_justification: str = Field(
        description=(
            "Full regulatory justification text suitable for inclusion "
            "in a validation dossier. References ICH Q2(R2) / Q14."
        )
    )

    # ── Lifecycle Monitoring ──
    revalidation_triggers: List[str] = Field(
        description=(
            "Conditions per ICH Q14 §6 that would mandate re-validation "
            "(e.g., 'R² < 0.990', 'RSD > 2.0%%', 'Recovery outside 98-102%%')"
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
#  TABULAR FORMAT FOR ML TRAINING
# ─────────────────────────────────────────────────────────────────────────────

class TrainingRecord(BaseModel):
    """
    Flat tabular record for Random Forest / XGBoost training.
    One row per HPLC method scenario. All fields are numeric
    or encoded categorical (ready for sklearn ingestion).
    """
    # Raw features (from input schema)
    product_matrix: int
    target_concentration: float
    api_stability_score: float
    prep_complexity: int
    hist_r2_linearity: float
    hist_rsd_precision: float
    hist_recovery_accuracy: float
    max_allowed_variance: float
    peak_quality_tailing: float
    peak_quality_resolution: float
    n_historical_campaigns: int
    instrument_variability: int
    reagent_stability: float
    elution_type_encoded: int        # 0=isocratic, 1=gradient
    run_time_minutes: float

    # Engineered features
    r2_deficit: float                # 1.0 - R²
    recovery_deviation: float        # |recovery - 100|
    tailing_excess: float            # max(0, tailing - 1.0)
    resolution_deficit: float        # max(0, 2.0 - resolution)
    rsd_over_target: float           # max(0, rsd - 1.0)
    complexity_score: float          # weighted composite
    chromatographic_risk: float      # elution + runtime composite
    variance_headroom: float         # max_allowed_variance - hist_rsd

    # Target variable
    full_validation_required: int    # 0=Safe to Optimize, 1=Full Required
