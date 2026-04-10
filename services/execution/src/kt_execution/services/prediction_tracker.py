"""Store and evaluate Kronos predictions for accuracy tracking."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kt_shared.models import PredictionResult

from ..db.models import Prediction

_logger = structlog.get_logger()


class PredictionTracker:
    async def store_prediction(
        self,
        prediction: PredictionResult,
        current_price: float,
        session: AsyncSession,
    ) -> None:
        """Store a Kronos prediction in the database."""
        record = Prediction(
            symbol=prediction.symbol,
            timeframe=prediction.timeframe.value,
            predicted_at=prediction.predicted_at,
            pred_len=prediction.pred_len,
            sample_count=prediction.sample_count,
            predicted_close_mean=prediction.mean_close[0],
            predicted_close_std=prediction.std_close[0],
            predicted_high_mean=prediction.mean_high[0],
            predicted_low_mean=prediction.mean_low[0],
            current_price_at_prediction=current_price,
            raw_predictions={
                "mean_close": prediction.mean_close,
                "std_close": prediction.std_close,
            },
        )
        session.add(record)
        await session.commit()

    async def evaluate_prediction(
        self,
        prediction_id: str,
        actual_price: float,
        session: AsyncSession,
    ) -> None:
        """Fill in the actual outcome for a stored prediction."""
        result = await session.execute(
            select(Prediction).where(Prediction.id == prediction_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return

        record.actual_close = actual_price
        record.prediction_error = (
            (actual_price - record.predicted_close_mean) / record.current_price_at_prediction
            if record.current_price_at_prediction > 0
            else None
        )
        await session.commit()

    async def get_accuracy_stats(
        self, session: AsyncSession, symbol: str | None = None, limit: int = 100
    ) -> dict:
        """Get prediction accuracy statistics."""
        query = select(Prediction).where(Prediction.actual_close.isnot(None))
        if symbol:
            query = query.where(Prediction.symbol == symbol)
        query = query.order_by(Prediction.predicted_at.desc()).limit(limit)

        result = await session.execute(query)
        records = result.scalars().all()

        if not records:
            return {"count": 0, "mean_error": None, "direction_accuracy": None}

        errors = [r.prediction_error for r in records if r.prediction_error is not None]
        direction_correct = sum(
            1
            for r in records
            if r.actual_close is not None
            and (r.predicted_close_mean > r.current_price_at_prediction)
            == (r.actual_close > r.current_price_at_prediction)
        )

        return {
            "count": len(records),
            "mean_error": sum(abs(e) for e in errors) / len(errors) if errors else None,
            "direction_accuracy": direction_correct / len(records) if records else None,
        }
