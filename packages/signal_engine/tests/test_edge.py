from kt_shared.models import AssetClass, Side
from kt_signal.edge import calculate_edge


class TestCalculateEdge:
    def test_buy_signal_when_predicted_higher(self):
        result = calculate_edge(
            current_price=100.0,
            predicted_close=102.0,
            ensemble_std=0.5,
            predicted_high=103.0,
            predicted_low=99.0,
            asset_class=AssetClass.STOCK,
            confidence=0.8,
        )
        assert result.side == Side.BUY
        assert result.expected_return > 0
        assert abs(result.expected_return - 0.02) < 1e-6

    def test_sell_signal_when_predicted_lower(self):
        result = calculate_edge(
            current_price=100.0,
            predicted_close=97.0,
            ensemble_std=0.5,
            predicted_high=101.0,
            predicted_low=96.0,
            asset_class=AssetClass.STOCK,
            confidence=0.7,
        )
        assert result.side == Side.SELL
        assert result.expected_return < 0

    def test_net_edge_accounts_for_transaction_costs(self):
        result = calculate_edge(
            current_price=100.0,
            predicted_close=100.5,
            ensemble_std=0.1,
            predicted_high=101.0,
            predicted_low=100.0,
            asset_class=AssetClass.STOCK,
            confidence=0.9,
        )
        # Expected return = 0.5%, stock round-trip cost = 0.2%
        assert result.net_edge < result.expected_return
        assert result.net_edge > 0  # 0.5% - 0.2% = 0.3%

    def test_crypto_higher_transaction_costs(self):
        result = calculate_edge(
            current_price=50000.0,
            predicted_close=50500.0,
            ensemble_std=100.0,
            predicted_high=51000.0,
            predicted_low=49500.0,
            asset_class=AssetClass.CRYPTO,
            confidence=0.6,
        )
        # Crypto costs: 0.5% round trip
        assert result.transaction_cost == 0.005

    def test_etf_lowest_transaction_costs(self):
        result = calculate_edge(
            current_price=180.0,
            predicted_close=182.0,
            ensemble_std=0.3,
            predicted_high=183.0,
            predicted_low=179.0,
            asset_class=AssetClass.ETF,
            confidence=0.8,
        )
        assert result.transaction_cost == 0.001  # 0.05% * 2

    def test_zero_price_returns_zero_edge(self):
        result = calculate_edge(
            current_price=0.0,
            predicted_close=100.0,
            ensemble_std=1.0,
            predicted_high=101.0,
            predicted_low=99.0,
            asset_class=AssetClass.STOCK,
            confidence=0.5,
        )
        assert result.net_edge == 0.0
        assert result.expected_return == 0.0

    def test_expected_volatility(self):
        result = calculate_edge(
            current_price=100.0,
            predicted_close=101.0,
            ensemble_std=0.5,
            predicted_high=105.0,
            predicted_low=95.0,
            asset_class=AssetClass.STOCK,
            confidence=0.8,
        )
        assert abs(result.expected_volatility - 0.10) < 1e-6  # (105-95)/100
