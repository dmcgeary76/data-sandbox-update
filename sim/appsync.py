"""Ask connected apps to pull the latest roster from Clever before users log in.

Students added by the morning's drift exist in Clever, but an app only knows about
them once it has synced. Calling the app's own sync endpoint first means today's new
students can sign in to the app, not just to Clever.

A failed sync never blocks logins: the Clever-side logins still count, and the
failure is reported in the run summary.
"""
from __future__ import annotations

import os

import requests


def run_app_syncs(cfg: dict) -> list[dict]:
    results = []
    for app in cfg["logins"].get("pre_batch_sync", []):
        name = app["name"]
        url = os.environ.get(app["url_env"], "")
        secret = os.environ.get(app["secret_env"], "")
        if not url or not secret:
            results.append({"app": name, "ok": False, "skipped": True,
                            "detail": f"{app['url_env']} / {app['secret_env']} not set; skipped"})
            continue
        try:
            resp = requests.post(url, headers={"Authorization": f"Bearer {secret}"},
                                 timeout=app.get("timeout_s", 300))
            body = _json(resp)
            if resp.status_code != 200:
                err = body.get("error") if isinstance(body, dict) else resp.text[:200]
                results.append({"app": name, "ok": False, "detail": f"HTTP {resp.status_code}: {err}"})
                continue
            mode = body.get("mode", "?")
            counts = body.get("counts", {})
            res = {"app": name, "ok": True, "mode": mode, "counts": counts,
                   "warnings": body.get("warnings", [])[:5],
                   "detail": ", ".join(f"{k} {v}" for k, v in counts.items()) or "synced"}
            expect = app.get("expect_mode")
            if expect and mode != expect:
                res["ok"] = False
                res["detail"] = (f"ran in {mode!r} mode, expected {expect!r}: the app is not syncing from "
                                 f"this district (check its Clever token). {res['detail']}")
            results.append(res)
        except requests.RequestException as e:
            results.append({"app": name, "ok": False, "detail": f"{type(e).__name__}: {e}"})
    return results


def _json(resp) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}
