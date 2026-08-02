"""Indicator adapters — expose sub-features of a composite indicator.

FeatureEngine only stores what an indicator's ``update()`` returns (or its
``value`` property). Composite indicators such as ADX hold secondary values
(``di_plus`` / ``di_minus``) that the regime classifier consumes. This
adapter lets one source indicator feed multiple named features without
duplicating its computation.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.core.data_models.market_data import Tick


class AttributeIndicator:
    """Adapter exposing one attribute of a source indicator as a feature.

    ``update()`` delegates to the source so both share a single computation
    state; ``value`` returns the source attribute (None until the source has
    warmed up, in which case FeatureEngine skips the feature key).
    """

    def __init__(self, source: Any, attribute: str) -> None:
        self._source = source
        self._attribute = attribute

    @property
    def value(self) -> Any:
        return getattr(self._source, self._attribute)

    def update(self, tick: Tick) -> None:
        self._source.update(tick)
        return None
