from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from kt_shared.config import ExecutionSettings


def _get_settings() -> ExecutionSettings:
    return ExecutionSettings()


async def verify_auth_token(
    authorization: str = Header(...),
    settings: ExecutionSettings = Depends(_get_settings),
) -> None:
    """Verify the bearer token from agent requests."""
    expected = f"Bearer {settings.auth_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid auth token")
