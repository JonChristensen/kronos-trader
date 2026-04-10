from __future__ import annotations

import asyncio

import structlog
import torch

from kt_shared.config import KronosSettings

_logger = structlog.get_logger()


class KronosModelManager:
    """Manages Kronos model lifecycle: loading, caching, device placement."""

    def __init__(self, settings: KronosSettings) -> None:
        self.settings = settings
        self._predictor = None
        self._device: str = settings.device

    async def load(self) -> None:
        """Load model from HuggingFace Hub. Runs in executor to avoid blocking."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_sync)

    def _load_sync(self) -> None:
        """Synchronous model loading — called via run_in_executor."""
        # Resolve device: fall back to CPU if CUDA unavailable
        if self._device == "cuda" and not torch.cuda.is_available():
            _logger.warning("cuda_unavailable", fallback="cpu")
            self._device = "cpu"

        _logger.info(
            "loading_kronos_model",
            model=self.settings.model_name,
            tokenizer=self.settings.tokenizer_name,
            device=self._device,
        )

        # Import Kronos modules — they require torch to be available
        from model import Kronos, KronosPredictor, KronosTokenizer

        tokenizer = KronosTokenizer.from_pretrained(self.settings.tokenizer_name)
        model = Kronos.from_pretrained(self.settings.model_name)

        self._predictor = KronosPredictor(
            model=model,
            tokenizer=tokenizer,
            device=self._device,
            max_context=self.settings.max_context,
        )

        _logger.info(
            "kronos_model_loaded",
            model=self.settings.model_name,
            device=self._device,
            max_context=self.settings.max_context,
        )

    @property
    def predictor(self):
        """Access the loaded KronosPredictor instance."""
        if self._predictor is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        return self._predictor

    @property
    def device(self) -> str:
        return self._device

    @property
    def is_loaded(self) -> bool:
        return self._predictor is not None
