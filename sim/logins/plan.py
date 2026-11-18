"""Decide who logs in today, into which apps, and in which batch.

The plan is deterministic for a given date (seeded), and the first batch of the
day saves it to state/runs/<date>/plan.json so every later batch uses the same plan
even if the roster changed in between.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from ..model import Roster


def build_plan(cfg: dict, roster: Roster, day: date) -> dict:
    lc = cfg["logins"]
    rng = random.Random(f"{cfg['seed']}:{day.isoformat()}:logins")
    cutoff = (day - timedelta(days=lc["min_age_days"])).isoformat()
    apps = cfg["apps"]

    def pick_apps() -> list[str]:
        first = rng.choices(apps, weights=[a.get("weight", 1) for a in apps])[0]
        chosen = [first["key"]]
        others = [a for a in apps if a["key"] != first["key"]]
        if others and rng.random() < lc["second_app_chance"]:
            chosen.append(rng.choices(others, weights=[a.get("weight", 1) for a in others])[0]["key"])
        return chosen

    users = []
    students = sorted((s for s in roster.students.values() if s.created_on <= cutoff), key=lambda s: s.id)
    teachers = sorted((t for t in roster.teachers.values() if t.created_on <= cutoff), key=lambda t: t.id)
    n_s = round(len(students) * rng.uniform(*lc["student_fraction"]))
    n_t = round(len(teachers) * rng.uniform(*lc["teacher_fraction"]))
    for s in rng.sample(students, n_s):
        users.append({"id": s.id, "role": "student", "name": f"{s.first} {s.last}", "school": s.school_id,
                      "apps": pick_apps()})
    for t in rng.sample(teachers, n_t):
        users.append({"id": t.id, "role": "teacher", "name": f"{t.first} {t.last}", "school": t.school_id,
                      "apps": pick_apps()})
    rng.shuffle(users)
    nb = len(lc["batch_hours_pt"])
    for u in users:
        u["batch"] = rng.choices(range(nb), weights=lc["batch_weights"])[0]
    return {"date": day.isoformat(), "eligible_students": len(students), "eligible_teachers": len(teachers),
            "users": users}


def run_dir(state_dir: Path, day: date) -> Path:
    return state_dir / "runs" / day.isoformat()


def load_or_create_plan(cfg: dict, roster: Roster, day: date, state_dir: Path, save: bool = True) -> dict:
    p = run_dir(state_dir, day) / "plan.json"
    if p.exists():
        return json.loads(p.read_text())
    plan = build_plan(cfg, roster, day)
    if save:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(plan, indent=1) + "\n")
    return plan


def completed_batches(state_dir: Path, day: date) -> set[int]:
    d = run_dir(state_dir, day)
    return {int(p.stem.split("-")[1]) for p in d.glob("batch-*.json")} if d.exists() else set()
