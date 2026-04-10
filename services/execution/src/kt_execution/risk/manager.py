"""Risk manager with position, loss, concentration, and crypto allocation limits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kt_shared.config import ExecutionSettings
from kt_shared.models import RiskStatus, TradeRequest

from ..db.models import DailyPnL, KillSwitchState, Position, Trade

_logger = structlog.get_logger()


@dataclass
class RiskDecision:
    allowed: bool
    reason: str | None = None


class RiskManager:
    """Enforces risk limits on all trade requests."""

    def __init__(self, settings: ExecutionSettings) -> None:
        self._settings = settings
        _logger.info(
            "risk_manager_initialized",
            max_position=f"${settings.max_position_dollars}",
            max_daily_loss=f"${settings.max_daily_loss_dollars}",
            max_trade=f"${settings.max_trade_dollars}",
            max_trades_per_hour=settings.max_trades_per_hour,
            max_concentration=f"{settings.max_concentration_pct:.0%}",
            max_crypto=f"{settings.max_crypto_pct:.0%}",
        )

    async def check_trade(
        self, request: TradeRequest, session: AsyncSession
    ) -> RiskDecision:
        """Run all risk checks on a trade request."""
        # 1. Kill switch
        kill_state = await self._get_kill_switch_state(session)
        if kill_state and kill_state.is_active:
            return RiskDecision(
                allowed=False,
                reason=f"Kill switch is active: {kill_state.activated_reason}",
            )

        # 2. Single trade size
        if request.notional_value > self._settings.max_trade_dollars:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Trade size ${request.notional_value:.2f} exceeds "
                    f"max ${self._settings.max_trade_dollars}"
                ),
            )

        # 3. Total position exposure
        current_exposure = await self._get_total_exposure(session)
        new_exposure = current_exposure + request.notional_value
        if new_exposure > self._settings.max_position_dollars:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Total exposure would be ${new_exposure:.2f}, "
                    f"exceeds max ${self._settings.max_position_dollars} "
                    f"(current: ${current_exposure:.2f})"
                ),
            )

        # 4. Daily loss limit
        daily_loss = await self._get_daily_loss(session)
        if daily_loss >= self._settings.max_daily_loss_dollars:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Daily loss ${daily_loss:.2f} reached "
                    f"max ${self._settings.max_daily_loss_dollars}"
                ),
            )

        # 5. Trades per hour rate limit
        recent_trades = await self._get_trades_last_hour(session)
        if recent_trades >= self._settings.max_trades_per_hour:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"Rate limit: {recent_trades} trades in last hour, "
                    f"max is {self._settings.max_trades_per_hour}"
                ),
            )

        # 6. Concentration check
        symbol_exposure = await self._get_symbol_exposure(session, request.symbol)
        total_portfolio = max(current_exposure, 1.0)  # Avoid division by zero
        new_symbol_exposure = symbol_exposure + request.notional_value
        concentration = new_symbol_exposure / (total_portfolio + request.notional_value)
        if concentration > self._settings.max_concentration_pct:
            return RiskDecision(
                allowed=False,
                reason=(
                    f"{request.symbol} concentration {concentration:.1%} would exceed "
                    f"max {self._settings.max_concentration_pct:.0%}"
                ),
            )

        # 7. Crypto allocation check
        if request.asset_class.value == "crypto":
            crypto_exposure = await self._get_crypto_exposure(session)
            new_crypto = crypto_exposure + request.notional_value
            crypto_pct = new_crypto / (total_portfolio + request.notional_value)
            if crypto_pct > self._settings.max_crypto_pct:
                return RiskDecision(
                    allowed=False,
                    reason=(
                        f"Crypto allocation {crypto_pct:.1%} would exceed "
                        f"max {self._settings.max_crypto_pct:.0%}"
                    ),
                )

        return RiskDecision(allowed=True)

    async def get_risk_status(
        self, session: AsyncSession, portfolio_value: float = 0.0
    ) -> RiskStatus:
        """Get current risk utilization."""
        kill_state = await self._get_kill_switch_state(session)
        current_exposure = await self._get_total_exposure(session)
        daily_loss = await self._get_daily_loss(session)
        crypto_exposure = await self._get_crypto_exposure(session)
        trades_hour = await self._get_trades_last_hour(session)

        total = max(current_exposure, 1.0)
        crypto_pct = crypto_exposure / total if total > 0 else 0.0

        # Find worst concentration
        worst_symbol, worst_pct = await self._get_worst_concentration(session)

        return RiskStatus(
            kill_switch_active=kill_state.is_active if kill_state else False,
            portfolio_value=portfolio_value,
            max_position_dollars=self._settings.max_position_dollars,
            current_position_dollars=current_exposure,
            position_utilization=(
                current_exposure / self._settings.max_position_dollars
                if self._settings.max_position_dollars > 0
                else 0.0
            ),
            max_daily_loss_dollars=self._settings.max_daily_loss_dollars,
            current_daily_loss_dollars=daily_loss,
            loss_utilization=(
                daily_loss / self._settings.max_daily_loss_dollars
                if self._settings.max_daily_loss_dollars > 0
                else 0.0
            ),
            crypto_allocation_pct=crypto_pct,
            max_crypto_pct=self._settings.max_crypto_pct,
            worst_concentration_symbol=worst_symbol,
            worst_concentration_pct=worst_pct,
            max_concentration_pct=self._settings.max_concentration_pct,
            trades_this_hour=trades_hour,
            max_trades_per_hour=self._settings.max_trades_per_hour,
        )

    # -- Private helpers --

    async def _get_kill_switch_state(self, session: AsyncSession) -> KillSwitchState | None:
        result = await session.execute(
            select(KillSwitchState).where(KillSwitchState.id == 1)
        )
        return result.scalar_one_or_none()

    async def _get_total_exposure(self, session: AsyncSession) -> float:
        result = await session.execute(
            select(func.coalesce(func.sum(Position.market_value), 0.0)).where(
                Position.quantity > 0
            )
        )
        return float(result.scalar_one())

    async def _get_daily_loss(self, session: AsyncSession) -> float:
        today = date.today()
        result = await session.execute(
            select(DailyPnL.realized_pnl).where(DailyPnL.trade_date == today)
        )
        pnl = result.scalar_one_or_none()
        return max(0.0, -(pnl or 0.0))

    async def _get_trades_last_hour(self, session: AsyncSession) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        result = await session.execute(
            select(func.count(Trade.id)).where(Trade.requested_at >= cutoff)
        )
        return result.scalar_one()

    async def _get_symbol_exposure(self, session: AsyncSession, symbol: str) -> float:
        result = await session.execute(
            select(func.coalesce(Position.market_value, 0.0)).where(
                Position.symbol == symbol, Position.quantity > 0
            )
        )
        return float(result.scalar_one_or_none() or 0.0)

    async def _get_crypto_exposure(self, session: AsyncSession) -> float:
        result = await session.execute(
            select(func.coalesce(func.sum(Position.market_value), 0.0)).where(
                Position.asset_class == "crypto", Position.quantity > 0
            )
        )
        return float(result.scalar_one())

    async def _get_worst_concentration(
        self, session: AsyncSession
    ) -> tuple[str | None, float]:
        total_exposure = await self._get_total_exposure(session)
        if total_exposure <= 0:
            return None, 0.0

        result = await session.execute(
            select(Position.symbol, Position.market_value)
            .where(Position.quantity > 0)
            .order_by(Position.market_value.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return None, 0.0
        return row[0], float(row[1]) / total_exposure
