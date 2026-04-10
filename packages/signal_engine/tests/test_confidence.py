from kt_shared.models import Timeframe
from kt_signal.confidence import score_confidence


class TestScoreConfidence:
    def test_high_confidence_all_factors_strong(self):
        score = score_confidence(
            ensemble_confidence=0.95,
            expected_return=0.03,
            timeframe=Timeframe.DAILY,
            avg_volume=2_000_000,
            predicted_volatility=0.02,
            historical_volatility=0.02,
        )
        assert score > 0.7

    def test_low_confidence_all_factors_weak(self):
        score = score_confidence(
            ensemble_confidence=0.1,
            expected_return=0.0005,
            timeframe=Timeframe.HOURLY,
            avg_volume=5_000,
            predicted_volatility=0.05,
            historical_volatility=0.01,
        )
        assert score < 0.3

    def test_daily_higher_than_hourly(self):
        base = dict(
            ensemble_confidence=0.5,
            expected_return=0.01,
            avg_volume=500_000,
        )
        daily = score_confidence(timeframe=Timeframe.DAILY, **base)
        hourly = score_confidence(timeframe=Timeframe.HOURLY, **base)
        assert daily > hourly

    def test_bounded_zero_to_one(self):
        score = score_confidence(
            ensemble_confidence=1.5,  # Over 1.0 — should be clamped
            expected_return=0.10,
            timeframe=Timeframe.DAILY,
            avg_volume=10_000_000,
        )
        assert 0.0 <= score <= 1.0

    def test_zero_volume_low_liquidity_factor(self):
        score = score_confidence(
            ensemble_confidence=0.8,
            expected_return=0.02,
            timeframe=Timeframe.DAILY,
            avg_volume=0,
        )
        # Should still produce a score, but lower due to zero liquidity
        assert score > 0.0
