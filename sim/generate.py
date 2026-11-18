"""First load: builds the whole district from scratch."""
from __future__ import annotations

import random
from datetime import date

from .factory import Factory, grade_code
from .model import Roster


def generate(cfg: dict, today: date) -> Roster:
    roster = Roster(seed=cfg["seed"])
    rng = random.Random(f"{cfg['seed']}:init")
    f = Factory(cfg, roster, rng, today)

    # 1. Teachers and their (still empty) sections.
    for school in cfg["schools"]:
        sid = school["id"]
        if school["model"] == "elementary":
            for grade in school["grades"]:
                role = f"{sid}:homeroom:{grade}"
                t = f.new_teacher(sid, role)
                roster.teachers[t.id] = t
                for c in school["courses"]:
                    sec = f.section(f"{sid}-{c['code']}-{grade_code(grade)}", sid, role, t.id,
                                    c["code"], c["name"], c["subject"], grade, c["period"])
                    roster.sections[sec.id] = sec
        elif school["model"] == "departmental":
            courses = school["core"] + school["electives"]
            for ci, c in enumerate(courses):
                role = f"{sid}:subject:{c['code']}"
                t = f.new_teacher(sid, role)
                roster.teachers[t.id] = t
                for gi, grade in enumerate(school["grades"]):
                    period = str(1 + (ci + gi) % 6) if c in school["core"] else str(5 + gi % 2)
                    sec = f.section(f"{sid}-{c['code']}-{grade}", sid, role, t.id,
                                    c["code"], c["name"], c["subject"], grade, period)
                    roster.sections[sec.id] = sec
        else:
            raise ValueError(f"unknown school model {school['model']!r}")

    # 2. Families until every grade reaches its target.
    targets = f.grade_targets()

    def counts() -> dict[str, int]:
        c = {g: 0 for g in targets}
        for s in roster.students.values():
            c[s.grade] += 1
        return c

    while True:
        c = counts()
        need = {g: targets[g] - c[g] for g in targets if c[g] < targets[g]}
        if not need:
            break
        first_grade = max(need, key=lambda g: (need[g], rng.random()))
        h = f.new_household()
        roster.households[h.id] = h
        grades = [first_grade] + f.sibling_grades(first_grade, f.sibling_count())
        for g in grades:
            if g != first_grade and counts()[g] >= targets[g]:
                continue  # sibling's grade is already full
            st = f.new_student(h, g)
            roster.students[st.id] = st
            f.enroll(st)

    return roster
