import numpy as np
from scipy import stats
from typing import Dict, List, Union

class SparkRiskAssessment:
    """
    FMEA Risk Calculator for the SPARK Approach.
    Evaluates method risk on a scale of 5-15 to determine the required validation plan.
    """
    
    def __init__(self):
        pass

    def calculate_rpn(
        self,
        maturite_methode: int,
        complexite_matrice: int,
        disponibilite_donnees: int,
        criticite_reglementaire: int,
        risque_patient: int
    ) -> Dict[str, Union[int, str]]:
        """
        Calculates the cumulative Risk Priority Number (RPN) based on 5 axes (each scored 1-3).
        """
        # Validate inputs
        inputs = [
            maturite_methode, complexite_matrice, disponibilite_donnees,
            criticite_reglementaire, risque_patient
        ]
        
        for val in inputs:
            if val not in [1, 2, 3]:
                raise ValueError("All FMEA inputs must be exactly 1, 2, or 3.")
                
        # Cumulative logic for SPARK approach RPN
        rpn = sum(inputs)
        
        if 12 <= rpn <= 15:
            decision = "PLAN COMPLET (15 injections)"
        elif 8 <= rpn <= 11:
            decision = "PLAN RÉDUIT (4 niveaux x 2 réplicats = 8 injections)"
        elif 5 <= rpn <= 7:
            decision = "PLAN LEVERAGED (Fusion bayésienne)"
        else:
            decision = "INVALIDE"
            
        return {
            "rpn": rpn,
            "decision": decision
        }


class SequentialCopilot:
    """
    Sequential Analysis Co-Pilot using Monte Carlo Simulation.
    Determines if an ongoing HPLC linearity run can be stopped early with 97% confidence
    that the final R^2 will be >= 0.999.
    """
    
    def __init__(self, simulations: int = 10000):
        self.simulations = simulations

    def evaluate_early_stopping(
        self,
        current_x: List[float],
        current_y: List[float],
        total_target_points: int = 15,
        remaining_x: List[float] = None
    ) -> Dict[str, Union[str, float, int]]:
        """
        Evaluates the probability of reaching R^2 >= 0.999 if the run is stopped early.
        """
        x_arr = np.array(current_x)
        y_arr = np.array(current_y)
        n_current = len(x_arr)
        
        if n_current >= total_target_points:
            return {"decision": "ARRÊT POSITIF", "probability": 1.0, "saved_injections": 0}
            
        if n_current < 3:
            return {"decision": "CONTINUER", "probability": 0.0, "message": "Not enough data for regression."}

        # 1. Perform linear regression on current data
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_arr, y_arr)
        
        # Calculate current residuals and standard error (sigma)
        predictions = slope * x_arr + intercept
        residuals = y_arr - predictions
        # Root Mean Square Error (RMSE) for sigma
        sigma = np.sqrt(np.sum(residuals**2) / (n_current - 2))
        
        # If sigma is effectively 0, add a tiny noise to prevent perfect simulations
        if sigma < 1e-6:
            sigma = 1e-6

        # Determine x values for the missing points
        n_missing = total_target_points - n_current
        if remaining_x is None:
            # Assume remaining points are evenly distributed across the existing x range
            x_missing = np.linspace(min(x_arr), max(x_arr), n_missing)
        else:
            x_missing = np.array(remaining_x)
            if len(x_missing) != n_missing:
                raise ValueError(f"remaining_x must have exactly {n_missing} elements.")

        # 2 & 3. Monte Carlo Simulation (Vectorized for extreme performance)
        # Generate random noise for all missing points across all simulations
        # Shape: (simulations, n_missing)
        noise = np.random.normal(0, sigma, size=(self.simulations, n_missing))
        
        # Calculate theoretical Y for missing points: y = a*x + b
        y_missing_theoretical = slope * x_missing + intercept
        
        # Add noise to get simulated Y values
        y_missing_simulated = y_missing_theoretical + noise
        
        # Combine existing data with simulated data
        # To calculate R^2 quickly for 10,000 simulations, we use numpy matrix operations
        # R^2 = 1 - (SS_res / SS_tot)
        
        # Full X array (same for all simulations)
        x_full = np.concatenate([x_arr, x_missing])
        x_mean = np.mean(x_full)
        ss_tot_x = np.sum((x_full - x_mean)**2)
        
        # Full Y array for all simulations
        # Shape: (simulations, total_target_points)
        y_full = np.concatenate([np.tile(y_arr, (self.simulations, 1)), y_missing_simulated], axis=1)
        
        # Calculate R^2 for each simulation
        y_means = np.mean(y_full, axis=1, keepdims=True)
        ss_tot = np.sum((y_full - y_means)**2, axis=1)
        
        # Numerator for slope: sum((x - x_mean) * (y - y_mean))
        covariance = np.sum((x_full - x_mean) * (y_full - y_means), axis=1)
        
        # Calculated slopes for simulations
        sim_slopes = covariance / ss_tot_x
        sim_intercepts = y_means.flatten() - sim_slopes * x_mean
        
        # Predicted Y for all simulations
        y_pred = sim_slopes[:, np.newaxis] * x_full + sim_intercepts[:, np.newaxis]
        
        # Residual sum of squares
        ss_res = np.sum((y_full - y_pred)**2, axis=1)
        
        # R^2 array
        r2_simulated = 1 - (ss_res / ss_tot)
        
        # 4. Count successes
        success_count = np.sum(r2_simulated >= 0.999)
        probability = success_count / self.simulations
        
        # 5 & 6. Decision Logic
        if probability >= 0.97:
            return {
                "decision": "ARRÊT POSITIF",
                "probability": float(probability),
                "saved_injections": n_missing
            }
        else:
            return {
                "decision": "CONTINUER",
                "probability": float(probability)
            }


