import csv
import io
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Response, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Union, Any

from spark_engine import SparkRiskAssessment, SequentialCopilot
from bayesian_knowledge_graph import BayesianKnowledgeGraph
from kalman_engine import generate_kalman_telemetry
from html_pdf_generator import generate_pdf_report
from fastapi.responses import FileResponse
from fastapi import BackgroundTasks
import tempfile
import os
import uuid

# ─────────────────────────────────────────────────────────────────────────────
#  APP SETUP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BIOPHARM SPARK Engine API",
    description="REST API for the SPARK Approach: FMEA Risk Calculator & Sequential Monte Carlo Co-Pilot.",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
#  PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class FMEARequest(BaseModel):
    maturite_methode: int = Field(..., ge=1, le=3, description="1=High maturity (Extensively validated prior knowledge), 3=Low maturity (Novel method).")
    complexite_matrice: int = Field(..., ge=1, le=3, description="1=Simple matrix (Pure API), 3=Complex matrix (Creams, biofluids with high interference risk).")
    disponibilite_donnees: int = Field(..., ge=1, le=3, description="1=High data availability (Historical batches exist), 3=Low availability.")
    criticite_reglementaire: int = Field(..., ge=1, le=3, description="1=Low criticality (In-process control), 3=High criticality (Release testing).")
    risque_patient: int = Field(..., ge=1, le=3, description="1=Low risk to patient, 3=High risk (Narrow therapeutic index drug).")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "maturite_methode": 2,
                    "complexite_matrice": 3,
                    "disponibilite_donnees": 1,
                    "criticite_reglementaire": 2,
                    "risque_patient": 2
                }
            ]
        }
    }

class FMEAResponse(BaseModel):
    rpn: int = Field(..., description="The calculated Risk Priority Number (Sum of the 5 axes). Minimum 5, Maximum 15.")
    decision: str = Field(..., description="The mathematically mapped validation plan recommendation.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "rpn": 10,
                    "decision": "PLAN RÉDUIT (4 niveaux x 2 réplicats = 8 injections)"
                }
            ]
        }
    }


class SequentialRequest(BaseModel):
    current_x: List[float] = Field(..., description="Array of currently completed target concentrations (e.g., [80.0, 80.0, 90.0, 90.0]).")
    current_y: List[float] = Field(..., description="Array of currently completed measured responses/areas (e.g., [82.1, 81.9, 92.5, 92.0]). Must match length of current_x.")
    total_target_points: int = Field(default=15, description="The theoretical maximum number of injections planned for the run (default is 15 for a full linearity plan).")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "current_x": [80.0, 80.0, 90.0, 90.0, 100.0, 100.0, 110.0, 110.0],
                    "current_y": [82.1, 81.9, 92.5, 92.0, 101.8, 102.1, 112.5, 113.0],
                    "total_target_points": 15
                }
            ]
        }
    }

class SequentialResponse(BaseModel):
    decision: str = Field(..., description="ARRÊT POSITIF (Stop the run) or CONTINUER (Keep running).")
    probability: float = Field(..., description="The computed Monte Carlo probability (0.0 to 1.0) that the final 15-point R² will be >= 0.999.")
    saved_injections: Union[int, None] = Field(default=None, description="Number of injections avoided if ARRÊT POSITIF is declared.")
    message: Union[str, None] = Field(default=None, description="Any warnings or context.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "decision": "ARRÊT POSITIF",
                    "probability": 0.9916,
                    "saved_injections": 7,
                    "message": None
                }
            ]
        }
    }


class HistoricalCampaign(BaseModel):
    campaign: str = Field(..., description="Name or ID of the historical campaign.")
    slope: float = Field(..., description="Historical slope value.")
    intercept: float = Field(..., description="Historical intercept value.")

class BayesianRequest(BaseModel):
    historical_campaigns: List[HistoricalCampaign] = Field(..., description="List of past validation metrics.")
    new_data_x: List[float] = Field(..., description="New concentration levels.")
    new_data_y: List[float] = Field(..., description="New response values.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "historical_campaigns": [
                        {"campaign": "Batch 2023-A", "slope": 1.015, "intercept": 0.05},
                        {"campaign": "Batch 2023-B", "slope": 1.020, "intercept": 0.04},
                        {"campaign": "Batch 2024-A", "slope": 1.010, "intercept": 0.06}
                    ],
                    "new_data_x": [80.0, 100.0, 120.0],
                    "new_data_y": [82.2, 102.3, 123.1]
                }
            ]
        }
    }

