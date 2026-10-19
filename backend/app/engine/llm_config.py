"""Runtime configuration for per-civilization LLM goal sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class LLMPlayerConfig:
    """Non-game-state configuration for one AI civilization.

    API keys deliberately live outside ``GameState`` and are excluded from the
    dataclass repr so accidental logging cannot expose them.
    """

    model: str | None = None
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)
    temperature: float = 0.7
    label: str | None = None

    def __post_init__(self) -> None:
        if self.model is not None and not self.model.strip():
            raise ValueError("model must not be blank")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        if self.base_url is None or not self.base_url.strip():
            return
        parsed = urlsplit(self.base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @property
    def display_label(self) -> str:
        """Safe label suitable for spectator responses and logs."""
        return self.label or self.model or "OpenAI-compatible LLM"
