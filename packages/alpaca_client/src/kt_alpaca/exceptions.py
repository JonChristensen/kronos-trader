from __future__ import annotations


class AlpacaError(Exception):
    """Base exception for Alpaca client errors."""


class AlpacaAuthError(AlpacaError):
    """Authentication failed."""


class AlpacaRateLimitError(AlpacaError):
    """Rate limit exceeded."""


class AlpacaInsufficientFunds(AlpacaError):
    """Insufficient buying power for the requested order."""


class AlpacaOrderRejected(AlpacaError):
    """Order was rejected by the broker."""