class BayesianResponse(BaseModel):
    posterior_slope_mean: float = Field(..., description="The mathematically fused posterior slope.")
    posterior_slope_var: float = Field(..., description="The mathematically fused posterior variance (uncertainty).")
    prior_influence_pct: float = Field(..., description="How much the historical data influenced the final result.")
    data_influence_pct: float = Field(..., description="How much the new data influenced the final result.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "posterior_slope_mean": 1.0151,
                    "posterior_slope_var": 0.000025,
                    "prior_influence_pct": 98.0,
                    "data_influence_pct": 2.0
                }
            ]
        }
    }


class LIMSExportRequest(BaseModel):
    batch_id: str = Field(default="DEMO-BATCH-001", description="Unique identifier for the batch")
    analyst_id: str = Field(default="AEC-USER", description="Identifier of the analyst executing the export")
    rpn_score: int = Field(..., description="FMEA Risk Priority Number")
    fmea_decision: str = Field(..., description="Calculated FMEA Plan Decision")
    monte_carlo_probability: float = Field(..., description="Sequential Co-Pilot Probability (%)")
    saved_injections: int = Field(..., description="Number of injections saved via early stopping")
    bayesian_posterior_slope: float = Field(..., description="Mathematically fused Posterior Slope")
    bayesian_prior_weight_pct: float = Field(..., description="Weight influence of historical prior (%)")



