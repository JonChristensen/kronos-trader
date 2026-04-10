"""Kronos Trader agent service entry point."""

from __future__ import annotations

import asyncio
import os
import signal

import structlog

from kt_alpaca.client import AlpacaClient
from kt_alpaca.data import MarketDataFetcher
from kt_alpaca.universe import UniverseManager
from kt_kronos.loader import KronosModelManager
from kt_kronos.predictor import KronosPredictionService
from kt_shared.config import AgentSettings, AlpacaSettings, KronosSettings
from kt_shared.logging import setup_logging
from kt_signal.engine import SignalEngine

from .execution_client import ExecutionClient
from .pipeline import TradingPipeline
from .scheduler import create_scheduler

_logger = structlog.get_logger()


async def main() -> None:
    setup_logging(
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        log_format=os.environ.get("LOG_FORMAT", "console"),
    )

    agent_settings = AgentSettings()
    alpaca_settings = AlpacaSettings()
    kronos_settings = KronosSettings()

    agent_settings.log_config()
    alpaca_settings.log_config()
    kronos_settings.log_config()

    # Initialize clients
    alpaca_client = AlpacaClient(alpaca_settings)
    data_fetcher = MarketDataFetcher(alpaca_settings)
    execution_client = ExecutionClient(agent_settings)
    universe_manager = UniverseManager(alpaca_client.trading_client)

    # Load Kronos model (may take time to download from HuggingFace)
    _logger.info("loading_kronos_model")
    kronos_manager = KronosModelManager(kronos_settings)
    await kronos_manager.load()
    kronos_service = KronosPredictionService(kronos_manager, kronos_settings)

    # Initialize signal engine
    signal_engine = SignalEngine(
        edge_threshold=agent_settings.edge_threshold,
        confidence_threshold=agent_settings.confidence_threshold,
        max_trade_dollars=500,  # Will be overridden by execution service risk checks
    )

    # Build pipeline
    pipeline = TradingPipeline(
        settings=agent_settings,
        data_fetcher=data_fetcher,
        kronos_service=kronos_service,
        signal_engine=signal_engine,
        execution_client=execution_client,
        universe_manager=universe_manager,
    )

    # Wait for execution service to be ready
    _logger.info("waiting_for_execution_service")
    for _ in range(30):
        if await execution_client.health_check():
            break
        await asyncio.sleep(2)
    else:
        _logger.error("execution_service_unreachable")
        return

    # Load initial universe
    await pipeline.refresh_universe()

    # Create and start scheduler
    scheduler = create_scheduler(pipeline, agent_settings)
    scheduler.start()

    _logger.info("agent_started", paper=alpaca_settings.paper)

    # Graceful shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()

    _logger.info("agent_shutting_down")
    scheduler.shutdown(wait=False)
    await execution_client.close()
    _logger.info("agent_stopped")


if __name__ == "__main__":
    asyncio.run(main())
