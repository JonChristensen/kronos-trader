from __future__ import annotations

from typing import Literal

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = structlog.get_logger()


def _mask_db_url(url: str) -> str:
    """Show only host portion of a database URL (strip credentials)."""
    if "@" in url:
        return url.split("@", 1)[-1]
    return "(no-auth)"


def _mask_token(token: str) -> str:
    return "(default)" if token == "change-this-to-a-random-secret" else "***"


class AlpacaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ALPACA_")

    api_key: str = ""
    secret_key: str = ""
    paper: bool = True
    data_feed: Literal["iex", "sip"] = "iex"

    @property
    def base_url(self) -> str:
        if self.paper:
            return "https://paper-api.alpaca.markets"
        return "https://api.alpaca.markets"

    def log_config(self) -> None:
        _logger.info(
            "config_effective",
            service="alpaca",
            paper=self.paper,
            data_feed=self.data_feed,
            api_key=self.api_key[:8] + "..." if self.api_key else "(empty)",
            base_url=self.base_url,
        )


class ExecutionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EXEC_")

    database_url: str = "postgresql+asyncpg://kt:kt@localhost:5433/kt_execution"
    host: str = "0.0.0.0"
    port: int = 8001
    auth_token: str = "change-this-to-a-random-secret"

    # Risk limits
    max_position_dollars: int = 1000
    max_daily_loss_dollars: int = 200
    max_trade_dollars: int = 500
    max_trades_per_hour: int = 50
    max_concentration_pct: float = 0.25  # Max % of portfolio in a single instrument
    max_crypto_pct: float = 0.30  # Max % of portfolio in crypto

    def log_config(self) -> None:
        _logger.info(
            "config_effective",
            service="execution",
            host=self.host,
            port=self.port,
            database_url=_mask_db_url(self.database_url),
            auth_token=_mask_token(self.auth_token),
            max_position_dollars=self.max_position_dollars,
            max_daily_loss_dollars=self.max_daily_loss_dollars,
            max_trade_dollars=self.max_trade_dollars,
            max_trades_per_hour=self.max_trades_per_hour,
            max_concentration_pct=self.max_concentration_pct,
            max_crypto_pct=self.max_crypto_pct,
        )


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_")

    execution_service_url: str = "http://localhost:8001"
    auth_token: str = "change-this-to-a-random-secret"
    daily_cycle_time: str = "09:35"  # HH:MM in US/Eastern
    intraday_interval_seconds: int = 3600
    crypto_interval_seconds: int = 14400  # 4 hours
    edge_threshold: float = 0.005  # 0.5% minimum expected return
    confidence_threshold: float = 0.4
    max_stale_order_seconds: int = 1800  # Cancel unfilled orders after 30 min

    def log_config(self) -> None:
        _logger.info(
            "config_effective",
            service="agent",
            execution_service_url=self.execution_service_url,
            auth_token=_mask_token(self.auth_token),
            daily_cycle_time=self.daily_cycle_time,
            intraday_interval_seconds=self.intraday_interval_seconds,
            crypto_interval_seconds=self.crypto_interval_seconds,
            edge_threshold=self.edge_threshold,
            confidence_threshold=self.confidence_threshold,
            max_stale_order_seconds=self.max_stale_order_seconds,
        )


class KronosSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KRONOS_")

    model_name: str = "NeoQuasar/Kronos-small"
    tokenizer_name: str = "NeoQuasar/Kronos-Tokenizer-base"
    device: str = "cuda"  # Falls back to "cpu" at runtime if CUDA unavailable
    max_context: int = 512
    daily_pred_len: int = 5  # Predict 5 daily candles ahead
    intraday_pred_len: int = 8  # Predict 8 hourly candles ahead
    sample_count: int = 20  # Ensemble runs for confidence
    top_p: float = 0.9
    temperature: float = 1.0

    def log_config(self) -> None:
        _logger.info(
            "config_effective",
            service="kronos",
            model_name=self.model_name,
            tokenizer_name=self.tokenizer_name,
            device=self.device,
            max_context=self.max_context,
            daily_pred_len=self.daily_pred_len,
            intraday_pred_len=self.intraday_pred_len,
            sample_count=self.sample_count,
            top_p=self.top_p,
            temperature=self.temperature,
        )
