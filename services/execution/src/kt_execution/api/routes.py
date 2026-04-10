"""API routes for the execution service."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kt_shared.models import TradeRequest, TradeResponse

from ..db.models import AuditLog, Prediction, SignalRecord, Trade
from ..db.session import get_session
from ..risk.kill_switch import activate_kill_switch, deactivate_kill_switch, get_kill_switch_state
from ..risk.manager import RiskManager
from ..services.audit_logger import AuditLogger
from ..services.trade_executor import TradeExecutor
from .dependencies import verify_auth_token

router = APIRouter(prefix="/api/v1")

# These are injected by main.py at startup
_risk_manager: RiskManager | None = None
_trade_executor: TradeExecutor | None = None
_audit_logger: AuditLogger | None = None


def init_routes(
    risk_manager: RiskManager,
    trade_executor: TradeExecutor,
    audit_logger: AuditLogger,
) -> None:
    global _risk_manager, _trade_executor, _audit_logger
    _risk_manager = risk_manager
    _trade_executor = trade_executor
    _audit_logger = audit_logger


@router.post("/trade", response_model=TradeResponse)
async def submit_trade(
    request: TradeRequest,
    _: None = Depends(verify_auth_token),
    session: AsyncSession = Depends(get_session),
) -> TradeResponse:
    """Submit a trade request — risk checks then execution."""
    assert _risk_manager is not None
    assert _trade_executor is not None

    decision = await _risk_manager.check_trade(request, session)
    if not decision.allowed:
        assert _audit_logger is not None
        await _audit_logger.log(
            session,
            "trade_risk_rejected",
            request.request_id,
            {"symbol": request.symbol, "reason": decision.reason},
        )
        return TradeResponse(
            request_id=request.request_id,
            status="rejected",
            rejection_reason=decision.reason,
        )

    return await _trade_executor.execute(request, session)


@router.get("/positions")
async def get_positions(session: AsyncSession = Depends(get_session)) -> list[dict]:
    from ..db.models import Position

    result = await session.execute(
        select(Position).where(Position.quantity > 0)
    )
    positions = result.scalars().all()
    return [
        {
            "symbol": p.symbol,
            "asset_class": p.asset_class,
            "side": p.side,
            "quantity": p.quantity,
            "avg_entry_price": p.avg_entry_price,
            "current_price": p.current_price,
            "market_value": p.market_value,
            "unrealized_pnl": p.unrealized_pnl,
        }
        for p in positions
    ]


@router.get("/trades")
async def get_trades(
    limit: int = 50, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    result = await session.execute(
        select(Trade).order_by(Trade.requested_at.desc()).limit(limit)
    )
    trades = result.scalars().all()
    return [
        {
            "request_id": str(t.request_id),
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
    ]


@router.get("/risk-status")
async def get_risk_status(session: AsyncSession = Depends(get_session)) -> dict:
    assert _risk_manager is not None
    status = await _risk_manager.get_risk_status(session)
    return status.model_dump()


@router.post("/kill-switch/activate")
async def kill_switch_activate(
    reason: str = "Manual activation",
    _: None = Depends(verify_auth_token),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await activate_kill_switch(session, reason)
    return {"status": "activated", "reason": reason}


@router.post("/kill-switch/deactivate")
async def kill_switch_deactivate(
    _: None = Depends(verify_auth_token),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await deactivate_kill_switch(session)
    return {"status": "deactivated"}


@router.get("/kill-switch")
async def get_kill_switch(session: AsyncSession = Depends(get_session)) -> dict:
    state = await get_kill_switch_state(session)
    return {
        "is_active": state.is_active,
        "activated_at": state.activated_at.isoformat() if state.activated_at else None,
        "activated_reason": state.activated_reason,
    }


@router.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "service": "kt-execution",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/predictions")
async def get_predictions(
    limit: int = 20, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    result = await session.execute(
        select(Prediction).order_by(Prediction.predicted_at.desc()).limit(limit)
    )
    preds = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "symbol": p.symbol,
            "timeframe": p.timeframe,
            "predicted_at": p.predicted_at.isoformat(),
            "predicted_close_mean": p.predicted_close_mean,
            "predicted_close_std": p.predicted_close_std,
            "current_price": p.current_price_at_prediction,
            "actual_close": p.actual_close,
            "prediction_error": p.prediction_error,
        }
        for p in preds
    ]


@router.get("/signals")
async def get_signals(
    limit: int = 20, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    result = await session.execute(
        select(SignalRecord).order_by(SignalRecord.created_at.desc()).limit(limit)
    )
    signals = result.scalars().all()
    return [
        {
            "signal_id": str(s.signal_id),
            "symbol": s.symbol,
            "asset_class": s.asset_class,
            "side": s.side,
            "timeframe": s.timeframe,
            "expected_return": s.expected_return,
            "confidence": s.confidence,
            "net_edge": s.net_edge,
            "predicted_close": s.predicted_close,
            "current_price": s.current_price,
            "actual_return": s.actual_return,
            "status": s.status,
            "created_at": s.created_at.isoformat(),
        }
        for s in signals
    ]


@router.get("/audit-log")
async def get_audit_log(
    limit: int = 50, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    entries = result.scalars().all()
    return [
        {
            "event_type": e.event_type,
            "request_id": str(e.request_id) if e.request_id else None,
            "details": e.details,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
