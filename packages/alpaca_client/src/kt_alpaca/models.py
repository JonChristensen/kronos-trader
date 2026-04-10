from __future__ import annotations

from dataclasses import dataclass

from kt_shared.models import AssetClass


@dataclass(frozen=True)
class Instrument:
    """A tradable instrument in our universe."""

    symbol: str
    asset_class: AssetClass
    exchange: str = ""
    min_order_size: float = 1.0
    fractionable: bool = False

    @property
    def is_crypto(self) -> bool:
        return self.asset_class == AssetClass.CRYPTO
