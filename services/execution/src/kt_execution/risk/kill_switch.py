from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import KillSwitchState

_logger = structlog.get_logger()


async def get_kill_switch_state(session: AsyncSession) -> KillSwitchState:
    """Get or create the singleton kill switch state."""
    result = await session.execute(
        select(KillSwitchState).where(KillSwitchState.id == 1)
    )
    state = result.scalar_one_or_none()
    if state is None:
        state = KillSwitchState(id=1, is_active=False)
        session.add(state)
        await session.commit()
        await session.refresh(state)
    return state


async def activate_kill_switch(session: AsyncSession, reason: str) -> None:
    """Activate the kill switch."""
    state = await get_kill_switch_state(session)
    state.is_active = True
    state.activated_at = datetime.now(timezone.utc)
    state.activated_reason = reason
    await session.commit()
    _logger.warning("kill_switch_activated", reason=reason)


async def deactivate_kill_switch(session: AsyncSession) -> None:
    """Deactivate the kill switch."""
    state = await get_kill_switch_state(session)
    state.is_active = False
    state.deactivated_at = datetime.now(timezone.utc)
    await session.commit()
    _logger.info("kill_switch_deactivated")
