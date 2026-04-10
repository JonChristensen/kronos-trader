from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from kt_shared.models import PredictionResult


@dataclass
class EnsembleStats:
    """Statistical summary of ensemble predictions."""

    mean_close: float
    std_close: float
    p10_close: float
    p90_close: float
    expected_return: float
    expected_volatility: float
    confidence: float


class EnsembleAnalyzer:
    """Extract trading signals from ensemble prediction samples."""

    @staticmethod
    def compute_statistics(
        prediction: PredictionResult, current_price: float
    ) -> EnsembleStats:
        """Compute ensemble stats for the first predicted step."""
        if not prediction.sample_closes:
            raise ValueError(f"No sample closes for {prediction.symbol}")

        closes = np.array(prediction.sample_closes)
        mean_close = float(np.mean(closes))
        std_close = float(np.std(closes))
        p10_close = float(np.percentile(closes, 10))
        p90_close = float(np.percentile(closes, 90))

        expected_return = EnsembleAnalyzer.expected_return(current_price, mean_close)
        expected_volatility = EnsembleAnalyzer.expected_volatility(
            prediction.mean_high[0], prediction.mean_low[0], current_price
        )
        confidence = EnsembleAnalyzer.ensemble_confidence(std_close, mean_close)

        return EnsembleStats(
            mean_close=mean_close,
            std_close=std_close,
            p10_close=p10_close,
            p90_close=p90_close,
            expected_return=expected_return,
            expected_volatility=expected_volatility,
            confidence=confidence,
        )

    @staticmethod
    def expected_return(current_price: float, predicted_mean_close: float) -> float:
        """Calculate expected return from current price to predicted mean."""
        if current_price <= 0:
            return 0.0
        return (predicted_mean_close - current_price) / current_price

    @staticmethod
    def expected_volatility(
        predicted_high: float, predicted_low: float, current_price: float
    ) -> float:
        """Calculate expected volatility as predicted range / price."""
        if current_price <= 0:
            return 0.0
        return (predicted_high - predicted_low) / current_price

    @staticmethod
    def ensemble_confidence(std_close: float, mean_close: float) -> float:
        """Compute confidence from ensemble agreement.

        Low coefficient of variation = high confidence.
        CV < 0.005 -> confidence 1.0
        CV > 0.05  -> confidence 0.0
        Linear interpolation between.
        """
        if mean_close <= 0 or math.isnan(std_close):
            return 0.0

        cv = std_close / abs(mean_close)

        # Linear map: CV in [0.005, 0.05] -> confidence in [1.0, 0.0]
        if cv <= 0.005:
            return 1.0
        if cv >= 0.05:
            return 0.0
        return 1.0 - (cv - 0.005) / (0.05 - 0.005)
