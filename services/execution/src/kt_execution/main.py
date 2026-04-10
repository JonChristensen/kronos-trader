"""Kronos Trader execution service — FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from kt_alpaca.client import AlpacaClient
from kt_shared.config import AlpacaSettings, ExecutionSettings
from kt_shared.logging import setup_logging

from .api.routes import init_routes, router
from .dashboard.routes import init_dashboard, dashboard_router
from .db.models import Base
from .db.session import get_engine, get_session_factory
from .risk.manager import RiskManager
from .services.audit_logger import AuditLogger
from .services.position_tracker import PositionTracker
from .services.prediction_tracker import PredictionTracker
from .services.trade_executor import TradeExecutor

_logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB, clients, and services."""
    setup_logging(
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        log_format=os.environ.get("LOG_FORMAT", "console"),
    )

    exec_settings = ExecutionSettings()
    alpaca_settings = AlpacaSettings()
    exec_settings.log_config()
    alpaca_settings.log_config()

    # Database
    engine = get_engine(exec_settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = get_session_factory(engine)

    # Clients
    alpaca_client = AlpacaClient(alpaca_settings)

    # Services
    audit_logger = AuditLogger()
    risk_manager = RiskManager(exec_settings)
    trade_executor = TradeExecutor(alpaca_client, audit_logger)
    position_tracker = PositionTracker(alpaca_client)
    prediction_tracker = PredictionTracker()

    # Inject into routes
    init_routes(risk_manager, trade_executor, audit_logger)
    init_dashboard(
        session_factory=session_factory,
        alpaca_client=alpaca_client,
        risk_manager=risk_manager,
        position_tracker=position_tracker,
        prediction_tracker=prediction_tracker,
    )

    _logger.info("execution_service_started", paper=alpaca_settings.paper)

    yield

    await engine.dispose()
    _logger.info("execution_service_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Kronos Trader Execution", lifespan=lifespan)
    app.include_router(router)
    app.include_router(dashboard_router)

    # Static files for dashboard
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


app = create_app()

if __name__ == "__main__":
    settings = ExecutionSettings()
    uvicorn.run(
        "kt_execution.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
