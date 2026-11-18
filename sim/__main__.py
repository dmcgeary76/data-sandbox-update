"""Command line entry point: `python -m sim <command>`. Run `python -m sim -h` for help."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timezone

from .config import ARTIFACT_DIR, BUILD_DIR, STATE_DIR, Secrets, load_config
from .model import Roster

ROSTER = STATE_DIR / "roster.json"
CURSOR = STATE_DIR / "events_cursor.json"


# ------------------------------------------------------------------ helpers
def summary(md: str) -> None:
    """Print, and also add to the GitHub Actions run page when running in CI."""
    print(md)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(md + "\n")


def load_roster() -> Roster:
    if not ROSTER.exists():
        sys.exit("No state/roster.json yet. Run `python -m sim init` (or the Bootstrap workflow) first.")
    return Roster.load(ROSTER)


def check(cfg: dict, r: Roster) -> None:
    from .validate import validate
    errs = validate(cfg, r)
    if errs:
        sys.exit("Roster failed validation, refusing to continue:\n  " + "\n  ".join(errs[:30]))


def render_files(cfg: dict, r: Roster):
    from .csvwriter import render, write
    return write(render(cfg, r), BUILD_DIR)


def upload(cfg: dict, r: Roster, paths) -> None:
    from .clever import sftp_upload, verify_sandbox_district
    sec = Secrets.from_env()
    d = verify_sandbox_district(cfg, sec)
    print(f"Verified sandbox district: {d.get('name')} ({d.get('id')})")
    sftp_upload(sec, paths, last_upload_at=r.last_upload_at)
    r.last_upload_at = datetime.now(timezone.utc).isoformat(timespec="seconds")


def counts_line(r: Roster) -> str:
    return (f"{len(r.students)} students, {len(r.teachers)} teachers, {len(r.sections)} sections, "
            f"{sum(len(h.guardians) for h in r.households.values())} contacts in {len(r.households)} families")


def write_changelog(day: date, changes: list, r: Roster, title: str) -> None:
    d = STATE_DIR / "changelog"
    d.mkdir(parents=True, exist_ok=True)
    expected = Counter(e for c in changes for e in c.events)
    (d / f"{day.isoformat()}.json").write_text(json.dumps({
        "date": day.isoformat(), "title": title, "totals": counts_line(r),
        "expected_events": dict(sorted(expected.items())), "changes": [c.as_dict() for c in changes],
    }, indent=1, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ commands
def cmd_init(a, cfg):
    from .generate import generate
    from .schedule import now_pt
    if ROSTER.exists() and not a.force:
        sys.exit("state/roster.json already exists. The district has been loaded; use --force only to start over.")
    today = date.fromisoformat(a.date) if a.date else now_pt().date()
    r = generate(cfg, today)
    r.last_drift_date = today.isoformat()  # the first load counts as today's change
    check(cfg, r)
    paths = render_files(cfg, r)
    if a.dry_run:
        summary(f"### Dry run: initial load\n{counts_line(r)}\nFiles written to `build/` (not uploaded).")
        return
    upload(cfg, r, paths)
    r.save(ROSTER)
    from .drift import Change
    write_changelog(today, [Change("initial_load", counts_line(r), ["users.created", "sections.created"])], r,
                    "Initial load")
    summary(f"### Initial load uploaded\n{counts_line(r)}")


def cmd_daily(a, cfg):
    """The scheduled drift job: report yesterday's events, apply today's drift, upload."""
    from .drift import Drift
    from .schedule import drift_due, now_pt
    r = load_roster()
    now = now_pt(a.now)
    due, why = drift_due(cfg, now, r.last_drift_date)
    if not due and not a.force:
        print(f"Nothing to do: {why}")
        return
    day = now.date()
    sec = Secrets.from_env()

    if not a.dry_run and sec.district_token:
        from .clever import events_report
        try:
            rep = events_report(sec, CURSOR)
            write_events(day, rep)
        except Exception as e:  # reporting must never block the drift
            summary(f"> Events report skipped: {type(e).__name__}: {e}")

    changes = Drift(cfg, r, day).run()
    check(cfg, r)
    paths = render_files(cfg, r)
    lines = [f"### Roster drift for {day} {'(dry run)' if a.dry_run else ''}", counts_line(r), ""]
    lines += [f"- **{c.kind}**: {c.summary}" for c in changes]
    exp = Counter(e for c in changes for e in c.events)
    lines += ["", "Expected events: " + ", ".join(f"{k} ×{v}" for k, v in sorted(exp.items()))]
    if a.dry_run:
        summary("\n".join(lines))
        return
    upload(cfg, r, paths)
    r.save(ROSTER)
    write_changelog(day, changes, r, "Daily drift")
    summary("\n".join(lines))


def write_events(day: date, rep: dict) -> None:
    d = STATE_DIR / "events"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{day.isoformat()}.json").write_text(json.dumps(rep, indent=1) + "\n")
    if rep.get("baseline"):
        summary("### Events API\nFirst run: recorded a starting cursor. Counts begin with the next run.")
    else:
        rows = "\n".join(f"| {k} | {v} |" for k, v in rep["counts"].items()) or "| (none) | 0 |"
        summary(f"### Events API since last run\n{rep['total']} events\n\n| type | count |\n|---|---|\n{rows}")


def cmd_events(a, cfg):
    from .clever import events_report, verify_sandbox_district
    sec = Secrets.from_env()
    verify_sandbox_district(cfg, sec)
    from .schedule import now_pt
    write_events(now_pt().date(), events_report(sec, CURSOR))


def cmd_render(a, cfg):
    r = load_roster()
    check(cfg, r)
    for p in render_files(cfg, r):
        print(p)


def cmd_validate(a, cfg):
    r = load_roster()
    check(cfg, r)
    print("OK:", counts_line(r))


def cmd_upload(a, cfg):
    r = load_roster()
    check(cfg, r)
    upload(cfg, r, render_files(cfg, r))
    r.save(ROSTER)
    summary(f"### Re-uploaded current roster\n{counts_line(r)}")


def cmd_plan(a, cfg):
    from .logins.plan import build_plan
    from .schedule import now_pt
    day = date.fromisoformat(a.date) if a.date else now_pt().date()
    plan = build_plan(cfg, load_roster(), day)
    by = Counter((u["batch"], u["role"]) for u in plan["users"])
    print(f"{day}: {len(plan['users'])} users "
          f"(eligible {plan['eligible_students']} students / {plan['eligible_teachers']} teachers)")
    for i, h in enumerate(cfg["logins"]["batch_hours_pt"]):
        print(f"  batch {i} @ {h}:00 PT: {by[(i, 'student')]} students, {by[(i, 'teacher')]} teachers")


def cmd_logins(a, cfg):
    from .logins.plan import completed_batches, load_or_create_plan, run_dir
    from .schedule import due_login_batches, now_pt
    r = load_roster()
    now = now_pt(a.now)
    day = now.date()
    done = completed_batches(STATE_DIR, day)
    if a.batch is not None:
        batches = [a.batch]
    else:
        batches = due_login_batches(cfg, now, done)
    if not batches and not cfg["logins"].get("enabled", True):
        print("Scheduled logins are paused (logins.enabled: false in config/sandbox.yaml). "
              "Use --batch N to run a test batch anyway.")
        return
    if not batches:
        print(f"No login batch due at {now:%a %H:%M} PT (done today: {sorted(done) or 'none'}).")
        return
    plan = load_or_create_plan(cfg, r, day, STATE_DIR, save=not a.dry_run)
    sec = Secrets.from_env()
    for b in batches:
        users = [u for u in plan["users"] if u["batch"] == b]
        if a.limit:
            users = users[: a.limit]
        print(f"Batch {b}: {len(users)} users")
        if a.dry_run:
            for u in users:
                print(f"  {u['role']} {u['id']} ({u['name']}) -> {', '.join(u['apps'])}")
            continue
        sec.require("login_url")
        from .logins.browser import run_users
        out = ARTIFACT_DIR / day.isoformat() / f"batch-{b}"
        results = asyncio.run(run_users(cfg, sec.login_url, users, out, headless=not a.headed))
        ok = sum(1 for x in results if x["ok"])
        launches = Counter(l["app"] for x in results for l in x["launches"])
        record = {"date": day.isoformat(), "batch": b, "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "users": len(results), "succeeded": ok, "launches": dict(launches),
                  "failures": [{k: x.get(k) for k in ("id", "role", "error", "url")} for x in results if not x["ok"]]}
        d = run_dir(STATE_DIR, day)
        d.mkdir(parents=True, exist_ok=True)
        # Manual or limited runs are tests: record them, but don't mark the scheduled batch as done.
        manual = a.batch is not None or a.limit
        name = f"manual-{datetime.now(timezone.utc):%H%M%S}-batch{b}.json" if manual else f"batch-{b}.json"
        (d / name).write_text(json.dumps(record, indent=1) + "\n")
        fails = "\n".join(f"- {f['role']} {f['id']}: {f['error']}" for f in record["failures"][:15])
        summary(f"### Logins {day} batch {b}\n{ok}/{len(results)} users logged in and launched apps. "
                f"Launches: {dict(launches)}\n{fails}")
        if results and ok == 0:
            sys.exit("Every login in this batch failed. See the uploaded artifacts for screenshots and traces.")


def cmd_logins_due(a, cfg):
    """Cheap check used by the workflow before installing a browser."""
    from .logins.plan import completed_batches
    from .schedule import due_login_batches, now_pt
    now = now_pt(a.now)
    due = due_login_batches(cfg, now, completed_batches(STATE_DIR, now.date()))
    if not cfg["logins"].get("enabled", True):
        print("Scheduled logins are paused (logins.enabled: false in config/sandbox.yaml).")
    print(f"{now:%a %H:%M} PT, due batches: {due or 'none'}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"due={'true' if due else 'false'}\n")


def cmd_probe(a, cfg):
    from .logins.browser import probe
    sec = Secrets.from_env()
    sec.require("login_url")
    username = a.username
    if not username and ROSTER.exists():
        r = Roster.load(ROSTER)
        username = sorted(s.id for s in r.students.values())[0] if r.students else None
    rep = asyncio.run(probe(cfg, sec.login_url, ARTIFACT_DIR / "probe", username))
    summary("### Login probe\n```json\n" + json.dumps(rep, indent=1) + "\n```")


def cmd_status(a, cfg):
    r = load_roster()
    print(counts_line(r))
    print(f"last drift: {r.last_drift_date or 'never'}; last upload: {r.last_upload_at or 'never'}; "
          f"open teaching vacancies: {len(r.vacancies)}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m sim", description="Clever sandbox activity simulator")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="generate the district and do the first upload")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--date")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("daily", help="scheduled job: events report, drift, upload")
    s.add_argument("--force", action="store_true", help="ignore the time-of-day/weekday/already-ran guard")
    s.add_argument("--dry-run", action="store_true", help="compute and print, but do not upload or save")
    s.add_argument("--now", help="pretend it is this Pacific time (ISO), for testing")
    s.set_defaults(fn=cmd_daily)

    s = sub.add_parser("logins", help="run due login batches")
    s.add_argument("--batch", type=int, help="run this batch regardless of schedule")
    s.add_argument("--limit", type=int, help="cap users per batch (testing)")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--headed", action="store_true")
    s.add_argument("--now")
    s.set_defaults(fn=cmd_logins)

    s = sub.add_parser("logins-due", help="print whether a login batch is due (sets a GitHub output)")
    s.add_argument("--now")
    s.set_defaults(fn=cmd_logins_due)

    s = sub.add_parser("plan", help="show who would log in on a date")
    s.add_argument("--date")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("probe", help="screenshot the login page/portal to calibrate selectors")
    s.add_argument("--username")
    s.set_defaults(fn=cmd_probe)

    for name, fn, h in [("events", cmd_events, "report Events API activity since last run"),
                        ("render", cmd_render, "write the CSVs to build/"),
                        ("validate", cmd_validate, "check roster integrity"),
                        ("upload", cmd_upload, "re-upload the current roster (no drift)"),
                        ("status", cmd_status, "print roster totals")]:
        sub.add_parser(name, help=h).set_defaults(fn=fn)

    a = p.parse_args(argv)
    a.fn(a, load_config())


if __name__ == "__main__":
    main()
