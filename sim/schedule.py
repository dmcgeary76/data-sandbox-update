"""Pacific-time scheduling guards.

GitHub cron only speaks UTC, and DST moves Pacific time by an hour twice a year.
The workflows fire at both possible UTC hours; these guards decide whether work
is actually due, and the state files make every job idempotent.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")


def now_pt(override: str | None = None) -> datetime:
    if override:
        dt = datetime.fromisoformat(override)
        return dt.replace(tzinfo=PT) if dt.tzinfo is None else dt.astimezone(PT)
    return datetime.now(timezone.utc).astimezone(PT)


def is_school_day(d: date, days: str) -> bool:
    return days == "daily" or d.weekday() < 5


def drift_due(cfg: dict, now: datetime, last_drift_date: str) -> tuple[bool, str]:
    dc = cfg["drift"]
    today = now.date()
    if not is_school_day(today, dc["days"]):
        return False, f"{today} is not a drift day ({dc['days']})"
    if now.hour < dc["run_hour_pt"]:
        return False, f"too early: {now:%H:%M} PT, drift runs from {dc['run_hour_pt']}:00 PT"
    if last_drift_date == today.isoformat():
        return False, f"drift already applied for {today}"
    return True, f"drift due for {today}"


def due_login_batches(cfg: dict, now: datetime, done: set[int]) -> list[int]:
    """Indexes of batches whose hour has arrived and that haven't run yet (catch-up included)."""
    lc = cfg["logins"]
    if not is_school_day(now.date(), lc["days"]):
        return []
    return [i for i, h in enumerate(lc["batch_hours_pt"]) if now.hour >= h and i not in done]