# ─────────────────────────────────────────────────────────────────────────────
#  API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/spark/fmea", response_model=FMEAResponse)
def calculate_fmea_risk(req: FMEARequest):
    """
    Calculates the cumulative Risk Priority Number (RPN) based on the 5 SPARK axes
    and returns the recommended validation plan.
    """
    try:
        assessor = SparkRiskAssessment()
        result = assessor.calculate_rpn(
            maturite_methode=req.maturite_methode,
            complexite_matrice=req.complexite_matrice,
            disponibilite_donnees=req.disponibilite_donnees,
            criticite_reglementaire=req.criticite_reglementaire,
            risque_patient=req.risque_patient
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/spark/extract")
async def extract_pdf_data(file: UploadFile = File(...)):
    """
    Real PDF extraction endpoint:
    1. pdfplumber reads raw text from the uploaded PDF (in-memory, no disk writes).
    2. Google Gemini analyzes the text and returns FMEA scores.
    3. Falls back to keyword heuristic if Gemini is unavailable.
    """
    import pdfplumber
    import httpx
    import json as json_mod
    import re

    GEMINI_API_KEY = "AIzaSyDzfcUOrKaq2NhWgxgyHWrtfV3KGYF8jP0"
    GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400, 
            detail="Only PDF files are allowed. Please upload a .pdf file."
        )

    try:
        # ── Step 1: Read PDF bytes into RAM ──
        pdf_bytes = await file.read()
        file_size_kb = len(pdf_bytes) / 1024
        pdf_stream = io.BytesIO(pdf_bytes)

        print(f"[SPARK Extract] Processing: {file.filename} ({file_size_kb:.1f} KB)")

        # ── Step 2: Extract text using pdfplumber (in-memory) ──
        raw_text = ""
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    raw_text += page_text + "\n"

        if not raw_text.strip():
            raise HTTPException(
                status_code=422,
                detail="Could not extract any text from the PDF. The file may be scanned/image-based."
            )

        # Truncate to first 4000 chars to stay within Gemini token limits
        text_for_llm = raw_text[:4000]
        print(f"[SPARK Extract] Extracted {len(raw_text)} chars of text from {len(pdf_stream.getvalue())} bytes")

        # ── Step 3: Ask Gemini to score the 5 FMEA axes ──
        gemini_prompt = f"""You are a pharmaceutical analytical chemistry expert specializing in HPLC method validation and ICH Q2(R2)/Q14 guidelines.

Analyze the following text extracted from an analytical protocol PDF and provide:
1. **drug_name**: Intelligently extract the name of the drug, active pharmaceutical ingredient, or specific product formulation being analyzed. If the document mentions a specific product like "Crème à 0.1%" or "Dosage comprimé 50mg", extract exactly that. DO NOT extract generic document titles like "Enregistrement N° 02" or "Validation analytique". Look deeply into the methodology, introduction, or objective sections for the actual molecule/formulation.
2. EXACTLY 5 risk axes scored on a scale of 1 to 3:

- **maturite** (Method Maturity): 1=Well-established compendial method with extensive prior validation history. 2=Adapted or partially validated method. 3=Novel, first-time development method with no prior data.
- **matrice** (Matrix Complexity): 1=Simple matrix (pure API, aqueous solution). 2=Moderate complexity (tablets, capsules). 3=Complex matrix (creams, biofluids, multi-component formulations).
- **donnees** (Data Availability): 1=Extensive historical data available (>3 prior campaigns). 2=Some historical data (1-2 campaigns). 3=No historical data at all.
- **criticite** (Regulatory Criticality): 1=In-process control or R&D testing. 2=Stability or routine QC testing. 3=Release testing for marketed product or regulatory submission.
- **risque** (Patient Risk): 1=Low risk (wide therapeutic index, topical). 2=Moderate risk (oral solid dosage). 3=High risk (narrow therapeutic index, injectable, biological).

IMPORTANT: Return ONLY a valid JSON object with exactly these 6 keys. No explanations, no markdown.
Example: {{"drug_name": "Paracetamol 500mg Tablets", "maturite": 2, "matrice": 3, "donnees": 1, "criticite": 2, "risque": 2}}

--- PROTOCOL TEXT ---
{text_for_llm}
"""

        fmea_data = None
        drug_name = "Unknown Protocol"
        
        models_to_try = [
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ]

        import asyncio

        for attempt, model in enumerate(models_to_try):
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        gemini_url,
                        json={
                            "contents": [{"parts": [{"text": gemini_prompt}]}],
                            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 100}
                        }
                    )

                    if resp.status_code == 200:
                        result = resp.json()
                        ai_text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        print(f"[SPARK Extract] Gemini ({model}) raw response: {ai_text}")

                        # Parse JSON from the AI response (handle markdown code blocks)
                        cleaned = ai_text.strip()
                        if cleaned.startswith("```"):
                            cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
                            cleaned = cleaned.replace("```", "").strip()

                        parsed = json_mod.loads(cleaned)

                        # Validate all 5 risk keys exist and values are 1-3, and drug_name is present
                        required_keys = ["maturite", "matrice", "donnees", "criticite", "risque"]
                        if all(k in parsed and parsed[k] in [1, 2, 3] for k in required_keys) and "drug_name" in parsed:
                            fmea_data = {k: parsed[k] for k in required_keys}
                            drug_name = parsed["drug_name"]
                            print(f"[SPARK Extract] [OK] Gemini FMEA scores: {fmea_data}, Drug: {drug_name}")
                            break # Success! Exit the retry loop
                        else:
                            print(f"[SPARK Extract] [WARN] Gemini ({model}) returned invalid values. Retrying...")
                    elif resp.status_code == 429:
                        print(f"[SPARK Extract] [WARN] Gemini ({model}) API rate limited (429). Retrying next model...")
                    else:
                        print(f"[SPARK Extract] [WARN] Gemini ({model}) API returned {resp.status_code}. Retrying next model...")

            except Exception as gemini_err:
                print(f"[SPARK Extract] [WARN] Gemini ({model}) call failed: {gemini_err}. Retrying next model...")
                
            # Delay before retry to bypass 429 Too Many Requests
            if attempt < len(models_to_try) - 1:
                await asyncio.sleep(4.0)

        # (The loop handles the retries)

        # ── Step 4: Fallback — keyword-based heuristic scoring ──
        if fmea_data is None:
            # Better fallback for drug name: use Regex to find the product name
            match = re.search(r'produit fini\s+(.+?)(?:\s+fabriqu[eé]|\s*à\s*Biopharm|\.|\n)', raw_text, re.IGNORECASE)
            if not match:
                match = re.search(r'dosage\s+de\s+(.+?)\s+dans', raw_text, re.IGNORECASE)
            if not match:
                match = re.search(r'dosage\s+du\s+(.+?)\s+dans', raw_text, re.IGNORECASE)
                
            if match and len(match.group(1).strip()) > 3:
                drug_name = match.group(1).strip()
                # Capitalize first letter safely
                if len(drug_name) > 0:
                    drug_name = drug_name[0].upper() + drug_name[1:]
            else:
                first_lines = [line.strip() for line in raw_text.split('\n') if len(line.strip()) > 5]
                if first_lines:
                    drug_name = first_lines[0][:60] + "..." if len(first_lines[0]) > 60 else first_lines[0]
                else:
                    drug_name = "Analytical Protocol"
                
            text_lower = raw_text.lower()

            # Maturité
            if any(w in text_lower for w in ["compendial", "pharmacopée", "usp", "ep method", "well-established"]):
                mat = 1
            elif any(w in text_lower for w in ["novel", "new method", "développement", "first-time", "nouvelle"]):
                mat = 3
            else:
                mat = 2

            # Matrice
            if any(w in text_lower for w in ["cream", "crème", "biological", "biologique", "plasma", "serum", "injectable"]):
                mtx = 3
            elif any(w in text_lower for w in ["tablet", "comprimé", "capsule", "gélule", "powder"]):
                mtx = 2
            else:
                mtx = 1

            # Données
            if any(w in text_lower for w in ["historical", "historique", "prior campaigns", "campagnes précédentes", "batch history"]):
                don = 1
            elif any(w in text_lower for w in ["limited data", "données limitées", "few batches"]):
                don = 2
            else:
                don = 3

            # Criticité
            if any(w in text_lower for w in ["release", "libération", "regulatory submission", "dossier", "amm", "marketing authorization"]):
                crit = 3
            elif any(w in text_lower for w in ["stability", "stabilité", "routine", "qc"]):
                crit = 2
            else:
                crit = 1

            # Risque Patient
            if any(w in text_lower for w in ["narrow therapeutic", "injectable", "parenteral", "biologique", "marge thérapeutique étroite"]):
                risk = 3
            elif any(w in text_lower for w in ["oral", "comprimé", "tablet", "capsule"]):
                risk = 2
            else:
                risk = 1

            fmea_data = {
                "maturite": mat,
                "matrice": mtx,
                "donnees": don,
                "criticite": crit,
                "risque": risk
            }
            print(f"[SPARK Extract] [HEURISTIC] FMEA scores: {fmea_data}")

        # ── Step 5: Return ──
        return {
            "success": True,
            "filename": file.filename,
            "drug_name": drug_name,
            "file_size_kb": round(file_size_kb, 1),
            "extracted_text_length": len(raw_text),
            "fmea_data": fmea_data
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract data from PDF: {str(e)}"
        )

