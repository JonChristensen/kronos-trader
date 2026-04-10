"""APScheduler configuration for dual-frequency trading."""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from kt_shared.config import AgentSettings

from .pipeline import TradingPipeline

_logger = structlog.get_logger()


def create_scheduler(
    pipeline: TradingPipeline, settings: AgentSettings
) -> AsyncIOScheduler:
    """Create the trading scheduler with all scheduled jobs."""
    scheduler = AsyncIOScheduler()

    # Parse daily cycle time (HH:MM)
    h, m = settings.daily_cycle_time.split(":")

    # 1. Universe refresh — daily at 08:00 ET
    scheduler.add_job(
        pipeline.refresh_universe,
        "cron",
        hour=8,
        minute=0,
        timezone="US/Eastern",
        id="universe_refresh",
        max_instances=1,
        misfire_grace_time=300,
    )

    # 2. Daily trading cycle — once per day at configured time
    scheduler.add_job(
        pipeline.run_daily_cycle,
        "cron",
        hour=int(h),
        minute=int(m),
        timezone="US/Eastern",
        id="daily_cycle",
        max_instances=1,
        misfire_grace_time=300,
    )

    # 3. Intraday cycle — every N seconds during market hours
    scheduler.add_job(
        pipeline.run_intraday_cycle,
        "interval",
        seconds=settings.intraday_interval_seconds,
        id="intraday_cycle",
        max_instances=1,
    )

    # 4. Crypto cycle — every N seconds, 24/7
    scheduler.add_job(
        pipeline.run_crypto_cycle,
        "interval",
        seconds=settings.crypto_interval_seconds,
        id="crypto_cycle",
        max_instances=1,
    )

    # 5. Prediction evaluation — daily at 16:30 ET
    scheduler.add_job(
        pipeline.evaluate_predictions,
        "cron",
        hour=16,
        minute=30,
        timezone="US/Eastern",
        id="prediction_eval",
        max_instances=1,
    )

    _logger.info(
        "scheduler_configured",
        daily_time=settings.daily_cycle_time,
        intraday_interval=f"{settings.intraday_interval_seconds}s",
        crypto_interval=f"{settings.crypto_interval_seconds}s",
        jobs=len(scheduler.get_jobs()),
    )

    return scheduler
