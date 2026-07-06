"""Retention policy model and markdown loader.

The business policy lives in ``politica_retencion.md``. Because markdown is
free-form, the loader extracts a small set of well-known numeric thresholds
via tolerant regular expressions and falls back to conservative enterprise
defaults for anything it cannot find, emitting warnings rather than failing.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_LOGGER = logging.getLogger(__name__)


class RetentionPolicy(BaseModel):
    """Typed representation of the enterprise retention policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_cost_threshold: float = Field(
        200.0, ge=0, description="Offer cost above which HITL approval is mandatory."
    )
    max_offer_cost: float = Field(
        500.0, ge=0, description="Hard cap: offers above this are never proposed."
    )
    max_discount_pct: float = Field(
        40.0, ge=0, le=100, description="Maximum discount the business allows."
    )
    min_roi: float = Field(1.0, description="Minimum acceptable ROI ratio for an offer.")
    high_value_clv: float = Field(
        1000.0, ge=0, description="CLV above which a customer is high value."
    )

    @classmethod
    def default(cls) -> "RetentionPolicy":
        """Return the built-in default policy."""
        return cls()


_PATTERNS: dict[str, str] = {
    "approval_cost_threshold": r"(?:aprobaci[oó]n|approval).{0,40}?(\d+(?:\.\d+)?)",
    "max_offer_cost": r"(?:costo\s+m[aá]ximo|max(?:imum)?\s+cost).{0,40}?(\d+(?:\.\d+)?)",
    "max_discount_pct": r"(?:descuento\s+m[aá]ximo|max(?:imum)?\s+discount).{0,40}?(\d+(?:\.\d+)?)",
    "min_roi": r"(?:roi\s+m[ií]nimo|min(?:imum)?\s+roi).{0,40}?(\d+(?:\.\d+)?)",
    "high_value_clv": r"(?:alto\s+valor|high\s+value).{0,40}?(\d+(?:\.\d+)?)",
}


def load_policy(md_path: str | Path | None) -> RetentionPolicy:
    """Load the retention policy from markdown, falling back to defaults.

    Args:
        md_path: Path to ``politica_retencion.md`` or ``None``.

    Returns:
        A validated :class:`RetentionPolicy`.
    """
    if md_path is None or not Path(md_path).exists():
        _LOGGER.warning("policy file not found; using default retention policy")
        return RetentionPolicy.default()

    text = Path(md_path).read_text(encoding="utf-8").lower()
    overrides: dict[str, float] = {}
    for field, pattern in _PATTERNS.items():
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            overrides[field] = float(match.group(1))
    if not overrides:
        _LOGGER.warning("no thresholds parsed from policy; using defaults")
    merged = {**RetentionPolicy.default().model_dump(), **overrides}
    return RetentionPolicy(**merged)
