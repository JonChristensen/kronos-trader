from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd
import structlog
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from kt_shared.config import AlpacaSettings
from kt_shared.constants import KRONOS_LOOKBACK
from kt_shared.models import AssetClass, Timeframe

_logger = structlog.get_logger()

# Map our Timeframe enum to Alpaca TimeFrame objects
_TIMEFRAME_MAP: dict[Timeframe, TimeFrame] = {
    Timeframe.DAILY: TimeFrame.Day,
    Timeframe.HOURLY: TimeFrame.Hour,
}


class MarketDataFetcher:
    """Fetch OHLCV bars from Alpaca for feeding into Kronos."""

    def __init__(self, settings: AlpacaSettings) -> None:
        self._settings = settings
        self._stock_client = StockHistoricalDataClient(
            api_key=settings.api_key,
            secret_key=settings.secret_key,
        )
        # Crypto client doesn't require authentication
        self._crypto_client = CryptoHistoricalDataClient()
        self._semaphore = asyncio.Semaphore(10)  # Max concurrent API calls

    def _classify_symbol(self, symbol: str) -> AssetClass:
        """Determine asset class from symbol format."""
        if "/" in symbol:
            return AssetClass.CRYPTO
        return AssetClass.STOCK  # ETFs use same API as stocks

    async def get_ohlcv_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = KRONOS_LOOKBACK,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV bars for a single symbol.

        Returns a DataFrame with columns: [timestamp, open, high, low, close, volume]
        matching Kronos input format.
        """
        async with self._semaphore:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_bars_sync, symbol, timeframe, limit
            )

    def _fetch_bars_sync(
        self, symbol: str, timeframe: Timeframe, limit: int
    ) -> pd.DataFrame:
        """Synchronous bar fetch — runs in thread pool."""
        asset_class = self._classify_symbol(symbol)
        alpaca_tf = _TIMEFRAME_MAP[timeframe]

        # Calculate start date based on timeframe and limit
        if timeframe == Timeframe.DAILY:
            start = datetime.now(timezone.utc) - timedelta(days=limit * 2)  # Buffer for weekends
        else:
            start = datetime.now(timezone.utc) - timedelta(hours=limit * 2)

        if asset_class == AssetClass.CRYPTO:
            request = CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=alpaca_tf,
                start=start,
            )
            bars = self._crypto_client.get_crypto_bars(request)
        else:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=alpaca_tf,
                start=start,
                feed=self._settings.data_feed,
            )
            bars = self._stock_client.get_stock_bars(request)

        # Convert to DataFrame
        df = bars.df
        if df.empty:
            _logger.warning("no_bars_returned", symbol=symbol, timeframe=timeframe.value)
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Reset multi-index (symbol, timestamp) to flat DataFrame
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index(level="symbol", drop=True)

        df = df.reset_index()
        df = df.rename(columns={"timestamp": "timestamp"})

        # Ensure correct column order and names for Kronos
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].tail(limit)
        df = df.reset_index(drop=True)

        _logger.debug(
            "bars_fetched",
            symbol=symbol,
            timeframe=timeframe.value,
            rows=len(df),
        )
        return df

    async def get_batch_ohlcv(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        limit: int = KRONOS_LOOKBACK,
    ) -> dict[str, pd.DataFrame]:
        """Fetch bars for multiple symbols concurrently."""
        tasks = [self.get_ohlcv_bars(s, timeframe, limit) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        data: dict[str, pd.DataFrame] = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                _logger.error("batch_fetch_error", symbol=symbol, error=str(result))
                continue
            if not result.empty:
                data[symbol] = result

        _logger.info(
            "batch_fetch_complete",
            timeframe=timeframe.value,
            requested=len(symbols),
            fetched=len(data),
        )
        return data

    async def get_latest_price(self, symbol: str) -> float | None:
        """Get the most recent close price for a symbol."""
        df = await self.get_ohlcv_bars(symbol, Timeframe.DAILY, limit=1)
        if df.empty:
            return None
        return float(df.iloc[-1]["close"])

    async def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """Get latest prices for multiple symbols."""
        data = await self.get_batch_ohlcv(symbols, Timeframe.DAILY, limit=1)
        return {
            symbol: float(df.iloc[-1]["close"])
            for symbol, df in data.items()
            if not df.empty
        }
