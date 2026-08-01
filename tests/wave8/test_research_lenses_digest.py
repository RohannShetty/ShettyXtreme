"""Tests for the lens registry and context digest (spec §3.1)."""
from __future__ import annotations

import pytest

from shettyxtreme.research.digest import ContextDigest
from shettyxtreme.research.lenses import LENSES, get_lens, list_lenses


def test_three_lenses_registered() -> None:
    names = {l.name for l in list_lenses()}
    assert names == {"oi_iv_flow", "directional_momentum", "tail_risk"}


def test_get_lens_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_lens("value")


def test_lens_prompt_builds() -> None:
    lens = get_lens("tail_risk")
    prompt = lens.build_prompt("SNAPSHOT")
    assert "SNAPSHOT" in prompt
    assert "{digest}" not in prompt


def test_digest_build_marks_sources() -> None:
    d = ContextDigest({"regime": "TRENDING_UP"})
    text = d.build()
    assert "[SOURCE: regime]" in text
    assert "TRENDING_UP" in text


def test_digest_unsourced_when_empty() -> None:
    text = ContextDigest().build()
    assert "[UNSOURCED]" in text


def test_digest_caps_sources_and_chars() -> None:
    d = ContextDigest()
    with pytest.raises(ValueError):
        for i in range(9):
            d.add(f"s{i}", "x")
    d2 = ContextDigest({"a": "y" * 5000})
    assert len(d2.sources["a"]) <= 2000
