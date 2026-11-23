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
    cfg = load_config()  # real login settings: Password click, two-step form, portal pattern
    cfg["logins"]["portal_url_pattern"] = "/in/[^/?]+/(student|teacher)"
    cfg["logins"]["concurrency"] = 2
    cfg["apps"] = [
        {"key": "lantern", "tile": "Lantern", "weight": 1, "expect_url": "/lantern-app",
         "steps": [{"action": "click_text", "text": "Start"}]},
        {"key": "devapp", "tile": "Lantern Learn - DEMO App", "weight": 1,
         "expect_url": "/api/auth/callback\\?code=", "fail_url": "/login/error"},
        {"key": "strict", "tile": "Strict App", "weight": 1,
         "expect_url": "/api/auth/callback\\?code=", "fail_url": "/login/error"},
    ]
    yield cfg, f"http://127.0.0.1:{srv.server_port}/in/demo", tmp_path
    srv.shutdown()


def test_login_and_launch(setup):
    cfg, url, out = setup
    users = [{"id": "123456", "role": "student", "apps": ["lantern"]}]
    [r] = asyncio.run(run_users(cfg, url, users, out))
    assert r["ok"], r
    assert r["launches"][0]["url"].endswith("/lantern-app")
    assert not (out / "failures").exists()


def test_teacher_portal(setup):
    cfg, url, out = setup
    [r] = asyncio.run(run_users(cfg, url, [{"id": "73079", "role": "teacher", "apps": ["lantern"]}], out))
    assert r["ok"], r


def test_launch_counts_when_app_callback_is_unreachable(setup):
    """A dev app whose redirect URI is localhost: Clever's hand-off still counts."""
    cfg, url, out = setup
    [r] = asyncio.run(run_users(cfg, url, [{"id": "300899", "role": "student", "apps": ["devapp"]}], out))
    assert r["ok"], r
    launch = r["launches"][0]
    assert "/api/auth/callback?code=" in launch["url"] and "abc123" not in launch["url"]
    assert launch["app_page_loaded"] is False


def test_app_error_page_counts_as_failure(setup):
    """Clever's hand-off worked, but the app had no matching account."""
    cfg, url, out = setup
    [r] = asyncio.run(run_users(cfg, url, [{"id": "300899", "role": "student", "apps": ["strict"]}], out))
    assert not r["ok"]
    assert "AppRejectedLogin" in r["error"] and "reason=no_match" in r["error"]


def test_failure_keeps_evidence(setup):
    cfg, url, out = setup
    cfg["apps"][0]["tile"] = "Nonexistent Tile"
    cfg["logins"]["per_user_timeout_s"] = 40
    users = [{"id": "123456", "role": "student", "apps": ["lantern"]}]
    [r] = asyncio.run(run_users(cfg, url, users, out))
    assert not r["ok"] and "not found" in r["error"]
    assert (out / "failures" / "student-123456.png").exists()
    assert (out / "failures" / "student-123456-trace.zip").exists()
