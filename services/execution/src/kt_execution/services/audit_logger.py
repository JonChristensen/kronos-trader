from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AuditLog

_logger = structlog.get_logger()


class AuditLogger:
    async def log(
        self,
        session: AsyncSession,
        event_type: str,
        request_id: UUID | None,
        details: dict,
    ) -> None:
        entry = AuditLog(
            event_type=event_type,
            request_id=request_id,
            details=details,
        )
        session.add(entry)
        await session.commit()

        _logger.info("audit_log", event_type=event_type, request_id=str(request_id))
