from collections import Counter
from datetime import date, timedelta

import pytest

from sim.config import load_config
from sim.drift import Drift, student_target, teacher_target
from sim.generate import generate
from sim.model import Roster
from sim.validate import validate


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def school_days(start: date, n: int):
    d = start
    while n:
        if d.weekday() < 5:
            yield d
            n -= 1
        d += timedelta(days=1)


def test_long_run_stays_valid_and_bounded(cfg):
    r = generate(cfg, date(2026, 11, 18))
    target_s, target_t = student_target(cfg), teacher_target(cfg)
    band_s = round(target_s * cfg["drift"]["band_pct"])
    kinds = Counter()
    for d in school_days(date(2026, 11, 19), 130):  # about six months of school days
        changes = Drift(cfg, r, d).run()
        assert changes, f"{d} produced no changes"
        kinds.update(c.kind for c in changes)
        assert validate(cfg, r) == [], d
        assert abs(len(r.students) - target_s) <= band_s + 3
        assert abs(len(r.teachers) - target_t) <= cfg["drift"]["teachers"]["band"]
        for g in r.students_in_grade("ES01", "3"), r.students_in_grade("MS01", "7"):
            assert len(g) > 5
    for k in ["student_withdrawn", "family_enrolled", "teacher_departed", "teacher_hired", "household_moved"]:
        assert kinds[k] > 0, f"never saw {k}"


def test_same_day_is_deterministic(cfg):
    a = generate(cfg, date(2026, 11, 18))
    b = Roster.from_json(a.to_json())
    d = date(2026, 11, 19)
    Drift(cfg, a, d).run()
    Drift(cfg, b, d).run()
    assert a.to_json() == b.to_json(), "a retried run must reproduce the same drift"


def test_removed_ids_never_reused(cfg):
    r = generate(cfg, date(2026, 11, 18))
    seen = set(r.students)
    removed = set()
    for d in school_days(date(2026, 11, 19), 60):
        before = set(r.students)
        Drift(cfg, r, d).run()
        removed |= before - set(r.students)
        assert not (set(r.students) & removed)
        seen |= set(r.students)


def test_teacher_departure_then_hire_fills_vacancy(cfg):
    r = generate(cfg, date(2026, 11, 18))
    for d in school_days(date(2026, 11, 19), 80):
        Drift(cfg, r, d).run()
        for role in r.vacancies:
            secs = r.sections_for_role(role)
            assert secs and all(s.teacher_id in r.teachers for s in secs), "vacant roles stay covered"
    assert len(r.vacancies) <= 2
