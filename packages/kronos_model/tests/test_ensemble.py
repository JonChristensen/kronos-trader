import pytest

from kt_kronos.ensemble import EnsembleAnalyzer
from kt_shared.models import PredictionResult, Timeframe


def _make_prediction(sample_closes: list[float], **kwargs) -> PredictionResult:
    defaults = dict(
        symbol="TEST",
        timeframe=Timeframe.DAILY,
        pred_len=5,
        sample_count=len(sample_closes),
        mean_close=[sum(sample_closes) / len(sample_closes)] * 5,
        std_close=[1.0] * 5,
        mean_high=[105.0] * 5,
        mean_low=[95.0] * 5,
        sample_closes=sample_closes,
    )
    defaults.update(kwargs)
    return PredictionResult(**defaults)


class TestEnsembleConfidence:
    def test_high_agreement_high_confidence(self):
        # All samples predict very similar close
        conf = EnsembleAnalyzer.ensemble_confidence(std_close=0.3, mean_close=100.0)
        assert conf > 0.9

    def test_low_agreement_low_confidence(self):
        # Samples disagree significantly
        conf = EnsembleAnalyzer.ensemble_confidence(std_close=6.0, mean_close=100.0)
        assert conf == 0.0

    def test_medium_agreement(self):
        conf = EnsembleAnalyzer.ensemble_confidence(std_close=2.0, mean_close=100.0)
        assert 0.0 < conf < 1.0

    def test_zero_mean_returns_zero(self):
        conf = EnsembleAnalyzer.ensemble_confidence(std_close=1.0, mean_close=0.0)
        assert conf == 0.0


class TestExpectedReturn:
    def test_positive_return(self):
        ret = EnsembleAnalyzer.expected_return(100.0, 105.0)
        assert abs(ret - 0.05) < 1e-6

    def test_negative_return(self):
        ret = EnsembleAnalyzer.expected_return(100.0, 97.0)
        assert abs(ret - (-0.03)) < 1e-6

    def test_zero_price(self):
        ret = EnsembleAnalyzer.expected_return(0.0, 100.0)
        assert ret == 0.0


class TestComputeStatistics:
    def test_basic_stats(self):
        prediction = _make_prediction(
            sample_closes=[100.0, 101.0, 102.0, 99.0, 100.5],
            mean_high=[105.0] * 5,
            mean_low=[95.0] * 5,
        )
        stats = EnsembleAnalyzer.compute_statistics(prediction, current_price=100.0)

        assert stats.mean_close == pytest.approx(100.5, rel=1e-2)
        assert stats.std_close > 0
        assert stats.p10_close < stats.p90_close
        assert stats.expected_return > 0  # Mean slightly above current
        assert 0.0 <= stats.confidence <= 1.0

    def test_empty_samples_raises(self):
        prediction = _make_prediction(sample_closes=[100.0])
        prediction.sample_closes = []
        with pytest.raises(ValueError):
            EnsembleAnalyzer.compute_statistics(prediction, current_price=100.0)
