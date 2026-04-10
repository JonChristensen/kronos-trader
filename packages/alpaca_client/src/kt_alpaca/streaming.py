from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from alpaca.data.live import CryptoDataStream, StockDataStream

from kt_shared.config import AlpacaSettings

_logger = structlog.get_logger()


class MarketStreamManager:
    """Manages WebSocket streaming connections for real-time market data.

    Scaffolded for future use — the initial system uses polling via
    MarketDataFetcher. Streaming will be added for lower-latency
    intraday signals.
    """

    def __init__(self, settings: AlpacaSettings) -> None:
        self._settings = settings
        self._stock_stream: StockDataStream | None = None
        self._crypto_stream: CryptoDataStream | None = None

    async def start_stock_stream(
        self,
        symbols: list[str],
        on_bar: Callable[[Any], None] | None = None,
    ) -> None:
        """Start streaming stock bars for the given symbols."""
        self._stock_stream = StockDataStream(
            api_key=self._settings.api_key,
            secret_key=self._settings.secret_key,
            feed=self._settings.data_feed,
        )
        if on_bar:
            self._stock_stream.subscribe_bars(on_bar, *symbols)
        _logger.info("stock_stream_started", symbols=symbols)

    async def start_crypto_stream(
        self,
        symbols: list[str],
        on_bar: Callable[[Any], None] | None = None,
    ) -> None:
        """Start streaming crypto bars for the given symbols."""
        self._crypto_stream = CryptoDataStream(
            api_key=self._settings.api_key,
            secret_key=self._settings.secret_key,
        )
        if on_bar:
            self._crypto_stream.subscribe_bars(on_bar, *symbols)
        _logger.info("crypto_stream_started", symbols=symbols)

    async def stop(self) -> None:
        """Stop all active streams."""
        if self._stock_stream:
            self._stock_stream.stop()
        if self._crypto_stream:
            self._crypto_stream.stop()
        _logger.info("streams_stopped")
