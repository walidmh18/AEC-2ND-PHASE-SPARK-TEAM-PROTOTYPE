import io
import json
import base64
import logging
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge
from jinja2 import Template

try:
    import pdfkit
except Exception as e:
    pdfkit = None
    logging.warning(f"pdfkit is missing: {e}. HTML fallback will be generated.")

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  1. VISUAL PROOF GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_fmea_radar(fmea_scores: dict) -> str:
    """
    Generates a 5-axis radar chart for the FMEA inputs (1-3 scale).
    Returns Base64 string.
    """
    logger.info("Generating FMEA Radar Chart...")
    
    labels = ['Maturité', 'Matrice', 'Données', 'Criticité', 'Risque']
    # Mapping dictionary keys to labels
    values = [
        fmea_scores.get('maturite_methode', 1),
        fmea_scores.get('complexite_matrice', 1),
        fmea_scores.get('disponibilite_donnees', 1),
        fmea_scores.get('criticite_reglementaire', 1),
        fmea_scores.get('risque_patient', 1)
    ]
    
    # Close the loop
    values += values[:1]
    
    # Calculate angles
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    
    fig, ax = plt.subplots(figsize=(5, 5), subplot_kw=dict(polar=True))
    modern_blue = '#0ea5e9'
    
    ax.plot(angles, values, color=modern_blue, linewidth=2, linestyle='solid')
    ax.fill(angles, values, color=modern_blue, alpha=0.25)
    
    ax.set_ylim(0, 3)
    ax.set_yticks([1, 2, 3])
    ax.set_yticklabels(['1', '2', '3'], color="grey", size=8)
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=11, fontweight='bold', color='#333333')
    ax.tick_params(axis='x', pad=20)
    
    ax.grid(color='#e5e7eb', linestyle='--', linewidth=1)
    ax.spines['polar'].set_color('none')
    
    img_buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img_buf, format='png', dpi=300, transparent=True)
    plt.close()
    
    img_buf.seek(0)
    return base64.b64encode(img_buf.read()).decode('utf-8')

def generate_probability_gauge(probability: float) -> str:
    """
    Generates a half-circle gauge chart showing Monte Carlo probability.
    """
    logger.info("Generating Probability Gauge Chart...")
    
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.axis('equal')
    
    # Background wedge (grey)
    bg_wedge = Wedge((0, 0), 1, 0, 180, width=0.3, color='#e2e8f0')
    ax.add_patch(bg_wedge)
    
    # Value wedge
    val_angle = 180 * probability
    # Colors: Green if >= 0.97, else Red/Orange
    color = '#10b981' if probability >= 0.97 else '#ef4444'
    val_wedge = Wedge((0, 0), 1, 180 - val_angle, 180, width=0.3, color=color)
    ax.add_patch(val_wedge)
    
    # Threshold line at 97% (180 * 0.97 = 174.6 degrees from right, or 5.4 from left)
    threshold_angle = 180 - (180 * 0.97)
    x_thresh = np.cos(np.radians(threshold_angle))
    y_thresh = np.sin(np.radians(threshold_angle))
    ax.plot([0.7 * x_thresh, 1.05 * x_thresh], [0.7 * y_thresh, 1.05 * y_thresh], color='#334155', lw=2, ls='--')
    
    # Text
    pct_text = f"{probability * 100:.2f}%"
    ax.text(0, 0.2, pct_text, ha='center', va='center', fontsize=24, fontweight='bold', color=color)
    ax.text(0, -0.1, "Seuil de Confiance: 97%", ha='center', va='center', fontsize=10, color='#64748b')
    
    ax.axis('off')
    
    img_buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img_buf, format='png', dpi=300, transparent=True)
    plt.close()
    
    img_buf.seek(0)
    return base64.b64encode(img_buf.read()).decode('utf-8')

def generate_kalman_drift_chart(measurements: list, filtered_states: list, threshold: float = 2.0) -> str:
    logger.info("Generating Kalman Drift Chart...")
    if not measurements or not filtered_states:
        return ""
        
    fig, ax = plt.subplots(figsize=(6, 4))
    
    # Plot noisy measurements
    ax.scatter(range(len(measurements)), measurements, color='gray', alpha=0.6, label="Raw Data (Bruitée)")
    
    # Plot EKF smoothed states
    ax.plot(range(len(filtered_states)), filtered_states, color='blue', linewidth=2, label="EKF State (Lissée)")
    
    # Plot Threshold
    ax.axhline(y=threshold, color='red', linestyle='--', linewidth=1.5, label="Seuil Critique (Rs < 2.0)")
    
    ax.set_title("Suivi de Dégradation de Colonne HPLC (Filtre de Kalman)", fontsize=10, fontweight='bold', color='#1e293b', pad=10)
    ax.set_xlabel("Campagnes / Mois", fontsize=9, color='#475569')
    ax.set_ylabel("Résolution (Rs)", fontsize=9, color='#475569')
    ax.legend(loc='lower left', fontsize=8)
    
    # Grid
    ax.grid(True, linestyle='--', alpha=0.5)
    
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=150, transparent=True)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return img_b64

