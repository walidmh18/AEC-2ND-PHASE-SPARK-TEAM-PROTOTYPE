"""
AQbD Risk Assessment — FastAPI Backend
=======================================
Wraps the continuous QbD risk engine in a REST API for frontend integration.
Utilizes continuous mathematical weighting and exponential penalty formulas
derived from the ADVO Dossier and ICH Q14/Q2(R2) guidelines.

Author:  BIOPHARM Competition Team
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Any

from qbd_risk_engine import compute_risk, EngineInput

# ─────────────────────────────────────────────────────────────────────────────
#  APP SETUP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BIOPHARM Continuous QbD Risk Assessment Engine",
    description="Calculates Risk Index and outputs optimized ICH-compliant validation plans.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
#  PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class RiskRequest(BaseModel):
    """
    Input payload mapping exactly to the requested frontend schema.
    Biochemical context is provided in the descriptions.
    """
    Product_Matrix: int = Field(
        ..., ge=0, le=3,
        description="0 = Raw API, 1 = Capsule, 2 = Tablet, 3 = Complex Cream. "
                    "Biochemical rationale: Complex matrices like creams contain excipients (emulsifiers, lipids) "
                    "that cause ion suppression or co-elution, fundamentally altering analyte recovery compared to pure API."
    )
    Target_Concentration: float = Field(
        ..., gt=0.0,
        description="Target concentration (mg/mL). Very low concentrations approach the LOD/LOQ, "
                    "increasing susceptibility to baseline noise and matrix interference."
    )
    Max_Allowed_Variance: float = Field(
        ..., gt=0.0,
        description="Max Allowed Variance in % (ATP tolerance). Represents the clinical/functional boundary "
                    "for product efficacy. Tighter bounds leave less room for analytical error."
    )
    Historical_R2: float = Field(
        ..., ge=0.0, le=1.0,
        description="Historical Linearity R² (e.g., 0.9995). Ensures the detector response remains directly proportional "
                    "to analyte concentration, preventing biased quantification at the method boundaries."
    )
    Historical_RSD: float = Field(
        ..., ge=0.0,
        description="Historical Precision RSD %. Reflects the baseline variance of the analytical system (pump jitter, "
                    "autosampler precision, integration errors)."
    )
    Peak_Quality: float = Field(
        ..., gt=0.0,
        description="Peak Quality / System Suitability (tailing factor). A tailing peak (>1.5) indicates secondary "
                    "retention mechanisms (e.g., silanol interactions) or column voiding, degrading resolution."
    )
    Prep_Complexity: int = Field(
        ..., ge=1, le=3,
        description="Prep Complexity (1-3 scale). 1=Simple dilution, 3=Liquid-Liquid Extraction (LLE) or Solid Phase Extraction (SPE). "
                    "More steps mathematically multiply the recovery variance and human error."
    )
    Instrument_Variability: int = Field(
        ..., ge=1, le=3,
        description="Instrument Variability (1-3 scale). Reflects OQ/PQ status. Older or uncalibrated components "
                    "cause drift in retention times and peak areas (e.g., lamp degradation, check valve leaks)."
    )
    Reagent_Stability: float = Field(
        ..., gt=0.0,
        description="Reagent Stability (half-life / score). Buffer degradation (pH shifts) or mobile phase evaporation "
                    "alters the analyte's ionization state, fundamentally shifting chromatographic retention."
    )


class RiskResponse(BaseModel):
    """Output payload mapping to the requested schema."""
    Optimized_Testing_Plan: str = Field(description="Specific ICH-compliant recommendation.")
    Cost_Time_Savings: Dict[str, Any] = Field(description="Calculated vs the BIOPHARM baseline.")
    Comparative_Analysis: str = Field(description="Text block comparing the new method to the old method.")
    Failure_Risk_Flags: List[Dict[str, str]] = Field(description="Specific warnings based on inputs.")
    
    # Additional context fields for transparency
    Exact_Risk_Index: float
    Risk_Category: str
    Validation_Profile: str
    Scores: Dict[str, Any]
    Desirability_Detail: Dict[str, float]


# ─────────────────────────────────────────────────────────────────────────────
#  API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/predict_risk", response_model=RiskResponse)
def predict_risk(req: RiskRequest) -> RiskResponse:
    """
    Receives method parameters, maps them to the continuous risk engine,
    and returns an optimized validation plan.
    """
    # Map API request to internal engine input
    engine_input = EngineInput(
        product_matrix=req.Product_Matrix,
        target_concentration=req.Target_Concentration,
        max_allowed_variance=req.Max_Allowed_Variance,
        hist_r2=req.Historical_R2,
        hist_rsd=req.Historical_RSD,
        peak_quality=req.Peak_Quality,
        prep_complexity=req.Prep_Complexity,
        instrument_variability=req.Instrument_Variability,
        reagent_stability=req.Reagent_Stability
    )
    
    # Calculate continuous risk using Derringer + ADVO + FMEA logic
    result = compute_risk(engine_input)
    
    # Construct response matching the exact requested output schema
    return RiskResponse(
        Optimized_Testing_Plan=result["Optimized_Testing_Plan"],
        Cost_Time_Savings=result["Cost_Time_Savings"],
        Comparative_Analysis=result["Comparative_Analysis"],
        Failure_Risk_Flags=result["Failure_Risk_Flags"],
        Exact_Risk_Index=result["Exact_Risk_Index"],
        Risk_Category=result["Risk_Category"],
        Validation_Profile=result["Validation_Profile"],
        Scores=result["Scores"],
        Desirability_Detail=result["Desirability_Detail"],
    )

@app.get("/health")
def health():
    return {"status": "ok", "engine": "BIOPHARM Continuous QbD Risk Assessment"}
