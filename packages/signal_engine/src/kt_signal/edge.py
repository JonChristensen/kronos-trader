from __future__ import annotations

from dataclasses import dataclass

from kt_shared.constants import TRANSACTION_COSTS
from kt_shared.models import AssetClass, Side


@dataclass
class EdgeResult:
    """Result of edge calculation for a single instrument."""

    expected_return: float
    transaction_cost: float
    net_edge: float
    side: Side
    confidence: float
    expected_volatility: float


def calculate_edge(
    current_price: float,
    predicted_close: float,
    ensemble_std: float,
    predicted_high: float,
    predicted_low: float,
    asset_class: AssetClass,
    confidence: float,
) -> EdgeResult:
    """Calculate the trading edge for an instrument.

    Edge = |expected_return| - transaction_costs.
    Positive edge = profitable signal after costs.
    """
    if current_price <= 0:
        return EdgeResult(
            expected_return=0.0,
            transaction_cost=0.0,
            net_edge=0.0,
            side=Side.BUY,
            confidence=0.0,
            expected_volatility=0.0,
        )

    expected_return = (predicted_close - current_price) / current_price
    side = Side.BUY if expected_return > 0 else Side.SELL

    # Transaction costs: entry + exit (round trip)
    cost_rate = TRANSACTION_COSTS.get(asset_class.value, 0.001)
    transaction_cost = cost_rate * 2  # Round trip

    net_edge = abs(expected_return) - transaction_cost

    expected_volatility = (predicted_high - predicted_low) / current_price

    return EdgeResult(
        expected_return=expected_return,
        transaction_cost=transaction_cost,
        net_edge=net_edge,
        side=side,
        confidence=confidence,
        expected_volatility=expected_volatility,
    )
