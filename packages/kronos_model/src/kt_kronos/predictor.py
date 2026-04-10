from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import structlog

from kt_shared.config import KronosSettings
from kt_shared.models import PredictionResult, Timeframe

if TYPE_CHECKING:
    from .loader import KronosModelManager

_logger = structlog.get_logger()


class KronosPredictionService:
    """Runs Kronos predictions with ensemble aggregation."""

    def __init__(self, model_manager: KronosModelManager, settings: KronosSettings) -> None:
        self._manager = model_manager
        self._settings = settings

    def _pred_len_for(self, timeframe: Timeframe) -> int:
        if timeframe == Timeframe.DAILY:
            return self._settings.daily_pred_len
        return self._settings.intraday_pred_len

    async def predict_single(
        self, df: pd.DataFrame, symbol: str, timeframe: Timeframe
    ) -> PredictionResult:
        """Run ensemble prediction for a single symbol."""
        pred_len = self._pred_len_for(timeframe)
        result = await asyncio.get_event_loop().run_in_executor(
            None, self._predict_sync, df, pred_len
        )
        return self._build_result(result, symbol, timeframe, pred_len)

    async def predict_batch(
        self,
        data: dict[str, pd.DataFrame],
        timeframe: Timeframe,
    ) -> dict[str, PredictionResult]:
        """Run predictions for multiple symbols.

        Processes sequentially to avoid GPU memory issues.
        For true batch prediction (if Kronos supports it), this can
        be optimized to use predict_batch() on the model.
        """
        results: dict[str, PredictionResult] = {}
        pred_len = self._pred_len_for(timeframe)

        for symbol, df in data.items():
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self._predict_sync, df, pred_len
                )
                results[symbol] = self._build_result(result, symbol, timeframe, pred_len)
            except Exception as exc:
                _logger.error("prediction_failed", symbol=symbol, error=str(exc))
                continue

        _logger.info(
            "batch_prediction_complete",
            timeframe=timeframe.value,
            symbols=len(data),
            predicted=len(results),
        )
        return results

    def _predict_sync(self, df: pd.DataFrame, pred_len: int) -> dict:
        """Synchronous prediction — runs in thread pool.

        Returns dict with per-sample predictions for ensemble analysis.
        """
        predictor = self._manager.predictor

        x_timestamp = df["timestamp"]
        # Build future timestamps based on the last timestamp and cadence
        last_ts = pd.Timestamp(x_timestamp.iloc[-1])
        if len(x_timestamp) >= 2:
            freq = pd.Timestamp(x_timestamp.iloc[-1]) - pd.Timestamp(x_timestamp.iloc[-2])
        else:
            freq = pd.Timedelta(hours=1)

        y_timestamp = pd.Series(
            [last_ts + freq * (i + 1) for i in range(pred_len)]
        )

        # Run multiple ensemble samples
        all_samples: list[pd.DataFrame] = []
        for _ in range(self._settings.sample_count):
            pred_df = predictor.predict(
                df=df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=pred_len,
                T=self._settings.temperature,
                top_p=self._settings.top_p,
                sample_count=1,
            )
            all_samples.append(pred_df)

        return {"samples": all_samples, "pred_len": pred_len}

    def _build_result(
        self, raw: dict, symbol: str, timeframe: Timeframe, pred_len: int
    ) -> PredictionResult:
        """Aggregate ensemble samples into a PredictionResult."""
        samples: list[pd.DataFrame] = raw["samples"]

        # Stack close prices across samples: shape (sample_count, pred_len)
        close_matrix = np.array([s["close"].values for s in samples])
        high_matrix = np.array([s["high"].values for s in samples])
        low_matrix = np.array([s["low"].values for s in samples])

        mean_close = close_matrix.mean(axis=0).tolist()
        std_close = close_matrix.std(axis=0).tolist()
        mean_high = high_matrix.mean(axis=0).tolist()
        mean_low = low_matrix.mean(axis=0).tolist()

        # First-step sample closes for ensemble confidence analysis
        sample_closes = close_matrix[:, 0].tolist()

        return PredictionResult(
            symbol=symbol,
            timeframe=timeframe,
            pred_len=pred_len,
            sample_count=len(samples),
            mean_close=mean_close,
            std_close=std_close,
            mean_high=mean_high,
            mean_low=mean_low,
            sample_closes=sample_closes,
        )
