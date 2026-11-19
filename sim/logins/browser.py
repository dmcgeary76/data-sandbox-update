"""Headless browser sessions: log in through Clever, launch app tiles, record results.

Each user gets a fresh browser context (no shared cookies), exactly like a
different person on a different device. Failures keep a screenshot and a
Playwright trace for debugging; successes keep nothing.
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import time
from pathlib import Path

from playwright.async_api import Browser, Page, TimeoutError as PWTimeout, async_playwright


async def _first_visible(page: Page, selectors: list[str], timeout_ms: int = 10_000):
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                if await loc.is_visible():
                    return loc
            except Exception:
                pass
        await page.wait_for_timeout(250)
    raise PWTimeout(f"none of these selectors became visible: {selectors}")


async def _find_tile(page: Page, tile: str):
    candidates = [
        page.get_by_role("link", name=tile, exact=False),
        page.get_by_role("button", name=tile, exact=False),
        page.get_by_text(tile, exact=True),
        page.locator(f'[aria-label*="{tile}" i]'),
        page.locator(f'img[alt*="{tile}" i]'),
    ]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        for c in candidates:
            loc = c.first
            try:
                if await loc.is_visible():
                    return loc
            except Exception:
                pass
        await page.wait_for_timeout(300)
    raise PWTimeout(f"app tile {tile!r} not found on the portal")


async def _enabled(loc, timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            if await loc.is_enabled():
                return True
        except Exception:
            pass
        await asyncio.sleep(0.2)
    return False


async def _fill_and_submit(page: Page, field, value: str, submit_selectors: list[str]) -> None:
    """Fill a field and press the form's submit button.

    Clever's login form is a React app. A value filled in before the page finishes
    wiring up the field never reaches React, and the submit button stays disabled.
    When that happens, retype the value key by key, the way a person would.
    """
    await field.click()
    await field.fill(value)
    submit = await _first_visible(page, submit_selectors)
    if not await _enabled(submit, 2_000):
        await field.fill("")
        await field.press_sequentially(value, delay=60)
        if not await _enabled(submit, 5_000):
            raise PWTimeout("the submit button stayed disabled after entering the value")
    await submit.click()


async def login(page: Page, lc: dict, login_url: str, username: str, password: str) -> None:
    await page.goto(login_url, wait_until="domcontentloaded")
    for text in lc.get("pre_login_clicks", []):
        await page.get_by_text(text, exact=True).first.click()
    user = await _first_visible(page, lc["username_selectors"], timeout_ms=15_000)
    # Some login pages ask for the password on a second screen (Clever does: username, Next, password).
    try:
        pw = await _first_visible(page, lc["password_selectors"], timeout_ms=1_000)
        await user.fill(username)
    except PWTimeout:
        await _fill_and_submit(page, user, username, lc["submit_selectors"])
        pw = await _first_visible(page, lc["password_selectors"], timeout_ms=15_000)
    await _fill_and_submit(page, pw, password, lc["submit_selectors"])
    await page.wait_for_url(re.compile(lc["portal_url_pattern"]), timeout=30_000)
    await page.wait_for_load_state("networkidle", timeout=15_000)


def _redact(url: str) -> str:
    return re.sub(r"\b(code|state|token)=[^&]+", r"\1=…", url)[:300]


async def launch_app(page: Page, app: dict, shots: Path, tag: str) -> dict:
    """Click an app tile and confirm Clever handed the user to the app.

    Success means a navigation matching `expect_url` happened, e.g. Clever's redirect
    to the app's OAuth callback with a login code. That is checked on the requests
    themselves, so it holds even if the app's page then fails to load (for example a
    dev app whose redirect URI is localhost). Steps only run if the app page loaded.
    """
    tile = await _find_tile(page, app["tile"])
    started = time.monotonic()
    pattern = re.compile(app["expect_url"])
    seen: list[str] = []
    failed: list[str] = []

    def on_request(req):
        if req.is_navigation_request():
            seen.append(req.url)

    def on_failed(req):
        if req.is_navigation_request():
            failed.append(req.url)

    page.context.on("request", on_request)
    page.context.on("requestfailed", on_failed)
    try:
        target = page
        try:
            async with page.context.expect_page(timeout=8_000) as new_page:
                await tile.click()
            target = await new_page.value
        except PWTimeout:
            target = page  # tile opened in the same tab
        deadline = time.monotonic() + 45
        hit = None
        while time.monotonic() < deadline and not hit:
            hit = next((u for u in seen if pattern.search(u)), None) or (
                target.url if pattern.search(target.url) else None)
            if not hit:
                await asyncio.sleep(0.3)
        if not hit:
            raise PWTimeout(f"never reached {app['expect_url']!r}; last URLs: {[_redact(u) for u in seen[-3:]]}")
        try:
            await target.wait_for_load_state("domcontentloaded", timeout=15_000)
        except PWTimeout:
            pass
        await asyncio.sleep(0.5)
    finally:
        page.context.remove_listener("request", on_request)
        page.context.remove_listener("requestfailed", on_failed)

    app_loaded = not (failed and seen and failed[-1] == seen[-1]) and \
        not target.url.startswith(("chrome-error:", "about:blank"))
    if app_loaded:
        for step in app.get("steps", []):
            await run_step(target, step, shots, tag)
    result = {"app": app["key"], "ok": True, "url": _redact(hit), "app_page_loaded": app_loaded,
              "seconds": round(time.monotonic() - started, 1)}
    # Linger briefly, as a person would, then return to the portal.
    await target.wait_for_timeout(random.randint(3_000, 9_000))
    if target is not page:
        await target.close()
    else:
        await page.go_back(wait_until="domcontentloaded")
    return result


async def run_step(page: Page, step: dict, shots: Path, tag: str) -> None:
    action = step["action"]
    if action == "click_text":
        await page.get_by_text(step["text"], exact=step.get("exact", False)).first.click()
    elif action == "click_selector":
        await page.locator(step["selector"]).first.click()
    elif action == "wait_for_selector":
        await page.locator(step["selector"]).first.wait_for(timeout=step.get("timeout_ms", 20_000))
    elif action == "wait_ms":
        await page.wait_for_timeout(step["ms"])
    elif action == "screenshot":
        shots.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(shots / f"{tag}-{step.get('name', 'step')}.png"))
    else:
        raise ValueError(f"unknown step action {action!r}")


async def simulate_user(browser: Browser, cfg: dict, login_url: str, user: dict, out_dir: Path) -> dict:
    lc = cfg["logins"]
    apps = {a["key"]: a for a in cfg["apps"]}
    tag = f"{user['role']}-{user['id']}"
    ctx = await browser.new_context(viewport={"width": 1366, "height": 850}, locale="en-US",
                                    timezone_id="America/Los_Angeles")
    await ctx.tracing.start(screenshots=True, snapshots=True)
    page = await ctx.new_page()
    page.set_default_timeout(30_000)
    rec = {"id": user["id"], "role": user["role"], "launches": [], "ok": False}
    started = time.monotonic()
    try:
        async with asyncio.timeout(lc["per_user_timeout_s"]):
            # Username and password follow the district's login pattern: both are the user's ID.
            await login(page, lc, login_url, user["id"], user["id"])
            rec["login"] = "ok"
            for key in user["apps"]:
                rec["launches"].append(await launch_app(page, apps[key], out_dir / "screens", tag))
        rec["ok"] = True
        await ctx.tracing.stop()
    except Exception as e:  # keep evidence for anything that went wrong
        rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
        rec["url"] = page.url
        fail = out_dir / "failures"
        fail.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=str(fail / f"{tag}.png"), full_page=True)
        except Exception:
            pass
        await ctx.tracing.stop(path=str(fail / f"{tag}-trace.zip"))
    finally:
        rec["seconds"] = round(time.monotonic() - started, 1)
        await ctx.close()
    return rec


async def run_users(cfg: dict, login_url: str, users: list[dict], out_dir: Path, headless: bool = True) -> list[dict]:
    lc = cfg["logins"]
    sem = asyncio.Semaphore(lc["concurrency"])
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, executable_path=exe)

        async def one(i: int, u: dict) -> dict:
            async with sem:
                await asyncio.sleep(random.uniform(1, 6))  # natural spacing between logins
                r = await simulate_user(browser, cfg, login_url, u, out_dir)
                status = "ok" if r["ok"] else f"FAILED ({r.get('error')})"
                print(f"  [{i + 1}/{len(users)}] {u['role']} {u['id']} -> {', '.join(u['apps'])}: {status}", flush=True)
                return r

        results = await asyncio.gather(*(one(i, u) for i, u in enumerate(users)))
        await browser.close()
    return list(results)


async def probe(cfg: dict, login_url: str, out_dir: Path, username: str | None) -> dict:
    """Capture what the login page and portal look like, to calibrate selectors and tile names."""
    out_dir.mkdir(parents=True, exist_ok=True)
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None
    report: dict = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=exe)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 850})
        await ctx.tracing.start(screenshots=True, snapshots=True)
        page = await ctx.new_page()
        try:
            await page.goto(login_url, wait_until="networkidle")
            report["login_url_final"] = page.url
            await page.screenshot(path=str(out_dir / "1-login-page.png"), full_page=True)
            report["login_inputs"] = await page.eval_on_selector_all(
                "input", "els => els.map(e => ({name: e.name, type: e.type, id: e.id, placeholder: e.placeholder, "
                "autocomplete: e.autocomplete, visible: !!(e.offsetWidth || e.offsetHeight)}))")
            report["login_buttons"] = await page.eval_on_selector_all(
                "button, a[role=button], input[type=submit]",
                "els => els.map(e => (e.innerText || e.value || '').trim()).filter(Boolean).slice(0, 40)")
            if username:
                await login(page, cfg["logins"], login_url, username, username)
                report["portal_url"] = page.url
                await page.screenshot(path=str(out_dir / "2-portal.png"), full_page=True)
                report["portal_links"] = await page.eval_on_selector_all(
                    "a, button, [role=link], [role=button]",
                    "els => els.map(e => ((e.getAttribute('aria-label') || e.innerText || '').trim().split('\\n')[0]))"
                    ".filter(Boolean).slice(0, 80)")
        except Exception as e:
            report["error"] = f"{type(e).__name__}: {e}"
            await page.screenshot(path=str(out_dir / "error.png"), full_page=True)
        finally:
            report["final_url"] = page.url
            await ctx.tracing.stop(path=str(out_dir / "probe-trace.zip"))
            await browser.close()
    return report
