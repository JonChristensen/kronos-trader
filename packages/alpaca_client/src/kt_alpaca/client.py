from __future__ import annotations

import structlog
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)

from kt_shared.config import AlpacaSettings
from kt_shared.models import OrderType, Side

from .exceptions import AlpacaInsufficientFunds, AlpacaOrderRejected

_logger = structlog.get_logger()


class AlpacaClient:
    """Thin wrapper around the Alpaca Trading SDK."""

    def __init__(self, settings: AlpacaSettings) -> None:
        self._settings = settings
        self._client = TradingClient(
            api_key=settings.api_key,
            secret_key=settings.secret_key,
            paper=settings.paper,
        )

    @property
    def trading_client(self) -> TradingClient:
        return self._client

    async def get_account(self) -> dict:
        """Retrieve account balance and buying power."""
        account = self._client.get_account()
        return {
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "buying_power": float(account.buying_power),
            "equity": float(account.equity),
            "last_equity": float(account.last_equity),
            "long_market_value": float(account.long_market_value),
            "short_market_value": float(account.short_market_value),
        }

    async def get_positions(self) -> list[dict]:
        """Retrieve all open positions."""
        positions = self._client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "quantity": float(p.qty),
                "side": "buy" if float(p.qty) > 0 else "sell",
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pnl": float(p.unrealized_pl),
                "asset_class": str(p.asset_class),
            }
            for p in positions
        ]

    async def submit_order(
        self,
        symbol: str,
        side: Side,
        order_type: OrderType,
        quantity: float,
        limit_price: float | None = None,
    ) -> dict:
        """Submit a trade order to Alpaca."""
        alpaca_side = OrderSide.BUY if side == Side.BUY else OrderSide.SELL

        try:
            if order_type == OrderType.MARKET:
                request = MarketOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                )
            else:
                if limit_price is None:
                    raise ValueError("limit_price required for LIMIT orders")
                request = LimitOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                    limit_price=limit_price,
                )

            order = self._client.submit_order(request)
            _logger.info(
                "order_submitted",
                symbol=symbol,
                side=side.value,
                order_type=order_type.value,
                quantity=quantity,
                order_id=str(order.id),
            )
            return {
                "order_id": str(order.id),
                "status": str(order.status),
                "symbol": order.symbol,
                "filled_qty": str(order.filled_qty),
                "filled_avg_price": str(order.filled_avg_price) if order.filled_avg_price else None,
            }

        except Exception as exc:
            error_msg = str(exc)
            if "insufficient" in error_msg.lower():
                raise AlpacaInsufficientFunds(error_msg) from exc
            if "rejected" in error_msg.lower():
                raise AlpacaOrderRejected(error_msg) from exc
            raise

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an open order."""
        self._client.cancel_order_by_id(order_id)
        _logger.info("order_cancelled", order_id=order_id)

    async def get_orders(self, status: str = "open") -> list[dict]:
        """Retrieve orders filtered by status."""
        request = GetOrdersRequest(status=status)
        orders = self._client.get_orders(request)
        return [
            {
                "order_id": str(o.id),
                "symbol": o.symbol,
                "side": str(o.side),
                "order_type": str(o.type),
                "qty": str(o.qty),
                "filled_qty": str(o.filled_qty),
                "status": str(o.status),
                "submitted_at": str(o.submitted_at),
            }
            for o in orders
        ]
