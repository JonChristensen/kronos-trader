"""Dashboard routes — serves the monitoring UI and JSON data endpoint."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kt_alpaca.client import AlpacaClient

from ..db.models import AuditLog, PortfolioSnapshot, Prediction, SignalRecord, Trade
from ..db.session import get_session
from ..risk.kill_switch import activate_kill_switch, deactivate_kill_switch, get_kill_switch_state
from ..risk.manager import RiskManager
from ..services.position_tracker import PositionTracker
from ..services.prediction_tracker import PredictionTracker

_logger = structlog.get_logger()

dashboard_router = APIRouter()

templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)

# Injected at startup
_session_factory: async_sessionmaker | None = None
_alpaca_client: AlpacaClient | None = None
_risk_manager: RiskManager | None = None
_position_tracker: PositionTracker | None = None
_prediction_tracker: PredictionTracker | None = None


def init_dashboard(
    session_factory: async_sessionmaker,
    alpaca_client: AlpacaClient,
    risk_manager: RiskManager,
    position_tracker: PositionTracker,
    prediction_tracker: PredictionTracker,
) -> None:
    global _session_factory, _alpaca_client, _risk_manager
    global _position_tracker, _prediction_tracker
    _session_factory = session_factory
    _alpaca_client = alpaca_client
    _risk_manager = risk_manager
    _position_tracker = position_tracker
    _prediction_tracker = prediction_tracker


async def _gather_dashboard_data(session: AsyncSession) -> dict:
    """Gather all data needed for the dashboard."""
    assert _alpaca_client is not None
    assert _risk_manager is not None
    assert _prediction_tracker is not None

    # Account data from Alpaca
    try:
        account = await _alpaca_client.get_account()
    except Exception as e:
        _logger.error("account_fetch_failed", error=str(e))
        account = {"cash": 0, "portfolio_value": 0, "equity": 0, "last_equity": 0}

    # Positions from Alpaca
    try:
        positions = await _alpaca_client.get_positions()
    except Exception:
        positions = []

    # Risk status
    risk_status = await _risk_manager.get_risk_status(
        session, portfolio_value=account.get("portfolio_value", 0)
    )

    # Kill switch
    kill_state = await get_kill_switch_state(session)

    # Recent trades
    result = await session.execute(
        select(Trade).order_by(Trade.requested_at.desc()).limit(20)
    )
    trades = result.scalars().all()

    # Recent predictions
    result = await session.execute(
        select(Prediction).order_by(Prediction.predicted_at.desc()).limit(20)
    )
    predictions = result.scalars().all()

    # Recent signals
    result = await session.execute(
        select(SignalRecord).order_by(SignalRecord.created_at.desc()).limit(20)
    )
    signals = result.scalars().all()

    # Portfolio snapshots for P&L chart
    result = await session.execute(
        select(PortfolioSnapshot).order_by(PortfolioSnapshot.timestamp.desc()).limit(500)
    )
    snapshots = list(reversed(result.scalars().all()))

    # Audit log
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20)
    )
    audit_entries = result.scalars().all()

    # Prediction accuracy
    accuracy = await _prediction_tracker.get_accuracy_stats(session)

    total_pnl = float(account.get("equity", 0)) - float(account.get("last_equity", 0))

    return {
        "account": account,
        "positions": positions,
        "risk_status": risk_status.model_dump(),
        "kill_switch": {
            "is_active": kill_state.is_active,
            "activated_at": kill_state.activated_at.isoformat() if kill_state.activated_at else None,
            "activated_reason": kill_state.activated_reason,
        },
        "trades": [
            {
                "symbol": t.symbol,
                "asset_class": t.asset_class,
                "side": t.side,
                "quantity": t.quantity,
                "notional_value": t.notional_value,
                "status": t.status,
                "expected_return": t.expected_return,
                "confidence": t.confidence,
                "alpaca_order_id": t.alpaca_order_id,
                "requested_at": t.requested_at.isoformat() if t.requested_at else None,
            }
            for t in trades
        ],
        "predictions": [
            {
                "symbol": p.symbol,
                "timeframe": p.timeframe,
                "predicted_close_mean": p.predicted_close_mean,
                "predicted_close_std": p.predicted_close_std,
                "current_price": p.current_price_at_prediction,
                "actual_close": p.actual_close,
                "predicted_at": p.predicted_at.isoformat(),
            }
            for p in predictions
        ],
        "signals": [
            {
                "symbol": s.symbol,
                "side": s.side,
                "expected_return": s.expected_return,
                "confidence": s.confidence,
                "net_edge": s.net_edge,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
            }
            for s in signals
        ],
        "pnl_chart": {
            "labels": [s.timestamp.isoformat() for s in snapshots],
            "values": [s.total_pnl for s in snapshots],
            "portfolio_values": [s.total_value for s in snapshots],
        },
        "accuracy": accuracy,
        "total_pnl": total_pnl,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@dashboard_router.get("/", response_class=HTMLResponse)
async def dashboard_page(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    data = await _gather_dashboard_data(session)
    return templates.TemplateResponse("dashboard.html", {"request": request, **data})


@dashboard_router.get("/dashboard/data")
async def dashboard_data(session: AsyncSession = Depends(get_session)) -> dict:
    return await _gather_dashboard_data(session)


@dashboard_router.post("/dashboard/kill-switch")
async def dashboard_kill_switch_toggle(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    form = await request.form()
    action = form.get("action", "")
    reason = form.get("reason", "Dashboard toggle")

    if action == "activate":
        await activate_kill_switch(session, str(reason))
    elif action == "deactivate":
        await deactivate_kill_switch(session)

    data = await _gather_dashboard_data(session)
    return templates.TemplateResponse("dashboard.html", {"request": request, **data})
