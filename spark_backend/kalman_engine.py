from __future__ import annotations

from typing import List, Optional, TypedDict


class KalmanTelemetryPoint(TypedDict):
    campaign: int
    raw: float
    filtered: float


DEFAULT_RAW_HISTORY: List[float] = [
    3.2,
    3.0,
    3.1,
    2.8,
    2.9,
    2.6,
    2.5,
    2.4,
    2.5,
    2.2,
]


def generate_kalman_telemetry(
    raw_history: Optional[List[float]] = None,
    *,
    Q: float = 0.01,
    R: float = 0.1,
    P0: float = 1.0,
    decimals: int = 2,
) -> List[KalmanTelemetryPoint]:
    """Generate 1D Kalman-smoothed telemetry for the frontend.

    Output schema matches `ValidationReport.tsx` expectations:
    `[{campaign: int, raw: number, filtered: number}, ...]`

    Args:
        raw_history: Noisy historical measurements (e.g., column resolution Rs).
            If omitted, uses a deterministic demo series.
        Q: Process noise (higher -> trust model less, follow measurements more).
        R: Measurement noise (higher -> trust measurements less, smoother output).
        P0: Initial estimate covariance.
        decimals: Rounding precision for frontend display.
    """

    history = DEFAULT_RAW_HISTORY if raw_history is None else raw_history
    if not history:
        return []

    if Q <= 0 or R <= 0 or P0 <= 0:
        raise ValueError("Q, R, and P0 must be > 0")

    # Initial state estimate and uncertainty
    x = float(history[0])
    P = float(P0)

    telemetry_data: List[KalmanTelemetryPoint] = []
    for i, z in enumerate(history):
        z_f = float(z)

        # Prediction step (random walk)
        x_pred = x
        P_pred = P + Q

        # Update step
        K = P_pred / (P_pred + R)
        x = x_pred + K * (z_f - x_pred)
        P = (1.0 - K) * P_pred

        telemetry_data.append(
            {
                "campaign": int(i),
                "raw": round(z_f, decimals),
                "filtered": round(float(x), decimals),
            }
        )

    return telemetry_data
