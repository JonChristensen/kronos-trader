"""Submits validated trades to Alpaca."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from kt_alpaca.client import AlpacaClient
from kt_alpaca.exceptions import AlpacaError
from kt_shared.models import TradeRequest, TradeResponse

from ..db.models import Trade
from .audit_logger import AuditLogger

_logger = structlog.get_logger()


class TradeExecutor:
    def __init__(self, alpaca_client: AlpacaClient, audit_logger: AuditLogger) -> None:
        self._alpaca = alpaca_client
        self._audit = audit_logger

    async def execute(
        self, request: TradeRequest, session: AsyncSession
    ) -> TradeResponse:
        """Execute a trade: record in DB, submit to Alpaca, update status."""
        # 1. Record trade in DB
        trade = Trade(
            request_id=request.request_id,
            signal_id=request.signal_id,
            symbol=request.symbol,
            asset_class=request.asset_class.value,
            side=request.side.value,
            order_type=request.order_type.value,
            quantity=request.quantity,
            notional_value=request.notional_value,
            limit_price=request.limit_price,
            expected_return=request.expected_return,
            confidence=request.confidence,
            timeframe=request.timeframe.value,
            status="submitted",
            submitted_at=datetime.now(timezone.utc),
        )
        session.add(trade)
        await session.flush()

        # 2. Submit to Alpaca
        try:
            result = await self._alpaca.submit_order(
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                limit_price=request.limit_price,
            )

            trade.alpaca_order_id = result["order_id"]
            trade.status = "accepted"
            await session.commit()

            await self._audit.log(
                session,
                "trade_submitted",
                request.request_id,
                {
                    "symbol": request.symbol,
                    "side": request.side.value,
                    "quantity": request.quantity,
                    "alpaca_order_id": result["order_id"],
                },
            )

            return TradeResponse(
                request_id=request.request_id,
                status="accepted",
                order_id=result["order_id"],
            )

        except AlpacaError as exc:
            trade.status = "rejected"
            trade.rejection_reason = str(exc)
            await session.commit()

            await self._audit.log(
                session,
                "trade_rejected",
                request.request_id,
                {"symbol": request.symbol, "error": str(exc)},
            )

            return TradeResponse(
                request_id=request.request_id,
                status="rejected",
                rejection_reason=str(exc),
            )

        except Exception as exc:
            trade.status = "error"
            trade.rejection_reason = str(exc)
            await session.commit()

            _logger.error("trade_execution_error", error=str(exc), symbol=request.symbol)

            return TradeResponse(
                request_id=request.request_id,
                status="error",
                rejection_reason=str(exc),
            )
