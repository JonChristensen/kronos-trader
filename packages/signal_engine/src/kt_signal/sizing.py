from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionSize:
    """Calculated position size for a trade."""

    shares: float
    notional_value: float
    kelly_fraction: float


def calculate_position_size(
    confidence: float,
    net_edge: float,
    current_price: float,
    portfolio_value: float,
    max_trade_dollars: float,
    max_concentration_pct: float = 0.25,
) -> PositionSize:
    """Calculate position size using quarter-Kelly criterion.

    Kelly fraction = edge * confidence
    We use quarter-Kelly for conservatism (0.25 * full Kelly).
    Then cap at max_trade_dollars and max_concentration_pct.
    """
    if net_edge <= 0 or confidence <= 0 or current_price <= 0 or portfolio_value <= 0:
        return PositionSize(shares=0.0, notional_value=0.0, kelly_fraction=0.0)

    # Quarter-Kelly sizing
    kelly_fraction = net_edge * confidence * 0.25
    target_dollars = portfolio_value * kelly_fraction

    # Cap at max trade size
    target_dollars = min(target_dollars, max_trade_dollars)

    # Cap at max concentration
    target_dollars = min(target_dollars, portfolio_value * max_concentration_pct)

    # Minimum trade size: $10
    if target_dollars < 10.0:
        return PositionSize(shares=0.0, notional_value=0.0, kelly_fraction=kelly_fraction)

    shares = target_dollars / current_price

    return PositionSize(
        shares=round(shares, 6),  # Fractional shares
        notional_value=round(target_dollars, 2),
        kelly_fraction=kelly_fraction,
    )
