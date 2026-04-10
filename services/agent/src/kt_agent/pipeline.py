"""Core trading pipeline: fetch data -> predict -> generate signals -> execute."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from kt_alpaca.client import AlpacaClient
from kt_alpaca.data import MarketDataFetcher
from kt_alpaca.models import Instrument
from kt_alpaca.universe import UniverseManager
from kt_kronos.predictor import KronosPredictionService
from kt_shared.config import AgentSettings
from kt_shared.constants import MARKET_CLOSE_HOUR, MARKET_OPEN_HOUR, MARKET_TZ
from kt_shared.models import AssetClass, OrderType, Position, Timeframe, TradeRequest
from kt_signal.engine import SignalEngine

from .execution_client import ExecutionClient

_logger = structlog.get_logger()


class TradingPipeline:
    """Orchestrates the full trading cycle."""

    def __init__(
        self,
        settings: AgentSettings,
        data_fetcher: MarketDataFetcher,
        kronos_service: KronosPredictionService,
        signal_engine: SignalEngine,
        execution_client: ExecutionClient,
        universe_manager: UniverseManager,
    ) -> None:
        self._settings = settings
        self._data = data_fetcher
        self._kronos = kronos_service
        self._signals = signal_engine
        self._exec = execution_client
        self._universe = universe_manager
        self._instruments: list[Instrument] = []

    async def refresh_universe(self) -> None:
        """Refresh the tradable universe (run daily at 08:00 ET)."""
        self._instruments = await self._universe.get_full_universe()
        _logger.info("universe_refreshed", count=len(self._instruments))

    async def run_daily_cycle(self) -> dict:
        """Run the daily trading cycle (09:35 ET).

        1. Ensure universe is loaded
        2. Fetch 512 daily bars for each symbol
        3. Run Kronos batch prediction (5-day horizon, 20 samples)
        4. Generate signals
        5. Execute trades
        """
        _logger.info("daily_cycle_started")

        if not self._instruments:
            await self.refresh_universe()

        symbols = [i.symbol for i in self._instruments]
        asset_map = {i.symbol: i.asset_class for i in self._instruments}

        # Fetch historical data
        data = await self._data.get_batch_ohlcv(symbols, Timeframe.DAILY)
        if not data:
            _logger.warning("daily_cycle_no_data")
            return {"signals": 0, "trades": 0}

        # Run predictions
        predictions = await self._kronos.predict_batch(data, Timeframe.DAILY)

        # Get current prices
        current_prices = await self._data.get_latest_prices(symbols)

        # Get existing positions for exit signal detection
        existing_positions = await self._get_existing_positions()

        # Get portfolio value for sizing
        portfolio_value = await self._get_portfolio_value()

        # Generate signals
        signals = self._signals.generate_signals(
            predictions=predictions,
            current_prices=current_prices,
            portfolio_value=portfolio_value,
            existing_positions=existing_positions,
            asset_classes=asset_map,
        )

        # Execute trades
        trades_submitted = 0
        for signal in signals:
            try:
                request = TradeRequest(
                    symbol=signal.symbol,
                    asset_class=signal.asset_class,
                    side=signal.side,
                    order_type=OrderType.MARKET,
                    quantity=signal.suggested_quantity,
                    notional_value=signal.notional_value,
                    signal_id=signal.signal_id,
                    expected_return=signal.expected_return,
                    confidence=signal.confidence,
                    timeframe=signal.timeframe,
                )
                response = await self._exec.submit_trade(request)
                if response.status == "accepted":
                    trades_submitted += 1
                else:
                    _logger.info(
                        "trade_rejected",
                        symbol=signal.symbol,
                        reason=response.rejection_reason,
                    )
            except Exception as exc:
                _logger.error("trade_submission_failed", symbol=signal.symbol, error=str(exc))

        result = {
            "cycle": "daily",
            "symbols_scanned": len(data),
            "predictions": len(predictions),
            "signals": len(signals),
            "trades": trades_submitted,
        }
        _logger.info("daily_cycle_complete", **result)
        return result

    async def run_intraday_cycle(self) -> dict:
        """Run the intraday cycle (every 1hr during market hours)."""
        # Skip outside market hours for stocks/ETFs
        now = datetime.now(MARKET_TZ)
        if now.hour < MARKET_OPEN_HOUR or now.hour >= MARKET_CLOSE_HOUR:
            _logger.debug("intraday_skip_outside_hours")
            return {"skipped": True}

        _logger.info("intraday_cycle_started")

        # Only use stock/ETF symbols for intraday
        symbols = [
            i.symbol for i in self._instruments if i.asset_class != AssetClass.CRYPTO
        ]
        if not symbols:
            return {"signals": 0, "trades": 0}

        asset_map = {i.symbol: i.asset_class for i in self._instruments}

        data = await self._data.get_batch_ohlcv(symbols, Timeframe.HOURLY)
        if not data:
            return {"signals": 0, "trades": 0}

        predictions = await self._kronos.predict_batch(data, Timeframe.HOURLY)
        current_prices = await self._data.get_latest_prices(symbols)
        existing_positions = await self._get_existing_positions()
        portfolio_value = await self._get_portfolio_value()

        signals = self._signals.generate_signals(
            predictions=predictions,
            current_prices=current_prices,
            portfolio_value=portfolio_value,
            existing_positions=existing_positions,
            asset_classes=asset_map,
        )

        trades_submitted = 0
        for signal in signals:
            try:
                request = TradeRequest(
                    symbol=signal.symbol,
                    asset_class=signal.asset_class,
                    side=signal.side,
                    order_type=OrderType.MARKET,
                    quantity=signal.suggested_quantity,
                    notional_value=signal.notional_value,
                    signal_id=signal.signal_id,
                    expected_return=signal.expected_return,
                    confidence=signal.confidence,
                    timeframe=signal.timeframe,
                )
                response = await self._exec.submit_trade(request)
                if response.status == "accepted":
                    trades_submitted += 1
            except Exception as exc:
                _logger.error("trade_submission_failed", symbol=signal.symbol, error=str(exc))

        result = {
            "cycle": "intraday",
            "symbols_scanned": len(data),
            "predictions": len(predictions),
            "signals": len(signals),
            "trades": trades_submitted,
        }
        _logger.info("intraday_cycle_complete", **result)
        return result

    async def run_crypto_cycle(self) -> dict:
        """Run the crypto cycle (every 4hr, 24/7)."""
        _logger.info("crypto_cycle_started")

        symbols = [
            i.symbol for i in self._instruments if i.asset_class == AssetClass.CRYPTO
        ]
        if not symbols:
            return {"signals": 0, "trades": 0}

        asset_map = {i.symbol: i.asset_class for i in self._instruments}

        data = await self._data.get_batch_ohlcv(symbols, Timeframe.HOURLY)
        if not data:
            return {"signals": 0, "trades": 0}

        predictions = await self._kronos.predict_batch(data, Timeframe.HOURLY)
        current_prices = await self._data.get_latest_prices(symbols)
        existing_positions = await self._get_existing_positions()
        portfolio_value = await self._get_portfolio_value()

        signals = self._signals.generate_signals(
            predictions=predictions,
            current_prices=current_prices,
            portfolio_value=portfolio_value,
            existing_positions=existing_positions,
            asset_classes=asset_map,
        )

        trades_submitted = 0
        for signal in signals:
            try:
                request = TradeRequest(
                    symbol=signal.symbol,
                    asset_class=signal.asset_class,
                    side=signal.side,
                    order_type=OrderType.MARKET,
                    quantity=signal.suggested_quantity,
                    notional_value=signal.notional_value,
                    signal_id=signal.signal_id,
                    expected_return=signal.expected_return,
                    confidence=signal.confidence,
                    timeframe=signal.timeframe,
                )
                response = await self._exec.submit_trade(request)
                if response.status == "accepted":
                    trades_submitted += 1
            except Exception as exc:
                _logger.error("trade_submission_failed", symbol=signal.symbol, error=str(exc))

        result = {
            "cycle": "crypto",
            "symbols_scanned": len(data),
            "predictions": len(predictions),
            "signals": len(signals),
            "trades": trades_submitted,
        }
        _logger.info("crypto_cycle_complete", **result)
        return result

    async def evaluate_predictions(self) -> None:
        """Compare past predictions to actual prices (run at 16:30 ET)."""
        _logger.info("prediction_evaluation_started")
        # This will be called by the scheduler; the execution service's
        # PredictionTracker handles the actual DB work via its API.
        # For now, log that it ran — full implementation connects to
        # /api/v1/predictions and updates actuals.

    async def _get_existing_positions(self) -> dict[str, Position]:
        """Fetch current positions from execution service."""
        try:
            positions = await self._exec.get_positions()
            return {
                p["symbol"]: Position(
                    symbol=p["symbol"],
                    asset_class=AssetClass(p.get("asset_class", "stock")),
                    side=p["side"],
                    quantity=p["quantity"],
                    avg_entry_price=p["avg_entry_price"],
                    current_price=p.get("current_price"),
                    market_value=p.get("market_value", 0),
                    unrealized_pnl=p.get("unrealized_pnl", 0),
                )
                for p in positions
            }
        except Exception as exc:
            _logger.warning("positions_fetch_failed", error=str(exc))
            return {}

    async def _get_portfolio_value(self) -> float:
        """Get current portfolio value from execution service."""
        try:
            status = await self._exec.get_risk_status()
            return float(status.get("portfolio_value", 10000.0))
        except Exception:
            return 10000.0  # Default for paper trading
