from __future__ import annotations

from kt_shared.models import Timeframe


def score_confidence(
    ensemble_confidence: float,
    expected_return: float,
    timeframe: Timeframe,
    avg_volume: float = 0.0,
    predicted_volatility: float = 0.0,
    historical_volatility: float = 0.0,
) -> float:
    """Score overall signal confidence from multiple factors.

    Returns a value in [0.0, 1.0].

    Weights:
        Ensemble agreement:  0.35
        Edge strength:       0.25
        Timeframe:           0.15
        Liquidity:           0.15
        Volatility ratio:    0.10
    """
    # Factor 1: Ensemble agreement (already 0-1 from EnsembleAnalyzer)
    f_ensemble = min(max(ensemble_confidence, 0.0), 1.0)

    # Factor 2: Edge strength — larger |expected_return| = more confidence
    # Map: |ret| >= 2% -> 1.0, |ret| <= 0.1% -> 0.0
    abs_ret = abs(expected_return)
    if abs_ret >= 0.02:
        f_edge = 1.0
    elif abs_ret <= 0.001:
        f_edge = 0.0
    else:
        f_edge = (abs_ret - 0.001) / (0.02 - 0.001)

    # Factor 3: Timeframe — daily signals slightly more reliable than intraday
    f_timeframe = 0.7 if timeframe == Timeframe.DAILY else 0.5

    # Factor 4: Liquidity — higher average volume = more confidence
    # Map: vol >= 1M -> 1.0, vol <= 10K -> 0.0
    if avg_volume >= 1_000_000:
        f_liquidity = 1.0
    elif avg_volume <= 10_000:
        f_liquidity = 0.0
    else:
        f_liquidity = (avg_volume - 10_000) / (1_000_000 - 10_000)

    # Factor 5: Volatility ratio — predicted vol close to historical = stable signal
    if historical_volatility > 0 and predicted_volatility > 0:
        ratio = predicted_volatility / historical_volatility
        # Ratio near 1.0 is best; deviations reduce confidence
        f_vol = max(0.0, 1.0 - abs(ratio - 1.0))
    else:
        f_vol = 0.5  # Neutral if we lack data

    # Weighted average
    confidence = (
        0.35 * f_ensemble
        + 0.25 * f_edge
        + 0.15 * f_timeframe
        + 0.15 * f_liquidity
        + 0.10 * f_vol
    )

    return min(max(confidence, 0.0), 1.0)
