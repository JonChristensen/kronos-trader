from kt_signal.sizing import calculate_position_size


class TestCalculatePositionSize:
    def test_basic_sizing(self):
        result = calculate_position_size(
            confidence=0.7,
            net_edge=0.02,
            current_price=100.0,
            portfolio_value=50000.0,
            max_trade_dollars=500.0,
        )
        assert result.shares > 0
        assert result.notional_value > 0
        assert result.notional_value <= 500.0

    def test_zero_edge_no_position(self):
        result = calculate_position_size(
            confidence=0.8,
            net_edge=0.0,
            current_price=100.0,
            portfolio_value=50000.0,
            max_trade_dollars=500.0,
        )
        assert result.shares == 0.0
        assert result.notional_value == 0.0

    def test_negative_edge_no_position(self):
        result = calculate_position_size(
            confidence=0.8,
            net_edge=-0.01,
            current_price=100.0,
            portfolio_value=50000.0,
            max_trade_dollars=500.0,
        )
        assert result.shares == 0.0

    def test_capped_at_max_trade(self):
        result = calculate_position_size(
            confidence=1.0,
            net_edge=0.10,  # Very high edge
            current_price=10.0,
            portfolio_value=100000.0,
            max_trade_dollars=500.0,
        )
        assert result.notional_value <= 500.0

    def test_capped_at_max_concentration(self):
        result = calculate_position_size(
            confidence=1.0,
            net_edge=0.10,
            current_price=10.0,
            portfolio_value=1000.0,
            max_trade_dollars=5000.0,
            max_concentration_pct=0.25,
        )
        assert result.notional_value <= 1000.0 * 0.25

    def test_minimum_trade_size(self):
        result = calculate_position_size(
            confidence=0.1,
            net_edge=0.001,
            current_price=100.0,
            portfolio_value=1000.0,
            max_trade_dollars=500.0,
        )
        # Quarter-Kelly with tiny edge: 1000 * 0.001 * 0.1 * 0.25 = $0.025
        # Below $10 minimum
        assert result.shares == 0.0

    def test_fractional_shares(self):
        result = calculate_position_size(
            confidence=0.8,
            net_edge=0.03,
            current_price=3500.0,  # High price stock
            portfolio_value=50000.0,
            max_trade_dollars=500.0,
        )
        # At $3500/share, should get fractional shares
        assert result.shares > 0
        assert result.shares < 1.0
