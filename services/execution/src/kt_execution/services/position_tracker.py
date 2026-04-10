"""Sync positions from Alpaca to local database."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kt_alpaca.client import AlpacaClient

from ..db.models import Position

_logger = structlog.get_logger()


class PositionTracker:
    def __init__(self, alpaca_client: AlpacaClient) -> None:
        self._alpaca = alpaca_client

    async def sync_positions(self, session: AsyncSession) -> int:
        """Sync all positions from Alpaca to local DB. Returns count synced."""
        remote_positions = await self._alpaca.get_positions()

        synced = 0
        remote_symbols = set()

        for rp in remote_positions:
            symbol = rp["symbol"]
            remote_symbols.add(symbol)

            result = await session.execute(
                select(Position).where(Position.symbol == symbol)
            )
            local_pos = result.scalar_one_or_none()

            if local_pos is None:
                local_pos = Position(
                    symbol=symbol,
                    asset_class=rp.get("asset_class", "stock"),
                    side=rp["side"],
                    quantity=rp["quantity"],
                    avg_entry_price=rp["avg_entry_price"],
                    current_price=rp["current_price"],
                    market_value=rp["market_value"],
                    unrealized_pnl=rp["unrealized_pnl"],
                )
                session.add(local_pos)
            else:
                local_pos.quantity = rp["quantity"]
                local_pos.current_price = rp["current_price"]
                local_pos.market_value = rp["market_value"]
                local_pos.unrealized_pnl = rp["unrealized_pnl"]

            synced += 1

        # Zero out positions that are no longer on Alpaca
        result = await session.execute(
            select(Position).where(Position.quantity > 0)
        )
        for local_pos in result.scalars():
            if local_pos.symbol not in remote_symbols:
                local_pos.quantity = 0.0
                local_pos.market_value = 0.0
                local_pos.unrealized_pnl = 0.0

        await session.commit()
        _logger.info("positions_synced", count=synced)
        return synced
