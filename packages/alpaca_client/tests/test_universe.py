from kt_alpaca.universe import UniverseManager
from kt_shared.models import AssetClass


class TestUniverseManager:
    def test_static_universe_contains_crypto(self):
        # UniverseManager requires a TradingClient, but get_static_universe
        # doesn't use it — pass None for unit testing.
        manager = UniverseManager(trading_client=None)  # type: ignore
        instruments = manager.get_static_universe()

        crypto = [i for i in instruments if i.asset_class == AssetClass.CRYPTO]
        assert len(crypto) >= 5
        symbols = {i.symbol for i in crypto}
        assert "BTC/USD" in symbols
        assert "ETH/USD" in symbols

    def test_static_universe_contains_etfs(self):
        manager = UniverseManager(trading_client=None)  # type: ignore
        instruments = manager.get_static_universe()

        etfs = [i for i in instruments if i.asset_class == AssetClass.ETF]
        assert len(etfs) >= 7
        symbols = {i.symbol for i in etfs}
        assert "GLD" in symbols
        assert "TLT" in symbols

    def test_crypto_instruments_fractionable(self):
        manager = UniverseManager(trading_client=None)  # type: ignore
        instruments = manager.get_static_universe()

        for i in instruments:
            if i.is_crypto:
                assert i.fractionable is True
                assert i.min_order_size < 1.0