@app.post("/spark/sequential", response_model=SequentialResponse)
def evaluate_sequential_stop(req: SequentialRequest):
    """
    Runs 10,000 Monte Carlo simulations to predict if the ongoing HPLC validation
    will achieve an R^2 >= 0.999. Decides whether to stop or continue.
    """
    if len(req.current_x) != len(req.current_y):
        raise HTTPException(status_code=400, detail="X and Y arrays must be of equal length.")
        
    try:
        # Initialize copilot
        copilot = SequentialCopilot(simulations=10000)
        
        result = copilot.evaluate_early_stopping(
            current_x=req.current_x,
            current_y=req.current_y,
            total_target_points=req.total_target_points
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/spark/bayesian", response_model=BayesianResponse)
def evaluate_bayesian_fusion(req: BayesianRequest):
    """
    Mathematically fuses historical validation data with new, ongoing data
    using Bayesian updating to justify reduced testing efforts.
    """
    try:
        kg = BayesianKnowledgeGraph(instrumental_noise_var=1.0)
        
        # Convert Pydantic models to dicts for the engine
        hist_dicts = [c.model_dump() for c in req.historical_campaigns]
        
        # 1. Calculate Prior
        prior = kg.calculate_prior(hist_dicts)
        
        # 2. Calculate Posterior
        posterior = kg.calculate_posterior(
            prior_slope_mean=prior['slope_mean'],
            prior_slope_var=prior['slope_var'],
            new_data_x=req.new_data_x,
            new_data_y=req.new_data_y
        )
        
        return posterior
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/spark/generate-report")
async def generate_report(payload: Dict[str, Any] = Body(default_factory=dict)):
    """Generate a combined report payload and inject Kalman telemetry.

    The frontend `ValidationReport.tsx` will bypass `DEMO_KALMAN_DATA` when it
    receives `kalman` as an array of points: `[{campaign, raw, filtered}, ...]`.

    Input is intentionally flexible (dict) so the caller can include other
    report sections (FMEA, sequential, etc.) and we simply append `kalman`.
    """

    try:
        raw_history = payload.get("kalman_raw_history") or payload.get("raw_history")
        Q = payload.get("kalman_Q", payload.get("Q", 0.01))
        R = payload.get("kalman_R", payload.get("R", 0.1))

        kalman_results = generate_kalman_telemetry(
            raw_history=raw_history,
            Q=float(Q),
            R=float(R),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Kalman telemetry generation failed: {e}")

    # Preserve any other caller-supplied sections, but do not echo calibration inputs.
    passthrough = dict(payload)
    for k in ("kalman_raw_history", "raw_history", "kalman_Q", "Q", "kalman_R", "R"):
        passthrough.pop(k, None)

    return {
        **passthrough,
        "success": True,
        "kalman": kalman_results,
    }

@app.post("/spark/export/lims", response_class=Response)
def export_to_lims(payload: LIMSExportRequest):
    """
    Transforms the combined SPARK metrics into a flat CSV format for LIMS ingestion.
    Automatically calculates system release status and attaches metadata.
    """
    try:
        # Determine strict release criteria based on ICH Q14 Monte Carlo thresholds
        if payload.monte_carlo_probability >= 97.0:
            system_status = "APPROVED_FOR_RELEASE"
        else:
            system_status = "INVESTIGATION_REQUIRED"

        # Generate ISO 8601 UTC timestamp
        current_timestamp = datetime.now(timezone.utc).isoformat()

        # Flatten data for CSV
        csv_data = {
            "Timestamp_UTC": current_timestamp,
            "Batch_ID": payload.batch_id,
            "Analyst_ID": payload.analyst_id,
            "System_Status": system_status,
            "RPN_Score": payload.rpn_score,
            "FMEA_Decision": payload.fmea_decision,
            "MC_Probability_Pct": payload.monte_carlo_probability,
            "Saved_Injections": payload.saved_injections,
            "Posterior_Slope": payload.bayesian_posterior_slope,
            "Prior_Weight_Pct": payload.bayesian_prior_weight_pct
        }

        # Use StringIO as an in-memory file buffer
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=csv_data.keys(), quoting=csv.QUOTE_MINIMAL)
        
        # Write headers and the single row of flattened data
        writer.writeheader()
        writer.writerow(csv_data)
        
        # Extract string content from buffer
        csv_content = output.getvalue()

        # Format HTTP Response for automatic download
        filename = f"lims_export_{payload.batch_id}.csv"
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        # Robust error handling: intercept transformation errors
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate LIMS CSV export: {str(e)}"
        )
