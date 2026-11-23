from datetime import date

from sim.config import load_config
from sim.generate import generate
from sim.logins.plan import build_plan
from sim.schedule import drift_due, due_login_batches, now_pt

cfg = load_config()


def _enabled():
    import copy
    c = copy.deepcopy(cfg)
    c["logins"]["enabled"] = True
    return c


def test_drift_guard():
    assert drift_due(cfg, now_pt("2026-11-18T04:59"), "")[0] is False
    assert drift_due(cfg, now_pt("2026-11-18T05:00"), "")[0] is True
    assert drift_due(cfg, now_pt("2026-11-18T06:30"), "2026-11-18")[0] is False
    assert drift_due(cfg, now_pt("2026-11-21T09:00"), "")[0] is False  # Saturday


def test_dst_both_utc_triggers_resolve_to_one_run():
    # 12:00 UTC and 13:00 UTC both fire; in PST only 13:00 is 5am, in PDT 12:00 is 5am.
    assert drift_due(cfg, now_pt("2026-12-02T12:00:00+00:00"), "")[0] is False  # 4am PST
    assert drift_due(cfg, now_pt("2026-12-02T13:00:00+00:00"), "")[0] is True   # 5am PST
    assert drift_due(cfg, now_pt("2026-06-02T12:00:00+00:00"), "")[0] is True   # 5am PDT


def test_login_pause_switch():
    import copy
    paused = copy.deepcopy(cfg)
    paused["logins"]["enabled"] = False
    assert due_login_batches(paused, now_pt("2026-11-18T15:00"), set()) == []


def test_login_catch_up():
    cfg = _enabled()
    assert due_login_batches(cfg, now_pt("2026-11-18T07:59"), set()) == []
    assert due_login_batches(cfg, now_pt("2026-11-18T08:05"), set()) == [0]
    assert due_login_batches(cfg, now_pt("2026-11-18T11:30"), {0}) == [1]
    assert due_login_batches(cfg, now_pt("2026-11-18T15:00"), set()) == [0, 1, 2, 3]
    assert due_login_batches(cfg, now_pt("2026-11-22T10:00"), set()) == []  # Sunday


def test_plan_fraction_and_eligibility():
    r = generate(cfg, date(2026, 11, 10))
    newest = sorted(r.students.values(), key=lambda s: s.id)[0]
    newest.created_on = "2026-11-18"
    p = build_plan(cfg, r, date(2026, 11, 18))
    students = [u for u in p["users"] if u["role"] == "student"]
    lo, hi = cfg["logins"]["student_fraction"]
    assert lo * (len(r.students) - 1) - 1 <= len(students) <= hi * len(r.students) + 1
    assert newest.id not in {u["id"] for u in p["users"]}, "brand-new students wait a day"
    assert build_plan(cfg, r, date(2026, 11, 18)) == p
    assert {u["batch"] for u in p["users"]} == {0, 1, 2, 3}


def test_batches_skip_users_removed_after_planning():
    from sim.logins.plan import still_enrolled
    r = generate(cfg, date(2026, 11, 10))
    p = build_plan(cfg, r, date(2026, 11, 18))
    victim = next(u for u in p["users"] if u["role"] == "student")
    del r.students[victim["id"]]
    keep, gone = still_enrolled(p["users"], r)
    assert gone == [victim]
    assert len(keep) == len(p["users"]) - 1
