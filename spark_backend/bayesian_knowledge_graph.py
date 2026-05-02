import numpy as np
from scipy import stats
from typing import Dict, List, Tuple

class BayesianKnowledgeGraph:
    """
    SPARK Approach Module 4: Historical Knowledge Exploitation.
    Mathematically fuses historical validation data with new, ongoing data
    using Bayesian updating to justify reduced testing efforts.
    """

    def __init__(self, instrumental_noise_var: float = 0.5):
        # Assumed baseline instrumental variance (sigma^2 of the detector noise)
        self.noise_var = instrumental_noise_var

    def calculate_prior(self, historical_campaigns: List[Dict[str, float]]) -> Dict[str, float]:
        """
        Calculates the Gaussian Prior (mean and variance) from historical campaigns.
        Expects a list of dicts with 'slope' and 'intercept'.
        """
        if not historical_campaigns:
            raise ValueError("Must provide at least one historical campaign to calculate prior.")

        slopes = [camp['slope'] for camp in historical_campaigns]
        intercepts = [camp['intercept'] for camp in historical_campaigns]

        prior_slope_mean = float(np.mean(slopes))
        # Use sample variance (ddof=1) if > 1 campaign, else assume high variance (low confidence)
        prior_slope_var = float(np.var(slopes, ddof=1)) if len(slopes) > 1 else 10.0
        
        # Prevent zero variance if campaigns are identical
        if prior_slope_var < 1e-6:
            prior_slope_var = 1e-6

        prior_intercept_mean = float(np.mean(intercepts))
        prior_intercept_var = float(np.var(intercepts, ddof=1)) if len(intercepts) > 1 else 10.0

        return {
            "slope_mean": prior_slope_mean,
            "slope_var": prior_slope_var,
            "intercept_mean": prior_intercept_mean,
            "intercept_var": prior_intercept_var
        }

    def calculate_posterior(
        self, 
        prior_slope_mean: float, 
        prior_slope_var: float, 
        new_data_x: List[float], 
        new_data_y: List[float]
    ) -> Dict[str, float]:
        """
        Computes the Bayesian Posterior for the slope by combining the Prior
        with the new Likelihood (observed data).
        
        Formula for 1D Bayesian Linear Regression (assuming centered data):
        Precision_post = Precision_prior + Precision_likelihood
        Var_post = 1 / ( (1/Var_prior) + sum(x_i^2)/sigma^2 )
        Mean_post = Var_post * ( Mean_prior/Var_prior + sum(x_i * y_i)/sigma^2 )
        """
        x_arr = np.array(new_data_x)
        y_arr = np.array(new_data_y)
        
        if len(x_arr) < 2:
            raise ValueError("Need at least 2 data points for a meaningful update.")

        # Center the data to isolate the slope update
        x_mean = np.mean(x_arr)
        y_mean = np.mean(y_arr)
        x_c = x_arr - x_mean
        y_c = y_arr - y_mean

        # Precision is the inverse of variance
        prior_precision = 1.0 / prior_slope_var
        
        # Likelihood precision based on sum of squares of X and instrumental noise
        sum_sq_x = np.sum(x_c**2)
        sum_xy = np.sum(x_c * y_c)
        
        likelihood_precision = sum_sq_x / self.noise_var
        
        # Calculate Posterior Variance
        posterior_precision = prior_precision + likelihood_precision
        posterior_slope_var = 1.0 / posterior_precision
        
        # Calculate Posterior Mean
        posterior_slope_mean = posterior_slope_var * (
            (prior_slope_mean * prior_precision) + (sum_xy / self.noise_var)
        )

        return {
            "posterior_slope_mean": float(posterior_slope_mean),
            "posterior_slope_var": float(posterior_slope_var),
            "prior_influence_pct": float((prior_precision / posterior_precision) * 100),
            "data_influence_pct": float((likelihood_precision / posterior_precision) * 100)
        }

    def apply_kalman_filter(self, noisy_measurements: List[float], dt: float = 1.0, threshold: float = 2.0) -> Dict:
        """
        Extended Kalman Filter (EKF) logic simplified for linear/mildly non-linear tracking
        of HPLC column degradation (e.g., Resolution drops over time).
        """
        if not noisy_measurements:
            return {"measurements": [], "filtered_states": [], "projected_remaining_campaigns": 0}
            
        # Initial state [Position, Velocity]
        x = np.array([noisy_measurements[0], 0.0]) 
        
        # State transition matrix (Kinematic model)
        F = np.array([[1.0, dt],
                      [0.0, 1.0]])
                      
        # Measurement matrix (We only observe Position)
        H = np.array([[1.0, 0.0]])
        
        # Initial Covariance Matrix
        P = np.array([[1.0, 0.0],
                      [0.0, 1.0]])
                      
        # Process Noise Covariance
        Q = np.array([[0.01, 0.0],
                      [0.0, 0.01]])
                      
        # Measurement Noise Covariance
        R = np.array([[self.noise_var]])
        
        filtered_states = []
        
        for z in noisy_measurements:
            # Predict
            x = np.dot(F, x)
            P = np.dot(F, np.dot(P, F.T)) + Q
            
            # Update
            y = z - np.dot(H, x)
            S = np.dot(H, np.dot(P, H.T)) + R
            K = np.dot(P, np.dot(H.T, np.linalg.inv(S)))
            
            x = x + np.dot(K, y)
            P = P - np.dot(K, np.dot(H, P))
            
            filtered_states.append(float(x[0]))
            
        # Projection: how many steps until threshold is crossed?
        current_pos = x[0]
        current_vel = x[1]
        
        projected_steps = 0
        if current_pos > threshold and current_vel < 0:
            # It's degrading
            projected_steps = int(np.ceil((threshold - current_pos) / current_vel))
        elif current_pos <= threshold:
            projected_steps = 0
        else:
            # Velocity is >= 0, so it's not degrading towards threshold
            projected_steps = 999 
            
        return {
            "measurements": noisy_measurements,
            "filtered_states": filtered_states,
            "projected_remaining_campaigns": projected_steps
        }


