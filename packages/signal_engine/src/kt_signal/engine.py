from __future__ import annotations

import structlog

from kt_shared.models import (
    AssetClass,
    Position,
    PredictionResult,
    Signal,
    Timeframe,
)

from .confidence import score_confidence
from .edge import calculate_edge
from .sizing import calculate_position_size

_logger = structlog.get_logger()


class SignalEngine:
    """Generate trading signals from Kronos predictions."""

    def __init__(
        self,
        edge_threshold: float,
        confidence_threshold: float,
        max_trade_dollars: float,
        max_concentration_pct: float = 0.25,
    ) -> None:
        self._edge_threshold = edge_threshold
        self._confidence_threshold = confidence_threshold
        self._max_trade_dollars = max_trade_dollars
        self._max_concentration_pct = max_concentration_pct

    def generate_signals(
        self,
        predictions: dict[str, PredictionResult],
        current_prices: dict[str, float],
        portfolio_value: float,
        existing_positions: dict[str, Position] | None = None,
        asset_classes: dict[str, AssetClass] | None = None,
    ) -> list[Signal]:
        """Generate signals for all predicted instruments.

        Handles both entry signals (new positions) and exit signals
        (when prediction direction flips on an existing position).
        """
        existing_positions = existing_positions or {}
        asset_classes = asset_classes or {}
        signals: list[Signal] = []

        for symbol, prediction in predictions.items():
            current_price = current_prices.get(symbol)
            if current_price is None or current_price <= 0:
                continue

            asset_class = asset_classes.get(symbol, AssetClass.STOCK)

            signal = self._evaluate_symbol(
                symbol=symbol,
                prediction=prediction,
                current_price=current_price,
                portfolio_value=portfolio_value,
                asset_class=asset_class,
                existing_position=existing_positions.get(symbol),
            )

            if signal is not None:
                signals.append(signal)

        # Sort by net edge (strongest signals first)
        signals.sort(key=lambda s: s.net_edge, reverse=True)

        _logger.info(
            "signals_generated",
            predictions=len(predictions),
            signals=len(signals),
            timeframe=next(iter(predictions.values())).timeframe.value if predictions else "n/a",
        )
        return signals

    def _evaluate_symbol(
        self,
        symbol: str,
        prediction: PredictionResult,
        current_price: float,
        portfolio_value: float,
        asset_class: AssetClass,
        existing_position: Position | None,
    ) -> Signal | None:
        """Evaluate a single symbol for a trading signal."""
        if not prediction.mean_close or not prediction.sample_closes:
            return None

        predicted_close = prediction.mean_close[0]
        ensemble_std = prediction.std_close[0]
        predicted_high = prediction.mean_high[0]
        predicted_low = prediction.mean_low[0]

        # Calculate ensemble confidence
        from kt_kronos.ensemble import EnsembleAnalyzer

        ensemble_conf = EnsembleAnalyzer.ensemble_confidence(ensemble_std, predicted_close)

        # Calculate edge
        edge_result = calculate_edge(
            current_price=current_price,
            predicted_close=predicted_close,
            ensemble_std=ensemble_std,
            predicted_high=predicted_high,
            predicted_low=predicted_low,
            asset_class=asset_class,
            confidence=ensemble_conf,
        )

        # Score overall confidence
        confidence = score_confidence(
            ensemble_confidence=ensemble_conf,
            expected_return=edge_result.expected_return,
            timeframe=prediction.timeframe,
        )

        # Filter: must meet edge and confidence thresholds
        if edge_result.net_edge < self._edge_threshold:
            return None
        if confidence < self._confidence_threshold:
            return None

        # If we have an existing position in the opposite direction, generate exit signal
        side = edge_result.side
        if existing_position is not None and existing_position.side != side:
            _logger.info(
                "exit_signal",
                symbol=symbol,
                old_side=existing_position.side.value,
                new_side=side.value,
            )

        # Calculate position size
        size = calculate_position_size(
            confidence=confidence,
            net_edge=edge_result.net_edge,
            current_price=current_price,
            portfolio_value=portfolio_value,
            max_trade_dollars=self._max_trade_dollars,
            max_concentration_pct=self._max_concentration_pct,
        )

        if size.shares <= 0:
            return None

        return Signal(
            symbol=symbol,
            asset_class=asset_class,
            side=side,
            timeframe=prediction.timeframe,
            current_price=current_price,
            predicted_close=predicted_close,
            expected_return=edge_result.expected_return,
            expected_volatility=edge_result.expected_volatility,
            confidence=confidence,
            ensemble_std=ensemble_std,
            net_edge=edge_result.net_edge,
            suggested_quantity=size.shares,
            notional_value=size.notional_value,
        )
