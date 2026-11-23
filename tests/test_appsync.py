import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sim.appsync import run_app_syncs

SECRET = "s3cret"


class H(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        H.calls.append((self.path, self.headers.get("Authorization")))
        if self.headers.get("Authorization") != f"Bearer {SECRET}":
            return self._json(401, {"error": "Not signed in."})
        if self.path == "/live":
            return self._json(200, {"mode": "live", "counts": {"users": 455, "sections": 30}, "warnings": []})
        if self.path == "/mock":
            return self._json(200, {"mode": "mock", "counts": {"users": 12}, "warnings": []})
        return self._json(500, {"mode": "live", "error": "Clever returned 401"})

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    H.calls = []
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def cfg_for():
    return {"logins": {"pre_batch_sync": [{"name": "lantern", "url_env": "T_SYNC_URL",
                                           "secret_env": "T_SYNC_SECRET", "expect_mode": "live"}]}}


def test_live_sync_ok(server, monkeypatch):
    monkeypatch.setenv("T_SYNC_URL", server + "/live")
    monkeypatch.setenv("T_SYNC_SECRET", SECRET)
    [r] = run_app_syncs(cfg_for())
    assert r["ok"] and r["mode"] == "live" and "users 455" in r["detail"]
    assert H.calls == [("/live", f"Bearer {SECRET}")]


def test_mock_mode_is_flagged(server, monkeypatch):
    monkeypatch.setenv("T_SYNC_URL", server + "/mock")
    monkeypatch.setenv("T_SYNC_SECRET", SECRET)
    [r] = run_app_syncs(cfg_for())
    assert not r["ok"] and "'mock'" in r["detail"]


def test_bad_secret_and_server_error_reported(server, monkeypatch):
    monkeypatch.setenv("T_SYNC_URL", server + "/live")
    monkeypatch.setenv("T_SYNC_SECRET", "wrong")
    [r] = run_app_syncs(cfg_for())
    assert not r["ok"] and "HTTP 401" in r["detail"]
    monkeypatch.setenv("T_SYNC_URL", server + "/boom")
    monkeypatch.setenv("T_SYNC_SECRET", SECRET)
    [r] = run_app_syncs(cfg_for())
    assert not r["ok"] and "HTTP 500" in r["detail"] and "Clever returned 401" in r["detail"]


def test_missing_settings_skip(monkeypatch):
    monkeypatch.delenv("T_SYNC_URL", raising=False)
    [r] = run_app_syncs(cfg_for())
    assert r["skipped"] and not r["ok"]


def test_unreachable_does_not_raise(monkeypatch):
    monkeypatch.setenv("T_SYNC_URL", "http://127.0.0.1:9/sync")
    monkeypatch.setenv("T_SYNC_SECRET", SECRET)
    [r] = run_app_syncs(cfg_for())
    assert not r["ok"] and "ConnectionError" in r["detail"]


def test_real_config_has_lantern_sync():
    from sim.config import load_config
    [s] = load_config()["logins"]["pre_batch_sync"]
    assert s["name"] == "lantern" and s["expect_mode"] == "live"
