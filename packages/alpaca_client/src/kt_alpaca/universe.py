from __future__ import annotations

import structlog
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest

from kt_shared.constants import CRYPTO_UNIVERSE, ETF_UNIVERSE
from kt_shared.models import AssetClass

from .models import Instrument

_logger = structlog.get_logger()


class UniverseManager:
    """Manages the tradable universe of instruments."""

    def __init__(self, trading_client: TradingClient) -> None:
        self._client = trading_client

    def get_static_universe(self) -> list[Instrument]:
        """Return the fixed crypto + ETF universe."""
        instruments: list[Instrument] = []

        for symbol in CRYPTO_UNIVERSE:
            instruments.append(
                Instrument(
                    symbol=symbol,
                    asset_class=AssetClass.CRYPTO,
                    exchange="CBSE",
                    min_order_size=0.0001,
                    fractionable=True,
                )
            )

        for symbol in ETF_UNIVERSE:
            instruments.append(
                Instrument(
                    symbol=symbol,
                    asset_class=AssetClass.ETF,
                    exchange="NYSE",
                    min_order_size=1.0,
                    fractionable=True,
                )
            )

        return instruments

    async def screen_small_caps(
        self,
        min_avg_volume: int = 500_000,
        max_symbols: int = 20,
    ) -> list[Instrument]:
        """Screen for liquid small-cap stocks.

        Uses Alpaca's asset listing to find tradable US equities.
        Volume filtering must be done via market data since the asset
        endpoint doesn't include volume.
        """
        try:
            request = GetAssetsRequest(status="active")
            assets = self._client.get_all_assets(request)

            # Filter for US equities that are tradable and fractionable
            candidates = [
                a
                for a in assets
                if a.tradable
                and a.asset_class == "us_equity"
                and a.exchange in ("NYSE", "NASDAQ")
                and a.fractionable
                and not a.symbol.endswith("W")  # Skip warrants
                and "." not in a.symbol  # Skip preferred shares etc.
            ]

            # Take a reasonable subset — full volume screening requires market data
            # which we'll refine in the pipeline
            selected = candidates[:max_symbols]

            instruments = [
                Instrument(
                    symbol=a.symbol,
                    asset_class=AssetClass.STOCK,
                    exchange=str(a.exchange),
                    min_order_size=1.0,
                    fractionable=bool(a.fractionable),
                )
                for a in selected
            ]

            _logger.info("small_cap_screen", candidates=len(candidates), selected=len(instruments))
            return instruments

        except Exception as exc:
            _logger.error("small_cap_screen_failed", error=str(exc))
            return []

    async def get_full_universe(self) -> list[Instrument]:
        """Return static universe plus dynamically screened small-caps."""
        static = self.get_static_universe()
        small_caps = await self.screen_small_caps()
        return static + small_caps
