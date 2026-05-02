"""
PDF-to-Structured-Data Extraction Pipeline
============================================
Converts unstructured text from HPLC validation research papers (PDFs)
into the structured TrainingRecord tabular format for Random Forest
model training.

Author:  BIOPHARM Competition Team
Version: 1.0.0

Dependencies:
    pip install pdfplumber pandas

Pipeline:
    1. Extract raw text from PDF pages
    2. Apply regex patterns to capture ICH validation parameters
    3. Parse and normalize extracted values
    4. Export as structured CSV matching TrainingRecord schema
"""

from __future__ import annotations

import re
import os
import csv
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Optional: pdfplumber for production use
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    warnings.warn(
        "pdfplumber not installed. Install with: pip install pdfplumber. "
        "Using fallback text input mode."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  REGEX PATTERNS — ICH HPLC Validation Parameters
# ─────────────────────────────────────────────────────────────────────────────

# Each pattern captures a named value from typical HPLC validation papers.
# Patterns are designed to be robust against formatting variations.

EXTRACTION_PATTERNS: Dict[str, List[re.Pattern]] = {

    # ── R² / Correlation Coefficient ──
    "r2_linearity": [
        re.compile(
            r"[Rr][\s²2]*\s*[=:]\s*(0\.9\d{2,6})", re.IGNORECASE
        ),
        re.compile(
            r"correlation\s+coefficient\s*[=:]\s*(0\.9\d{2,6})", re.IGNORECASE
        ),
        re.compile(
            r"linearity.*?[Rr][\s²2]*\s*[=:of]*\s*(0\.9\d{2,6})", re.IGNORECASE
        ),
    ],

    # ── %RSD / Relative Standard Deviation ──
    "rsd_precision": [
        re.compile(
            r"%?\s*RSD\s*[=:<]\s*(\d+\.?\d*)\s*%?", re.IGNORECASE
        ),
        re.compile(
            r"relative\s+standard\s+deviation\s*[=:]\s*(\d+\.?\d*)", re.IGNORECASE
        ),
        re.compile(
            r"precision.*?(\d+\.\d+)\s*%", re.IGNORECASE
        ),
    ],

    # ── Recovery % (Accuracy) ──
    "recovery_accuracy": [
        re.compile(
            r"recovery\s*[=:]\s*(\d{2,3}\.?\d*)\s*%?", re.IGNORECASE
        ),
        re.compile(
            r"accuracy.*?(\d{2,3}\.\d+)\s*%", re.IGNORECASE
        ),
        re.compile(
            r"mean\s+recovery\s*[=:of]*\s*(\d{2,3}\.\d+)", re.IGNORECASE
        ),
    ],

    # ── Tailing Factor ──
    "tailing_factor": [
        re.compile(
            r"tailing\s*(?:factor)?\s*[=:]\s*(\d+\.?\d*)", re.IGNORECASE
        ),
        re.compile(
            r"asymmetry\s*(?:factor)?\s*[=:]\s*(\d+\.?\d*)", re.IGNORECASE
        ),
        re.compile(
            r"peak\s+symmetry\s*[=:]\s*(\d+\.?\d*)", re.IGNORECASE
        ),
    ],

    # ── Resolution ──
    "resolution": [
        re.compile(
            r"resolution\s*(?:\(Rs\))?\s*[=:>]\s*(\d+\.?\d*)", re.IGNORECASE
        ),
        re.compile(
            r"Rs\s*[=:>]\s*(\d+\.?\d*)", re.IGNORECASE
        ),
    ],

    # ── Concentration / Range ──
    "concentration": [
        re.compile(
            r"concentration\s*[=:]\s*(\d+\.?\d*)\s*(?:mg|µg|ug)/\s*(?:mL|ml)",
            re.IGNORECASE
        ),
        re.compile(
            r"(\d+\.?\d*)\s*(?:mg|µg)/\s*(?:mL|ml)", re.IGNORECASE
        ),
    ],

    # ── Run Time ──
    "run_time": [
        re.compile(
            r"run\s*time\s*[=:]\s*(\d+\.?\d*)\s*min", re.IGNORECASE
        ),
        re.compile(
            r"retention\s+time.*?(\d+\.?\d+)\s*min", re.IGNORECASE
        ),
        re.compile(
            r"analysis\s+time\s*[=:]\s*(\d+\.?\d*)\s*min", re.IGNORECASE
        ),
    ],

    # ── Linearity Range ──
    "linearity_range": [
        re.compile(
            r"linearity.*?(\d+)\s*[-–]\s*(\d+)\s*%", re.IGNORECASE
        ),
        re.compile(
            r"range\s*[=:]\s*(\d+)\s*[-–]\s*(\d+)\s*%", re.IGNORECASE
        ),
    ],

    # ── Dosage Form ──
    "dosage_form": [
        re.compile(
            r"(tablet|capsule|cream|ointment|suspension|injection|powder|gel"
            r"|solution|syrup|suppository)",
            re.IGNORECASE
        ),
    ],

    # ── Elution Type ──
    "elution_type": [
        re.compile(r"(isocratic|gradient)\s*(?:elution|mode)?", re.IGNORECASE),
    ],

    # ── Column Info ──
    "column": [
        re.compile(
            r"(C18|C8|phenyl|HILIC|CN).*?(\d+)\s*[×x]\s*(\d+\.?\d*)\s*mm",
            re.IGNORECASE
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
#  PDF TEXT EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts all text from a PDF file using pdfplumber.
    Falls back to basic extraction if pdfplumber unavailable.
    """
    if not HAS_PDFPLUMBER:
        raise ImportError(
            "pdfplumber is required for PDF extraction. "
            "Install with: pip install pdfplumber"
        )

    full_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)

            # Also extract tables (common in validation papers)
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row:
                        cleaned = [str(cell) if cell else "" for cell in row]
                        full_text.append(" | ".join(cleaned))

    return "\n".join(full_text)


def extract_tables_from_pdf(pdf_path: str) -> List[pd.DataFrame]:
    """
    Extracts tabular data from PDF pages.
    HPLC validation papers often present results in tables.
    """
    if not HAS_PDFPLUMBER:
        return []

    all_tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for t_idx, table in enumerate(tables):
                if table and len(table) > 1:
                    # Use first row as header if it looks like one
                    header = table[0]
                    data = table[1:]
                    try:
                        df = pd.DataFrame(data, columns=header)
                        df.attrs["source_page"] = page_num + 1
                        df.attrs["table_index"] = t_idx
                        all_tables.append(df)
                    except Exception:
                        continue
    return all_tables


# ─────────────────────────────────────────────────────────────────────────────
#  PARAMETER EXTRACTION FROM TEXT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractedMethod:
    """Raw extracted parameters from a single paper/method."""
    source_file: str = ""
    r2_linearity: Optional[float] = None
    rsd_precision: Optional[float] = None
    recovery_accuracy: Optional[float] = None
    tailing_factor: Optional[float] = None
    resolution: Optional[float] = None
    concentration: Optional[float] = None
    run_time: Optional[float] = None
    dosage_form: Optional[str] = None
    elution_type: Optional[str] = None
    linearity_range: Optional[str] = None
    extraction_confidence: Dict[str, float] = field(default_factory=dict)


def extract_parameters_from_text(
    text: str,
    source_file: str = "unknown"
) -> ExtractedMethod:
    """
    Applies regex patterns to extract HPLC validation parameters
    from unstructured text. Returns an ExtractedMethod with all
    found values and extraction confidence scores.
    """
    result = ExtractedMethod(source_file=source_file)

    for param_name, patterns in EXTRACTION_PATTERNS.items():
        best_match = None
        best_confidence = 0.0

        for i, pattern in enumerate(patterns):
            matches = pattern.findall(text)
            if matches:
                # Take the first credible match
                match_val = matches[0]
                # Confidence decreases with pattern specificity rank
                confidence = 1.0 - (i * 0.15)
                if confidence > best_confidence:
                    best_match = match_val
                    best_confidence = confidence

        if best_match is not None:
            result.extraction_confidence[param_name] = best_confidence
            _assign_extracted_value(result, param_name, best_match)

    return result


def _assign_extracted_value(
    result: ExtractedMethod,
    param_name: str,
    value: Any
) -> None:
    """Assigns an extracted value to the correct field with type conversion."""
    try:
        if param_name == "r2_linearity":
            result.r2_linearity = float(value)
        elif param_name == "rsd_precision":
            result.rsd_precision = float(value)
        elif param_name == "recovery_accuracy":
            val = float(value)
            if 80.0 <= val <= 120.0:  # Sanity check
                result.recovery_accuracy = val
        elif param_name == "tailing_factor":
            val = float(value)
            if 0.5 <= val <= 5.0:
                result.tailing_factor = val
        elif param_name == "resolution":
            val = float(value)
            if 0.5 <= val <= 15.0:
                result.resolution = val
        elif param_name == "concentration":
            result.concentration = float(value)
        elif param_name == "run_time":
            result.run_time = float(value)
        elif param_name == "dosage_form":
            result.dosage_form = str(value).lower().strip()
        elif param_name == "elution_type":
            result.elution_type = str(value).lower().strip()
        elif param_name == "linearity_range":
            if isinstance(value, tuple):
                result.linearity_range = f"{value[0]}-{value[1]}%"
            else:
                result.linearity_range = str(value)
    except (ValueError, TypeError):
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  CONVERSION TO TRAINING RECORD
# ─────────────────────────────────────────────────────────────────────────────

DOSAGE_FORM_MAP: Dict[str, int] = {
    "powder": 0, "api": 0,
    "tablet": 1, "capsule": 1, "caplet": 1,
    "cream": 2, "ointment": 2, "gel": 2,
    "suspension": 3, "solution": 3, "injection": 3, "syrup": 3,
}


def extracted_to_training_record(
    extracted: ExtractedMethod,
    defaults: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Converts an ExtractedMethod into a flat dictionary matching
    the TrainingRecord schema for ML training.
    
    Missing values are filled with sensible defaults or flagged.
    """
    d = defaults or {}

    # Map dosage form to integer
    product_matrix = 1  # Default: solid oral
    if extracted.dosage_form:
        for keyword, code in DOSAGE_FORM_MAP.items():
            if keyword in extracted.dosage_form:
                product_matrix = code
                break

    # Map elution type
    elution_enc = 0  # Default: isocratic
    if extracted.elution_type and "gradient" in extracted.elution_type:
        elution_enc = 1

    # Raw features
    r2 = extracted.r2_linearity or d.get("hist_r2_linearity", 0.999)
    rsd = extracted.rsd_precision or d.get("hist_rsd_precision", 0.8)
    recovery = extracted.recovery_accuracy or d.get("hist_recovery_accuracy", 100.0)
    tailing = extracted.tailing_factor or d.get("peak_quality_tailing", 1.2)
    resolution = extracted.resolution or d.get("peak_quality_resolution", 2.5)
    conc = extracted.concentration or d.get("target_concentration", 1.0)
    run_time = extracted.run_time or d.get("run_time_minutes", 10.0)

    record = {
        # Raw features
        "product_matrix": product_matrix,
        "target_concentration": conc,
        "api_stability_score": d.get("api_stability_score", 3.0),
        "prep_complexity": d.get("prep_complexity", 1 + product_matrix // 2),
        "hist_r2_linearity": r2,
        "hist_rsd_precision": rsd,
        "hist_recovery_accuracy": recovery,
        "max_allowed_variance": d.get("max_allowed_variance", 2.0),
        "peak_quality_tailing": tailing,
        "peak_quality_resolution": resolution,
        "n_historical_campaigns": d.get("n_historical_campaigns", 1),
        "instrument_variability": d.get("instrument_variability", 2),
        "reagent_stability": d.get("reagent_stability", 8.0),
        "elution_type_encoded": elution_enc,
        "run_time_minutes": run_time,

        # Engineered features
        "r2_deficit": 1.0 - r2,
        "recovery_deviation": abs(recovery - 100.0),
        "tailing_excess": max(0.0, tailing - 1.0),
        "resolution_deficit": max(0.0, 2.0 - resolution),
        "rsd_over_target": max(0.0, rsd - 1.0),
        "complexity_score": (
            product_matrix * 0.4
            + (1 + product_matrix // 2) * 0.3
            + d.get("api_stability_score", 3.0) / 10.0 * 0.3
        ),
        "chromatographic_risk": (
            elution_enc * 0.5
            + min(1.0, run_time / 60.0) * 0.5
        ),
        "variance_headroom": d.get("max_allowed_variance", 2.0) - rsd,

        # Metadata
        "source_file": extracted.source_file,
    }

    return record


# ─────────────────────────────────────────────────────────────────────────────
#  BATCH PROCESSING PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def process_pdf_directory(
    pdf_dir: str,
    output_csv: str,
    defaults: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """
    Processes all PDFs in a directory, extracts HPLC validation
    parameters, and exports a structured CSV for ML training.
    
    Args:
        pdf_dir: Path to directory containing PDF research papers
        output_csv: Path for the output CSV file
        defaults: Default values for parameters not extractable from text
    
    Returns:
        DataFrame with all extracted training records
    """
    pdf_files = list(Path(pdf_dir).glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files in {pdf_dir}")

    all_records = []
    extraction_report = []

    for pdf_path in pdf_files:
        print(f"\nProcessing: {pdf_path.name}")
        try:
            text = extract_text_from_pdf(str(pdf_path))
            extracted = extract_parameters_from_text(text, pdf_path.name)

            # Log extraction quality
            n_found = sum(
                1 for v in [
                    extracted.r2_linearity, extracted.rsd_precision,
                    extracted.recovery_accuracy, extracted.tailing_factor,
                    extracted.resolution, extracted.run_time,
                ] if v is not None
            )
            print(f"  Extracted {n_found}/6 core parameters")
            print(f"  Confidence: {extracted.extraction_confidence}")

            record = extracted_to_training_record(extracted, defaults)
            all_records.append(record)

            extraction_report.append({
                "file": pdf_path.name,
                "params_found": n_found,
                "r2_found": extracted.r2_linearity is not None,
                "rsd_found": extracted.rsd_precision is not None,
                "recovery_found": extracted.recovery_accuracy is not None,
                "confidence": extracted.extraction_confidence,
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            extraction_report.append({
                "file": pdf_path.name,
                "params_found": 0,
                "error": str(e),
            })

    if all_records:
        df = pd.DataFrame(all_records)
        # Drop metadata column before saving
        save_cols = [c for c in df.columns if c != "source_file"]
        df[save_cols].to_csv(output_csv, index=False)
        print(f"\n{'='*60}")
        print(f"Exported {len(df)} records to {output_csv}")
        print(f"{'='*60}")
        return df
    else:
        print("No records extracted.")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
#  CLI / DEMO
# ─────────────────────────────────────────────────────────────────────────────

def demo_extraction() -> None:
    """
    Demonstrates the extraction pipeline on a sample text snippet
    (simulating a paragraph from an HPLC validation paper).
    """
    sample_text = """
    RP-HPLC Method Development and Validation for Quantification
    of Entrectinib in Bulk and Pharmaceutical Dosage Form (Tablet).
    
    Chromatographic conditions: C18 column (150 x 4.6 mm, 5 um),
    isocratic elution with ACN:Buffer pH 3.0 (30:70 v/v),
    flow rate 1.0 mL/min, detection at 254 nm, run time 10 min.
    
    Linearity was established over the range 50-150% of the target
    concentration (0.02 mg/mL). The correlation coefficient R2 = 0.9998
    was obtained, demonstrating excellent linearity.
    
    Precision: The %RSD for system precision was 0.42% and for
    method precision was 0.85%, both well within the ICH limit of 2.0%.
    
    Accuracy: Mean recovery was found to be 99.8% across three
    concentration levels (80%, 100%, 120%).
    
    System suitability: Tailing factor = 1.12, Resolution = 3.45,
    Theoretical plates N > 5000.
    """

    print("=" * 60)
    print("  PDF Extraction Pipeline — Demo")
    print("=" * 60)

    extracted = extract_parameters_from_text(sample_text, "demo_paper.pdf")

    print(f"\n  Source: {extracted.source_file}")
    print(f"  R2 Linearity:     {extracted.r2_linearity}")
    print(f"  RSD Precision:    {extracted.rsd_precision}")
    print(f"  Recovery:         {extracted.recovery_accuracy}")
    print(f"  Tailing Factor:   {extracted.tailing_factor}")
    print(f"  Resolution:       {extracted.resolution}")
    print(f"  Concentration:    {extracted.concentration}")
    print(f"  Run Time:         {extracted.run_time}")
    print(f"  Dosage Form:      {extracted.dosage_form}")
    print(f"  Elution Type:     {extracted.elution_type}")
    print(f"  Confidence:       {extracted.extraction_confidence}")

    # Convert to training record
    record = extracted_to_training_record(extracted)
    print(f"\n  Training Record ({len(record)} fields):")
    for k, v in record.items():
        if k != "source_file":
            print(f"    {k:35s} = {v}")


if __name__ == "__main__":
    demo_extraction()
