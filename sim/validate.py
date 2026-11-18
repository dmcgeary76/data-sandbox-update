"""Integrity checks. Uploads are refused if any of these fail."""
from __future__ import annotations

from collections import Counter

from .model import Roster


def validate(cfg: dict, r: Roster) -> list[str]:
    errs: list[str] = []
    school_ids = {s["id"] for s in cfg["schools"]}
    grades_by_school = {s["id"]: set(s["grades"]) for s in cfg["schools"]}

    # ids unique across users (Clever requires unique sis ids per type; we keep them globally unique)
    ids = list(r.students) + list(r.teachers)
    for i, n in Counter(ids).items():
        if n > 1:
            errs.append(f"duplicate user id {i}")

    for st in r.students.values():
        if st.school_id not in school_ids:
            errs.append(f"student {st.id} has unknown school {st.school_id}")
        elif st.grade not in grades_by_school[st.school_id]:
            errs.append(f"student {st.id} grade {st.grade} not served by {st.school_id}")
        if st.household_id not in r.households:
            errs.append(f"student {st.id} has missing household {st.household_id}")
        elif not r.households[st.household_id].guardians:
            errs.append(f"student {st.id} has no guardian contacts")
        if not r.sections_for_student(st.id):
            errs.append(f"student {st.id} is not enrolled in any section")

    for t in r.teachers.values():
        if t.school_id not in school_ids:
            errs.append(f"teacher {t.id} has unknown school {t.school_id}")

    for sec in r.sections.values():
        if sec.teacher_id not in r.teachers:
            errs.append(f"section {sec.id} has missing teacher {sec.teacher_id}")
        if not sec.student_ids:
            errs.append(f"section {sec.id} has no students (Clever would drop it)")
        for sid in sec.student_ids:
            if sid not in r.students:
                errs.append(f"section {sec.id} enrolls missing student {sid}")
        if len(set(sec.student_ids)) != len(sec.student_ids):
            errs.append(f"section {sec.id} has duplicate enrollments")

    for h in r.households.values():
        if not r.students_in_household(h.id):
            errs.append(f"household {h.id} has no students")

    contact_ids = Counter(g.id for h in r.households.values() for g in h.guardians)
    for cid, n in contact_ids.items():
        if n > 1:
            errs.append(f"contact id {cid} used in {n} households")

    emails = Counter(t.email for t in r.teachers.values())
    for e, n in emails.items():
        if n > 1:
            errs.append(f"duplicate teacher email {e}")
    return errs