# ─────────────────────────────────────────────────────────────────────────────
#  EXECUTION BLOCK
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("="*60)
    print("  SPARK ENGINE: Mathematical Risk & Sequential Analysis")
    print("="*60)
    
    # --- TASK 1: FMEA Risk Calculator ---
    print("\n--- [1] FMEA RISK ASSESSMENT ---")
    assessor = SparkRiskAssessment()
    
    # Scenario: High Matrix Complexity (3), High Data Availability (1) -> low risk for data
    # maturite=2, complexite=3, dispo=1, criticite=2, patient=2 -> Total: 10
    risk_result = assessor.calculate_rpn(
        maturite_methode=2,
        complexite_matrice=3,
        disponibilite_donnees=1,
        criticite_reglementaire=2,
        risque_patient=2
    )
    print(f"RPN Score: {risk_result['rpn']}")
    print(f"Recommended Plan: {risk_result['decision']}")
    
    # --- TASK 2: Sequential Co-Pilot ---
    print("\n--- [2] SEQUENTIAL ANALYSIS CO-PILOT (Monte Carlo) ---")
    copilot = SequentialCopilot(simulations=10000)
    
    # Scenario: We have completed 8 injections (e.g., 4 levels x 2 replicates).
    # Target concentration is 100 mg/mL. We tested 80, 90, 100, 110.
    # We are missing the 120% level and some replicates to hit 15.
    
    # Almost perfect linear data (R^2 currently ~0.9998)
    current_x = [80.0, 80.0, 90.0, 90.0, 100.0, 100.0, 110.0, 110.0]
    
    # Create near-perfect y values (y = 1.02 * x + 0.5) with tiny variance
    true_slope = 1.02
    true_intercept = 0.5
    current_y = [
        true_slope * x + true_intercept + np.random.normal(0, 0.2) 
        for x in current_x
    ]
    
    print(f"Current Injections Completed: {len(current_x)}")
    print("Running 10,000 Monte Carlo Simulations...")
    
    mc_result = copilot.evaluate_early_stopping(
        current_x=current_x,
        current_y=current_y,
        total_target_points=15
    )
    
    print(f"Decision: {mc_result['decision']}")
    print(f"Probability (R^2 >= 0.999): {mc_result['probability'] * 100:.2f}%")
    
    if mc_result['decision'] == "ARRÊT POSITIF":
        print(f"Injections Saved: {mc_result['saved_injections']} injections")
    
    print("\nSimulating a noisy scenario (CONTINUER expected)...")
    noisy_y = [
        true_slope * x + true_intercept + np.random.normal(0, 5.0) 
        for x in current_x
    ]
    mc_result_noisy = copilot.evaluate_early_stopping(current_x, noisy_y, 15)
    print(f"Decision: {mc_result_noisy['decision']}")
    print(f"Probability (R^2 >= 0.999): {mc_result_noisy['probability'] * 100:.2f}%")
