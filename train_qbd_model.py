"""
QbD ML Training Pipeline — Supervised Classification
=====================================================
Generates synthetic HPLC validation data seeded from real Biopharm
historical campaigns, trains RandomForest + XGBoost classifiers,
outputs feature importance and exports model as .pkl.

Author:  BIOPHARM Competition Team
Version: 2.0.0
"""

from __future__ import annotations
import os
import json
import pickle
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import (
    StratifiedKFold, cross_val_score, train_test_split
)
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score
)
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
#  REAL DATA EXTRACTION — Biopharm Historical Campaigns
# ─────────────────────────────────────────────────────────────────────────────

# Extracted from the CSV files in FINAL BIOPHARM folder:
#   - Linéarité Principe Actif (19/04/2023): R²=0.999637, slope=5478.94
#   - Linéarite Placebo Chargé (19/04/2023): R²=0.999887, slope=5626.38
#   - Linéarité PA 50mg (26/05/2025): R²=0.999107, slope=15436.87
#   - FC020 Placebo chargé 500mg (26/05/2025): R²=0.999313, slope=15326.02
#   - FC020 Placebo chargé (16/03/2026): R²=0.993359
#   - Calcul exactitude 50mg: recovery 99.7-101.7%, mean ~100.3%

REAL_CAMPAIGNS: List[Dict] = [
    {
        "product": "Comprime_50mg",
        "dosage_form": "coated_tablet",
        "r2_pa": 0.999107,
        "r2_placebo": 0.999313,
        "slope_pa": 15436.87,
        "slope_placebo": 15326.02,
        "recovery_mean": 100.27,
        "recovery_rsd": 0.70,
        "bias_mean_pct": 100.02,
        "extraction_steps": 1,
        "run_time": 10.0,
        "elution": "isocratic",
    },
    {
        "product": "Comprime_500mg",
        "dosage_form": "coated_tablet",
        "r2_pa": 0.999637,
        "r2_placebo": 0.999887,
        "slope_pa": 5478.94,
        "slope_placebo": 5626.38,
        "recovery_mean": 100.01,
        "recovery_rsd": 0.42,
        "bias_mean_pct": 100.00,
        "extraction_steps": 1,
        "run_time": 10.0,
        "elution": "isocratic",
    },
    {
        "product": "Gelules_25_50_100mg",
        "dosage_form": "api_powder",
        "r2_pa": 0.9995,
        "r2_placebo": 0.9993,
        "slope_pa": 5500.0,
        "slope_placebo": 5400.0,
        "recovery_mean": 99.8,
        "recovery_rsd": 0.55,
        "bias_mean_pct": 99.9,
        "extraction_steps": 1,
        "run_time": 10.0,
        "elution": "isocratic",
    },
    {
        "product": "Creme_0.1pct",
        "dosage_form": "cream",
        "r2_pa": 0.9936,
        "r2_placebo": 0.9934,
        "slope_pa": 12000.0,
        "slope_placebo": 11800.0,
        "recovery_mean": 99.25,
        "recovery_rsd": 1.2,
        "bias_mean_pct": 99.25,
        "extraction_steps": 3,
        "run_time": 15.0,
        "elution": "isocratic",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
#  SYNTHETIC DATA GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

DOSAGE_FORMS = ["api_powder", "coated_tablet", "suspension", "cream"]
ELUTION_TYPES = ["isocratic", "gradient"]


def _label_from_params(row: Dict) -> int:
    """
    Determines the target label based on ICH regulatory thresholds.
    1 = Full Validation Required (FAIL / high risk)
    0 = Safe to Optimize (PASS / low risk)

    Uses a probabilistic boundary near ICH limits to create
    realistic class separation.
    """
    penalties = 0.0

    # R² check — ICH limit 0.990
    if row["hist_r2_linearity"] < 0.990:
        penalties += 3.0
    elif row["hist_r2_linearity"] < 0.995:
        penalties += 1.5
    elif row["hist_r2_linearity"] < 0.999:
        penalties += 0.5

    # RSD check — ICH limit 2.0%
    if row["hist_rsd_precision"] > 2.0:
        penalties += 3.0
    elif row["hist_rsd_precision"] > 1.5:
        penalties += 1.5
    elif row["hist_rsd_precision"] > 1.0:
        penalties += 0.5

    # Recovery check — ICH limits 98-102%
    recovery_dev = abs(row["hist_recovery_accuracy"] - 100.0)
    if recovery_dev > 2.0:
        penalties += 3.0
    elif recovery_dev > 1.5:
        penalties += 1.5
    elif recovery_dev > 1.0:
        penalties += 0.5

    # Tailing factor — limit 2.0
    if row["system_suitability_tailing"] > 2.0:
        penalties += 2.0
    elif row["system_suitability_tailing"] > 1.5:
        penalties += 1.0

    # Resolution — limit 1.5
    if row["system_suitability_resolution"] < 1.5:
        penalties += 2.5
    elif row["system_suitability_resolution"] < 2.0:
        penalties += 1.0

    # Matrix complexity
    form_penalty = {
        "api_powder": 0.0, "coated_tablet": 0.3,
        "suspension": 1.0, "cream": 1.5,
    }
    penalties += form_penalty.get(row["dosage_form"], 0.5)

    # Extraction steps
    penalties += row["extraction_steps"] * 0.3

    # API stability
    if row["api_stability"] > 7:
        penalties += 1.5
    elif row["api_stability"] > 4:
        penalties += 0.5

    # Gradient elution
    if row["elution_type"] == "gradient":
        penalties += 0.8

    # Run time
    if row["run_time_minutes"] > 30:
        penalties += 1.0
    elif row["run_time_minutes"] > 15:
        penalties += 0.3

    # Decision boundary with stochastic noise
    threshold = 4.5
    noise = np.random.normal(0, 0.5)
    return 1 if (penalties + noise) >= threshold else 0


def generate_synthetic_dataset(
    n_samples: int = 5000,
    seed: int = 42,
    real_data_weight: float = 0.15,
) -> pd.DataFrame:
    """
    Generates a synthetic dataset of realistic HPLC method scenarios.

    A fraction (real_data_weight) of samples are perturbed versions of
    real Biopharm campaign data. The rest are fully synthetic but
    distributed to match realistic pharmaceutical method profiles.
    """
    rng = np.random.default_rng(seed)
    records = []

    n_real_seeded = int(n_samples * real_data_weight)
    n_synthetic = n_samples - n_real_seeded

    # ── Real-data-seeded samples ──
    for _ in range(n_real_seeded):
        campaign = REAL_CAMPAIGNS[rng.integers(0, len(REAL_CAMPAIGNS))]
        record = {
            "dosage_form": campaign["dosage_form"],
            "extraction_steps": max(0, campaign["extraction_steps"]
                                    + rng.integers(-1, 2)),
            "api_stability": round(rng.uniform(1.0, 5.0), 1),
            "target_concentration": round(rng.uniform(0.5, 2.0), 2),
            "hist_rsd_precision": round(max(0.05, campaign["recovery_rsd"]
                                            + rng.normal(0, 0.2)), 3),
            "hist_r2_linearity": round(min(1.0, max(0.980,
                campaign["r2_pa"] + rng.normal(0, 0.002))), 6),
            "hist_recovery_accuracy": round(
                campaign["recovery_mean"] + rng.normal(0, 0.5), 2),
            "system_suitability_tailing": round(
                max(0.8, rng.normal(1.15, 0.2)), 2),
            "system_suitability_resolution": round(
                max(1.0, rng.normal(2.5, 0.4)), 2),
            "elution_type": campaign["elution"],
            "run_time_minutes": round(max(3, campaign["run_time"]
                                          + rng.normal(0, 3)), 1),
        }
        record["full_validation_required"] = _label_from_params(record)
        records.append(record)

    # ── Fully synthetic samples ──
    for _ in range(n_synthetic):
        dosage = rng.choice(DOSAGE_FORMS, p=[0.20, 0.35, 0.25, 0.20])
        extract_steps = int(rng.choice(
            [0, 1, 2, 3, 4],
            p=[0.10, 0.35, 0.30, 0.15, 0.10]
        ))

        # R² distribution: most methods are > 0.995, some outliers
        r2_base = rng.beta(15, 0.3)  # heavily skewed toward 1.0
        r2 = round(0.980 + r2_base * 0.020, 6)
        r2 = min(r2, 0.99999)

        # RSD: most < 1.0, tail toward 2.5
        rsd = round(max(0.05, rng.lognormal(-0.5, 0.6)), 3)
        rsd = min(rsd, 4.0)

        # Recovery: centered at 100, spread to 96-104
        recovery = round(rng.normal(100.0, 1.0), 2)
        recovery = max(95.0, min(105.0, recovery))

        record = {
            "dosage_form": dosage,
            "extraction_steps": extract_steps,
            "api_stability": round(rng.uniform(1.0, 10.0), 1),
            "target_concentration": round(
                max(0.01, rng.lognormal(0.0, 0.8)), 3),
            "hist_rsd_precision": rsd,
            "hist_r2_linearity": r2,
            "hist_recovery_accuracy": recovery,
            "system_suitability_tailing": round(
                max(0.8, rng.lognormal(0.1, 0.25)), 2),
            "system_suitability_resolution": round(
                max(0.5, rng.normal(2.3, 0.5)), 2),
            "elution_type": rng.choice(ELUTION_TYPES, p=[0.60, 0.40]),
            "run_time_minutes": round(max(3, rng.lognormal(2.5, 0.5)), 1),
        }
        record["full_validation_required"] = _label_from_params(record)
        records.append(record)

    df = pd.DataFrame(records)
    # Shuffle
    df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────

def encode_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    Encodes categorical features and engineers derived features.
    Returns (X dataframe, feature_names list).
    """
    df_enc = df.copy()

    # Encode categoricals
    df_enc["dosage_form_encoded"] = LabelEncoder().fit_transform(
        df_enc["dosage_form"]
    )
    df_enc["elution_type_encoded"] = (
        df_enc["elution_type"].map({"isocratic": 0, "gradient": 1})
    )

    # Derived features
    df_enc["r2_deficit"] = 1.0 - df_enc["hist_r2_linearity"]
    df_enc["recovery_deviation"] = abs(
        df_enc["hist_recovery_accuracy"] - 100.0
    )
    df_enc["tailing_excess"] = np.maximum(
        0, df_enc["system_suitability_tailing"] - 1.0
    )
    df_enc["resolution_deficit"] = np.maximum(
        0, 2.0 - df_enc["system_suitability_resolution"]
    )
    df_enc["rsd_over_target"] = np.maximum(
        0, df_enc["hist_rsd_precision"] - 1.0
    )
    df_enc["complexity_score"] = (
        df_enc["dosage_form_encoded"] * 0.4
        + df_enc["extraction_steps"] * 0.3
        + df_enc["api_stability"] / 10.0 * 0.3
    )
    df_enc["chromatographic_risk"] = (
        df_enc["elution_type_encoded"] * 0.5
        + np.log1p(df_enc["run_time_minutes"]) / 4.0 * 0.5
    )

    feature_cols = [
        "dosage_form_encoded",
        "extraction_steps",
        "api_stability",
        "target_concentration",
        "hist_rsd_precision",
        "hist_r2_linearity",
        "hist_recovery_accuracy",
        "system_suitability_tailing",
        "system_suitability_resolution",
        "elution_type_encoded",
        "run_time_minutes",
        # Derived
        "r2_deficit",
        "recovery_deviation",
        "tailing_excess",
        "resolution_deficit",
        "rsd_over_target",
        "complexity_score",
        "chromatographic_risk",
    ]

    return df_enc[feature_cols], feature_cols


# ─────────────────────────────────────────────────────────────────────────────
#  MODEL TRAINING
# ─────────────────────────────────────────────────────────────────────────────

def train_models(
    X: pd.DataFrame,
    y: pd.Series,
    feature_names: List[str],
    output_dir: str = ".",
) -> Dict:
    """
    Trains RandomForest and GradientBoosting (XGBoost-like) classifiers.
    Performs stratified cross-validation, exports the best model as .pkl.
    """
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # ── RandomForest ──
    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        min_samples_split=10,
        min_samples_leaf=5,
        max_features="sqrt",
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    # ── GradientBoosting (scikit-learn's XGBoost equivalent) ──
    gb = GradientBoostingClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_split=10,
        min_samples_leaf=5,
        random_state=42,
    )

    results = {}
    best_model = None
    best_score = 0.0
    best_name = ""

    for name, model in [("RandomForest", rf), ("GradientBoosting", gb)]:
        print(f"\n{'='*60}")
        print(f"  Training: {name}")
        print(f"{'='*60}")

        # Cross-validation
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        cv_scores = cross_val_score(
            model, X_train, y_train, cv=cv, scoring="roc_auc"
        )
        print(f"  CV ROC-AUC: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

        # Fit on full training set
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]

        test_auc = roc_auc_score(y_test, y_prob)
        print(f"  Test ROC-AUC: {test_auc:.4f}")
        print(f"\n  Classification Report:")
        print(classification_report(y_test, y_pred))

        # Feature importance
        importances = model.feature_importances_
        fi = sorted(
            zip(feature_names, importances),
            key=lambda x: x[1],
            reverse=True,
        )
        print(f"  Feature Importance (Top 10):")
        for fname, imp in fi[:10]:
            bar = "#" * int(imp * 50)
            print(f"    {fname:35s} {imp:.4f} {bar}")

        results[name] = {
            "model": model,
            "cv_auc_mean": round(cv_scores.mean(), 4),
            "cv_auc_std": round(cv_scores.std(), 4),
            "test_auc": round(test_auc, 4),
            "feature_importance": {fn: round(fi_v, 4) for fn, fi_v in fi},
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        }

        if test_auc > best_score:
            best_score = test_auc
            best_model = model
            best_name = name

    # ── Export best model ──
    model_path = os.path.join(output_dir, "qbd_risk_model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": best_model,
            "model_name": best_name,
            "feature_names": feature_names,
            "test_auc": best_score,
        }, f)
    print(f"\n{'='*60}")
    print(f"  Best Model: {best_name} (AUC={best_score:.4f})")
    print(f"  Exported to: {model_path}")
    print(f"{'='*60}")

    # ── Export feature importance as JSON ──
    fi_path = os.path.join(output_dir, "feature_importance.json")
    with open(fi_path, "w") as f:
        json.dump(results[best_name]["feature_importance"], f, indent=2)
    print(f"  Feature importance saved to: {fi_path}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Full pipeline: generate data → engineer features → train → export."""
    output_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 60)
    print("  QbD ML Training Pipeline — BIOPHARM Competition")
    print("=" * 60)

    # Step 1: Generate synthetic dataset
    print("\n[1/4] Generating synthetic dataset (5,000 samples)...")
    df = generate_synthetic_dataset(n_samples=5000, seed=42)
    dataset_path = os.path.join(output_dir, "synthetic_hplc_dataset.csv")
    df.to_csv(dataset_path, index=False)
    print(f"  Dataset saved to: {dataset_path}")
    print(f"  Shape: {df.shape}")
    print(f"  Class distribution:\n{df['full_validation_required'].value_counts()}")

    # Step 2: Feature engineering
    print("\n[2/4] Engineering features...")
    y = df["full_validation_required"]
    X, feature_names = encode_features(df)
    print(f"  Features: {len(feature_names)}")
    print(f"  Samples: {len(X)}")

    # Step 3: Train models
    print("\n[3/4] Training models...")
    results = train_models(X, y, feature_names, output_dir=output_dir)

    # Step 4: Summary
    print("\n[4/4] Pipeline complete.")
    print(f"  Files created:")
    print(f"    - synthetic_hplc_dataset.csv")
    print(f"    - qbd_risk_model.pkl")
    print(f"    - feature_importance.json")


if __name__ == "__main__":
    main()