# ─────────────────────────────────────────────────────────────────────────────
#  2. HTML/CSS TEMPLATE
# ─────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>BIOPHARM - Rapport SPARK AQbD</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        
        body {
            font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
            color: #334155;
            background-color: #ffffff;
            margin: 0;
            padding: 40px;
            line-height: 1.6;
        }
        
        .header {
            border-bottom: 3px solid #0ea5e9;
            padding-bottom: 20px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
        }
        
        .header h1 {
            color: #0f172a;
            margin: 0;
            font-size: 28px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .header .subtitle {
            color: #64748b;
            font-size: 14px;
            margin-top: 5px;
        }
        
        .section-box {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 25px;
            margin-bottom: 30px;
        }
        
        h2 {
            color: #0ea5e9;
            font-size: 20px;
            margin-top: 0;
            margin-bottom: 20px;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 8px;
            display: flex;
            align-items: center;
        }
        
        .flex-row {
            display: flex;
            gap: 30px;
            align-items: center;
        }
        
        .flex-col {
            flex: 1;
        }
        
        .metric {
            margin-bottom: 20px;
        }
        
        .metric-label {
            font-weight: 600;
            color: #475569;
            font-size: 13px;
            text-transform: uppercase;
        }
        
        .metric-value {
            font-size: 22px;
            color: #0f172a;
            font-weight: 700;
        }
        
        .decision-badge {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 16px;
        }
        
        .bg-green { background: #d1fae5; color: #047857; }
        .bg-red { background: #fee2e2; color: #b91c1c; }
        .bg-blue { background: #e0f2fe; color: #0369a1; }
        
        .chart-img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            background: white;
            border-radius: 6px;
            overflow: hidden;
            border: 1px solid #e2e8f0;
        }
        
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }
        
        th {
            background-color: #f1f5f9;
            color: #475569;
            font-weight: 600;
            font-size: 13px;
        }
        
        tr:last-child td {
            border-bottom: none;
        }
        
        .footer {
            margin-top: 50px;
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
            border-top: 1px solid #e2e8f0;
            padding-top: 20px;
        }
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>BIOPHARM</h1>
            <div class="subtitle">Méthodologie SPARK : Rapport de Validation (ICH Q14)</div>
        </div>
    </div>

    <!-- SECTION 1: FMEA -->
    <div class="section-box">
        <h2>1. Évaluation des Risques (FMEA)</h2>
        <div class="flex-row">
            <div class="flex-col">
                <div class="metric">
                    <div class="metric-label">Score RPN (Risk Priority Number)</div>
                    <div class="metric-value">{{ rpn }} / 15</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Décision de Base</div>
                    <div class="decision-badge bg-blue">{{ decision }}</div>
                </div>
            </div>
            <div class="flex-col" style="text-align: center;">
                <img class="chart-img" src="data:image/png;base64, {{ radar_chart_base64 }}" style="max-width: 250px;" alt="FMEA Radar">
            </div>
        </div>
    </div>

    <!-- SECTION 2: SEQUENTIAL -->
    <div class="section-box">
        <h2>2. Co-Pilote Séquentiel (Monte Carlo)</h2>
        <div class="flex-row">
            <div class="flex-col" style="text-align: center;">
                <img class="chart-img" src="data:image/png;base64, {{ gauge_chart_base64 }}" style="max-width: 280px;" alt="Probability Gauge">
            </div>
            <div class="flex-col">
                <div class="metric">
                    <div class="metric-label">Statut de la Séquence</div>
                    <div class="decision-badge {% if sequential_decision == 'ARRÊT POSITIF' %}bg-green{% else %}bg-red{% endif %}">
                        {{ sequential_decision }}
                    </div>
                </div>
                <div class="metric">
                    <div class="metric-label">Injections Économisées</div>
                    <div class="metric-value" style="color: #10b981;">+{{ saved_injections }} Injections</div>
                </div>
            </div>
        </div>
    </div>

    <!-- SECTION 3: BAYESIAN -->
    <div class="section-box">
        <h2>3. Savoir Historique (Fusion Bayésienne)</h2>
        <p style="font-size: 14px; color: #475569; margin-bottom: 15px;">
            Fusion mathématique du "Prior" (campagnes précédentes) avec le "Likelihood" (nouvelles données partielles).
        </p>
        <table>
            <thead>
                <tr>
                    <th>Métrique Bayésienne</th>
                    <th>Valeur</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Pente Postérieure (Moyenne Fûtée)</strong></td>
                    <td>{{ posterior_slope_mean }}</td>
                </tr>
                <tr>
                    <td><strong>Variance Postérieure (Incertitude)</strong></td>
                    <td>{{ posterior_slope_var }}</td>
                </tr>
                <tr>
                    <td><strong>Poids du Savoir Historique (Prior)</strong></td>
                    <td><strong style="color: #0ea5e9;">{{ prior_influence_pct }}%</strong></td>
                </tr>
                <tr>
                    <td><strong>Poids des Nouvelles Données (Likelihood)</strong></td>
                    <td>{{ data_influence_pct }}%</td>
                </tr>
            </tbody>
        </table>
    </div>

    <!-- SECTION 4: KALMAN FILTER -->
    <div class="section-box">
        <h2>4. Maintenance Prédictive (Filtre de Kalman)</h2>
        <p style="font-size: 14px; color: #475569; margin-bottom: 15px;">
            Le filtre de Kalman étendu prédit que la colonne nécessitera un remplacement dans <strong style="color: #ef4444;">{{ projected_remaining_campaigns }} campagnes</strong> avant de franchir le seuil critique.
        </p>
        <div style="text-align: center;">
            <img class="chart-img" src="data:image/png;base64, {{ kalman_chart_base64 }}" style="max-width: 100%;" alt="Kalman Drift Chart">
        </div>
    </div>


    <div class="footer">
        Généré automatiquement par le Moteur SPARK BIOPHARM &bull; Document Confidentiel
    </div>

</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
#  3. PDF GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_pdf_report(payload: dict, output_path: str):
    logger.info("Starting SPARK PDF generation pipeline...")
    
    # 1. Generate charts
    fmea_scores = payload.get("fmea_scores", {})
    radar_chart_base64 = generate_fmea_radar(fmea_scores)
    
    # Scale probability appropriately for the gauge chart which expects 0-1
    probability = payload.get("probability", 0.0)
    if probability > 1.0:
        probability = probability / 100.0
    gauge_chart_base64 = generate_probability_gauge(probability)
    
    kalman_chart_base64 = generate_kalman_drift_chart(
        payload.get("kalman_measurements", []),
        payload.get("kalman_filtered_states", [])
    )
    
    # 2. Render HTML
    logger.info("Rendering HTML Template with Jinja2...")
    template = Template(HTML_TEMPLATE)
    
    rendered_html = template.render(
        rpn=payload.get("rpn", 0),
        decision=payload.get("decision", ""),
        probability=payload.get("probability", 0.0),
        saved_injections=payload.get("saved_injections", 0),
        sequential_decision=payload.get("sequential_decision", ""),
        posterior_slope_mean=payload.get("posterior_slope_mean", 0.0),
        posterior_slope_var=payload.get("posterior_slope_var", 0.0),
        prior_influence_pct=payload.get("prior_influence_pct", 0.0),
        data_influence_pct=payload.get("data_influence_pct", 0.0),
        radar_chart_base64=radar_chart_base64,
        gauge_chart_base64=gauge_chart_base64,
        kalman_chart_base64=kalman_chart_base64,
        projected_remaining_campaigns=payload.get("projected_remaining_campaigns", 0)
    )
    
    # 3. Write to PDF
    if pdfkit is None:
        logger.error("Cannot generate PDF: pdfkit is not available.")
        html_fallback = output_path.replace(".pdf", ".html")
        with open(html_fallback, "w", encoding="utf-8") as f:
            f.write(rendered_html)
        logger.info(f"Saved HTML fallback to {html_fallback}")
        return
        
    logger.info(f"Converting HTML to PDF via pdfkit...")
    try:
        path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
        
        options = {
            'page-size': 'A4',
            'margin-top': '0mm',
            'margin-right': '0mm',
            'margin-bottom': '0mm',
            'margin-left': '0mm',
            'encoding': "UTF-8",
            'enable-local-file-access': None
        }
        
        pdfkit.from_string(rendered_html, output_path, configuration=config, options=options)
        logger.info(f"Successfully saved PDF to {output_path}")
    except Exception as e:
        logger.error(f"pdfkit failed: {e}")
        html_fallback = output_path.replace(".pdf", ".html")
        with open(html_fallback, "w", encoding="utf-8") as f:
            f.write(rendered_html)
        logger.info(f"Saved HTML fallback to {html_fallback}")

# ─────────────────────────────────────────────────────────────────────────────
#  4. EXECUTION FLOW
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("="*60)
    print("  SPARK PDF Report Generator")
    print("="*60)
    
    dummy_api_response = {
        # FMEA Data
        "rpn": 10,
        "decision": "PLAN RÉDUIT (4 niveaux x 2 réplicats = 8 injections)",
        "fmea_scores": {"Maturité": 2, "Matrice": 3, "Données": 1, "Réglementaire": 2, "Patient": 2},
        
        # Sequential Data
        "probability": 99.16,
        "saved_injections": 7,
        "sequential_decision": "ARRÊT POSITIF",
        
        # Bayesian Data
        "posterior_slope_mean": 1.0151,
        "posterior_slope_var": 0.000025,
        "prior_influence_pct": 98.0,
        "data_influence_pct": 2.0,
        
        # EKF Data
        "kalman_measurements": [3.2, 3.0, 3.1, 2.8, 2.9, 2.6, 2.5, 2.4, 2.5, 2.2],
        "kalman_filtered_states": [3.2, 3.09, 3.09, 2.92, 2.9, 2.7, 2.57, 2.45, 2.46, 2.28],
        "projected_remaining_campaigns": 3
    }
    
    try:
        generate_pdf_report(dummy_api_response, "SPARK_Final_Report.pdf")
        print("\n[SUCCESS] SPARK_Final_Report.pdf generated.")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
