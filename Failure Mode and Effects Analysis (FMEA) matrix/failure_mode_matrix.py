class QbDValidationEngine:
    def __init__(self):
        # Define the thresholds for the Risk Priority Number (RPN)
        self.LOW_RISK_MAX = 8
        self.MED_RISK_MAX = 17

    def calculate_rpn(self, matrix_complexity, historical_reliability, method_vulnerability):
        """Calculates the Risk Priority Number based on three 1-3 inputs."""
        return matrix_complexity * historical_reliability * method_vulnerability

    def get_validation_plan(self, product_name, v1, v2, v3):
        """Processes the inputs through the FMEA logic gates."""
        
        # 1. Calculate the Risk Score
        rpn = self.calculate_rpn(v1, v2, v3)
        
        # 2. Base Output Dictionary
        report = {
            "Product": product_name,
            "RPN_Score": rpn,
            "Risk_Level": "",
            "Recommended_Action": "",
            "Scientific_Justification": ""
        }

        # 3. Decision Logic Gates
        if rpn <= self.LOW_RISK_MAX:
            report["Risk_Level"] = "LOW RISK (Green Zone)"
            report["Recommended_Action"] = "Reduced Validation Plan. Linearity: 3 Levels (80%, 100%, 120%), 2 Replicates."
            report["Scientific_Justification"] = "Historical data proves 0% failure rate at extreme spectrums. Redundant testing eliminated per ICH Q14."
            
        elif rpn <= self.MED_RISK_MAX:
            report["Risk_Level"] = "MEDIUM RISK (Yellow Zone)"
            report["Recommended_Action"] = "Standard Validation Plan. Linearity: 5 Levels (80% - 120%), 2 Replicates."
            report["Scientific_Justification"] = "Moderate historical variance dictates standard boundary testing, but replicates can be safely reduced."
            
        else:
            report["Risk_Level"] = "HIGH RISK (Red Zone)"
            report["Recommended_Action"] = "Full ICH Q2(R2) Plan. Linearity: 5 Levels (70% - 130%), 3 Replicates."
            report["Scientific_Justification"] = "High matrix complexity and/or historical instability requires comprehensive boundary testing to ensure patient safety."

        return report

# ==========================================
# SIMULATION: Testing the Engine
# ==========================================

# Initialize our engine
engine = QbDValidationEngine()

# Scenario 1: A simple 50mg Capsule (Low complexity) with great historical data
print("--- Scenario 1: BIOPHARM 50mg Capsule ---")
capsule_result = engine.get_validation_plan(
    product_name="Capsule 50mg",
    v1=1, # Matrix: Simple powder
    v2=1, # History: R^2 > 0.9995
    v3=1  # Method: Simple Isocratic
)
for key, value in capsule_result.items():
    print(f"{key}: {value}")

print("\n")

# Scenario 2: A complex skin cream with fluctuating historical data
print("--- Scenario 2: BIOPHARM Skin Cream ---")
cream_result = engine.get_validation_plan(
    product_name="Dermatological Cream",
    v1=3, # Matrix: Complex extraction needed
    v2=3, # History: RSD often > 2.0%
    v3=2  # Method: Gradient HPLC
)
for key, value in cream_result.items():
    print(f"{key}: {value}")