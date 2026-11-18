"""Exercises the real Playwright flow against a local fake portal (no Clever access needed)."""
import asyncio
import os
import shutil

import pytest

pytest.importorskip("playwright")
from fake_clever import serve  # noqa: E402

from sim.config import load_config  # noqa: E402
from sim.logins.browser import run_users  # noqa: E402


def _browser_available():
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if exe:
        return os.path.exists(exe)
    from pathlib import Path
    return any(Path.home().joinpath(".cache/ms-playwright").glob("chromium*"))


pytestmark = pytest.mark.skipif(not _browser_available(), reason="no Playwright Chromium installed")


@pytest.fixture
def setup(tmp_path):
    srv = serve()
    cfg = load_config()
    cfg["logins"]["portal_url_pattern"] = "/portal"
    cfg["logins"]["concurrency"] = 2
    cfg["apps"][0]["expect_url"] = "/lantern-app"
    cfg["apps"][0]["steps"] = [{"action": "click_text", "text": "Start"}]
    cfg["apps"].append({"key": "other", "tile": "Other App", "weight": 1, "expect_url": "/other-app"})
    yield cfg, f"http://127.0.0.1:{srv.server_port}/in/demo", tmp_path
    srv.shutdown()


def test_login_and_launch(setup):
    cfg, url, out = setup
    users = [{"id": "123456", "role": "student", "apps": ["lantern"]}]
    [r] = asyncio.run(run_users(cfg, url, users, out))
    assert r["ok"], r
    assert r["launches"][0]["url"].endswith("/lantern-app")
    assert not (out / "failures").exists()


def test_failure_keeps_evidence(setup):
    cfg, url, out = setup
    cfg["apps"][0]["tile"] = "Nonexistent Tile"
    cfg["logins"]["per_user_timeout_s"] = 40
    users = [{"id": "123456", "role": "student", "apps": ["lantern"]}]
    [r] = asyncio.run(run_users(cfg, url, users, out))
    assert not r["ok"] and "not found" in r["error"]
    assert (out / "failures" / "student-123456.png").exists()
    assert (out / "failures" / "student-123456-trace.zip").exists()
