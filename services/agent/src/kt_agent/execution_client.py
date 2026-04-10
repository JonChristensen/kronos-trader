"""HTTP client for the execution service."""

from __future__ import annotations

import structlog
import httpx

from kt_shared.config import AgentSettings
from kt_shared.models import TradeRequest, TradeResponse

_logger = structlog.get_logger()


class ExecutionClient:
    """Sends trade requests to the execution service over HTTP."""

    def __init__(self, settings: AgentSettings) -> None:
        self._base_url = settings.execution_service_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {settings.auth_token}"}
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=30.0,
        )

    async def submit_trade(self, request: TradeRequest) -> TradeResponse:
        """Submit a trade request to the execution service."""
        response = await self._client.post(
            "/api/v1/trade",
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return TradeResponse.model_validate(response.json())

    async def get_positions(self) -> list[dict]:
        response = await self._client.get("/api/v1/positions")
        response.raise_for_status()
        return response.json()

    async def get_risk_status(self) -> dict:
        response = await self._client.get("/api/v1/risk-status")
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> bool:
        try:
            response = await self._client.get("/api/v1/health")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