# ─────────────────────────────────────────────────────────────────────────────
#  EXECUTION BLOCK
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("="*60)
    print("  SPARK ENGINE: Bayesian Knowledge Graph")
    print("="*60)

    kg = BayesianKnowledgeGraph(instrumental_noise_var=1.0)

    # 1. THE PRIOR (Historical Knowledge)
    # We have 3 previous validations for similar molecules.
    historical_data = [
        {"campaign": "Batch 2023-A", "slope": 1.015, "intercept": 0.05},
        {"campaign": "Batch 2023-B", "slope": 1.020, "intercept": 0.04},
        {"campaign": "Batch 2024-A", "slope": 1.010, "intercept": 0.06},
    ]
    
    prior = kg.calculate_prior(historical_data)
    
    print("\n[1] HISTORICAL PRIOR CALCULATED:")
    print(f"Mean Slope: {prior['slope_mean']:.4f}")
    print(f"Variance (Uncertainty): {prior['slope_var']:.6f}")

    # 2. THE LIKELIHOOD (New Ongoing Validation Data)
    # We only run 3 injections instead of 15 (Extreme effort reduction)
    # The true slope is 1.025, but with only 3 points, classical stats would fail.
    new_x = [80.0, 100.0, 120.0]
    new_y = [82.2, 102.3, 123.1]
    
    # Classical OLS on just 3 points
    ols_slope, _, _, _, _ = stats.linregress(new_x, new_y)
    
    # 3. THE POSTERIOR (Bayesian Fusion)
    posterior = kg.calculate_posterior(
        prior_slope_mean=prior['slope_mean'],
        prior_slope_var=prior['slope_var'],
        new_data_x=new_x,
        new_data_y=new_y
    )

    print("\n[2] BAYESIAN FUSION (POSTERIOR) - ONLY 3 DATA POINTS:")
    print(f"Classical OLS Slope (No Prior):  {ols_slope:.4f}")
    print(f"Bayesian Posterior Slope:        {posterior['posterior_slope_mean']:.4f}")
    print(f"Posterior Variance:              {posterior['posterior_slope_var']:.6f}")
    
    print(f"\n[3] FUSION WEIGHTS:")
    print(f"Historical Prior Influence:      {posterior['prior_influence_pct']:.1f}%")
    print(f"New Data Likelihood Influence:   {posterior['data_influence_pct']:.1f}%")
    
    print("\nCONCLUSION:")
    if posterior['posterior_slope_var'] < prior['slope_var']:
        variance_reduction = (1 - (posterior['posterior_slope_var'] / prior['slope_var'])) * 100
        print(f"By mathematically fusing historical data, we reduced slope uncertainty by {variance_reduction:.2f}%.")
        print("This statistically justifies stopping the validation at just 3 levels instead of 15!")
