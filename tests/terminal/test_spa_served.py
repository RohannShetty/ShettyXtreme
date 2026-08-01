"""The built Svelte SPA is served from /static/."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from shettyxtreme.terminal.api.app import app


def test_spa_index_served() -> None:
    resp = TestClient(app).get("/static/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert '<div id="app"></div>' in body
    asset = re.search(r'src="(/static/assets/[^"]+\.js)"', body)
    assert asset is not None, "built JS asset link missing from index.html"
    asset_resp = TestClient(app).get(asset.group(1))
    assert asset_resp.status_code == 200