# ─── Persistent reports directory for download ───
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

@app.post("/spark/export/pdf")
def export_to_pdf(payload: dict):
    """
    Step 1: Generate the PDF/HTML report and return a download_id.
    The file is saved to a local directory for retrieval via GET.
    """
    try:
        download_id = uuid.uuid4().hex
        output_path = os.path.join(REPORTS_DIR, f"{download_id}.pdf")
        
        generate_pdf_report(payload, output_path)
        
        # Determine which file was actually created
        if os.path.exists(output_path):
            filename = "SPARK_Validation_Report.pdf"
        else:
            html_fallback = output_path.replace(".pdf", ".html")
            if os.path.exists(html_fallback):
                # Rename to use the download_id for consistency
                os.rename(html_fallback, os.path.join(REPORTS_DIR, f"{download_id}.html"))
                filename = "SPARK_Validation_Report.html"
            else:
                raise Exception("Failed to generate PDF or HTML fallback")
        
        return {"download_id": download_id, "filename": filename}
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate PDF report: {str(e)}"
        )

@app.get("/spark/export/pdf/download/{download_id}")
def download_pdf(download_id: str):
    """
    Step 2: Serve the generated file as a direct browser download.
    The browser navigates here natively, guaranteeing correct filename.
    """
    # Try PDF first, then HTML fallback
    pdf_path = os.path.join(REPORTS_DIR, f"{download_id}.pdf")
    html_path = os.path.join(REPORTS_DIR, f"{download_id}.html")
    
    if os.path.exists(pdf_path):
        file_path = pdf_path
        filename = "SPARK_Validation_Report.pdf"
        media_type = "application/pdf"
    elif os.path.exists(html_path):
        file_path = html_path
        filename = "SPARK_Validation_Report.html"
        media_type = "text/html"
    else:
        raise HTTPException(status_code=404, detail="Report not found or expired.")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type
    )

@app.get("/health")
def health():
    return {"status": "ok", "engine": "BIOPHARM SPARK Approach API"}
