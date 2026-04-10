from __future__ import annotations

from zoneinfo import ZoneInfo

# Market universes — static lists of instruments to track.
# Small-cap stocks are screened dynamically; these are the always-on lists.

CRYPTO_UNIVERSE: list[str] = [
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "AVAX/USD",
    "LINK/USD",
]

ETF_UNIVERSE: list[str] = [
    "GLD",   # Gold
    "SLV",   # Silver
    "USO",   # Crude oil
    "TLT",   # 20+ yr treasuries
    "HYG",   # High-yield corporate bonds
    "XLE",   # Energy sector
    "XLF",   # Financials sector
]

# US equity market hours (Eastern time)
MARKET_TZ = ZoneInfo("US/Eastern")
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# Transaction cost estimates by asset class (as fraction of trade value)
TRANSACTION_COSTS: dict[str, float] = {
    "stock": 0.001,   # ~0.1% (spread + SEC fee)
    "crypto": 0.0025,  # ~0.25% (Alpaca crypto spread)
    "etf": 0.0005,     # ~0.05% (tight ETF spreads)
}

# Kronos model lookback — number of historical candles to feed the model
KRONOS_LOOKBACK = 512
