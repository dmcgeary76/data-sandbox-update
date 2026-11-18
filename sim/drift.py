"""Daily roster drift: small, realistic changes that produce Events API traffic.

Totals are mean-reverting: the further a count drifts from its target, the more
likely the next day pushes it back. Hard bands make runaway drift impossible.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

from .factory import Factory
from .model import Roster, Student, Teacher


@dataclass
class Change:
    kind: str
    summary: str
    events: list[str] = field(default_factory=list)  # Events API types we expect this to produce

    def as_dict(self) -> dict:
        return {"kind": self.kind, "summary": self.summary, "expected_events": self.events}


def student_target(cfg: dict) -> int:
    return sum(s["students_per_grade"] * len(s["grades"]) for s in cfg["schools"])


def teacher_target(cfg: dict) -> int:
    n = 0
    for s in cfg["schools"]:
        n += len(s["grades"]) if s["model"] == "elementary" else len(s["core"]) + len(s["electives"])
    return n


class Drift:
    def __init__(self, cfg: dict, roster: Roster, day: date):
        self.cfg = cfg
        self.r = roster
        self.day = day
        self.rng = random.Random(f"{cfg['seed']}:{day.isoformat()}:drift")
        self.f = Factory(cfg, roster, self.rng, day)
        self.dc = cfg["drift"]
        self.changes: list[Change] = []

    # ================================================================= entry
    def run(self) -> list[Change]:
        self.student_churn()
        self.teacher_churn()
        self.record_updates()
        self.r.last_drift_date = self.day.isoformat()
        return self.changes

    # ================================================================= students
    def plan_student_counts(self) -> tuple[int, int]:
        sc = self.dc["students"]
        target = student_target(self.cfg)
        band = max(1, round(target * self.dc["band_pct"]))
        current = len(self.r.students)
        adds = self.rng.randint(*sc["add_range"])
        removes = self.rng.randint(*sc["remove_range"])
        bias = max(-2, min(2, round((target - current) / 3)))
        if bias > 0:
            adds += bias
        elif bias < 0:
            removes += -bias
        # hard band
        while current + adds - removes > target + band and adds > 0:
            adds -= 1
        while current + adds - removes < target - band and removes > 0:
            removes -= 1
        return adds, removes

    def grade_pressure(self) -> dict[str, float]:
        """>1 means the grade is over target."""
        targets = self.f.grade_targets()
        counts = {g: 0 for g in targets}
        for s in self.r.students.values():
            counts[s.grade] = counts.get(s.grade, 0) + 1
        return {g: counts[g] / targets[g] for g in targets}

    def student_churn(self) -> None:
        adds, removes = self.plan_student_counts()
        self.remove_students(removes)
        self.add_students(adds)

    def remove_students(self, n: int) -> None:
        sc = self.dc["students"]
        while n > 0 and self.r.students:
            pressure = self.grade_pressure()
            pool = [s for s in self.r.students.values() if s.created_on != self.day.isoformat()]
            if not pool:
                return
            st = self.rng.choices(pool, weights=[pressure[s.grade] ** 4 for s in pool])[0]
            sibs = [s for s in self.r.students_in_household(st.household_id) if s.id != st.id]
            if sibs and len(sibs) + 1 <= n and self.rng.random() < sc["whole_household_withdraw_chance"]:
                group = [st] + sibs
                h = self.r.households[st.household_id]
                for s in group:
                    self._drop_student(s)
                names = ", ".join(f"{s.first} {s.last} (gr {s.grade})" for s in group)
                self.changes.append(Change(
                    "household_withdrawn", f"Family moved away: {names}",
                    ["users.deleted"] * (len(group) + len(h.guardians)) + ["sections.updated"]))
                self._drop_household_if_empty(h.id)
                n -= len(group)
            else:
                hid = st.household_id
                secs = self._drop_student(st)
                emptied = self._drop_household_if_empty(hid)
                ev = ["users.deleted"] + ["sections.updated"] * secs
                if emptied:
                    ev += ["users.deleted"] * emptied
                self.changes.append(Change("student_withdrawn",
                                           f"Withdrew {st.first} {st.last} ({st.id}, grade {st.grade}, {st.school_id})", ev))
                n -= 1

    def _drop_student(self, st: Student) -> int:
        touched = 0
        for sec in list(self.r.sections.values()):
            if st.id in sec.student_ids:
                sec.student_ids.remove(st.id)
                touched += 1
                if not sec.student_ids:
                    self._refill_section(sec)
        del self.r.students[st.id]
        return touched

    def _refill_section(self, sec) -> None:
        """Clever drops sections with no students; keep every section populated."""
        pool = [s.id for s in self.r.students_in_grade(sec.school_id, sec.grade)]
        if pool:
            sec.student_ids.append(self.rng.choice(pool))

    def _drop_household_if_empty(self, hid: str) -> int:
        if self.r.students_in_household(hid):
            return 0
        h = self.r.households.pop(hid)
        self.f.names.release(h.surname)
        return len(h.guardians)

    def pick_grade(self) -> str:
        pressure = self.grade_pressure()
        grades = list(pressure)
        return self.rng.choices(grades, weights=[(1 / max(pressure[g], 0.2)) ** 4 for g in grades])[0]

    def add_students(self, n: int) -> None:
        sc = self.dc["students"]
        while n > 0:
            grade = self.pick_grade()
            joinable = [h for h in self.r.households.values()
                        if 0 < len(self.r.students_in_household(h.id)) < 4]
            if joinable and self.rng.random() < sc["new_sibling_chance"]:
                h = self.rng.choice(joinable)
                st = self.f.new_student(h, grade)
                self.r.students[st.id] = st
                secs = self.f.enroll(st)
                kin = ", ".join(s.first for s in self.r.students_in_household(h.id) if s.id != st.id)
                self.changes.append(Change(
                    "student_enrolled", f"Enrolled {st.first} {st.last} ({st.id}, grade {grade}), sibling of {kin}",
                    ["users.created", "users.updated"] + ["sections.updated"] * len(secs)))
                n -= 1
                continue
            h = self.f.new_household()
            self.r.households[h.id] = h
            kids = [grade]
            if n >= 2 and self.rng.random() < 0.25:
                kids += self.f.sibling_grades(grade, 2)
            added = []
            for g in kids:
                st = self.f.new_student(h, g)
                self.r.students[st.id] = st
                secs = self.f.enroll(st)
                added.append((st, len(secs)))
            names = ", ".join(f"{s.first} {s.last} ({s.id}, grade {s.grade})" for s, _ in added)
            self.changes.append(Change(
                "family_enrolled",
                f"New family enrolled: {names}; guardians: {', '.join(g.full_name for g in h.guardians)}",
                ["users.created"] * (len(added) + len(h.guardians)) + ["sections.updated"] * sum(k for _, k in added)))
            n -= len(added)

    # ================================================================= teachers
    def teacher_churn(self) -> None:
        tc = self.dc["teachers"]
        if self.rng.random() >= tc["change_chance"]:
            return
        target, band = teacher_target(self.cfg), tc["band"]
        n = len(self.r.teachers)
        if n < target or (self.r.vacancies and n <= target):
            action = "add"
        elif n > target:
            action = "remove"
        else:
            action = self.rng.choice(["add", "remove"])
        if action == "add" and n + 1 > target + band:
            action = "remove"
        if action == "remove" and n - 1 < target - band:
            action = "add"
        if action == "remove" and not self.remove_teacher():
            return
        if action == "add":
            self.add_teacher()

    def removable_teachers(self) -> list[Teacher]:
        minimum = self.dc["teachers"]["min_per_school"]
        return [t for t in self.r.teachers.values()
                if len(self.r.teachers_at(t.school_id)) > minimum and t.created_on != self.day.isoformat()]

    def remove_teacher(self) -> bool:
        pool = self.removable_teachers()
        if not pool:
            return False
        interventionists = [t for t in pool if ":intervention:" in t.role_key]
        t = self.rng.choice(interventionists) if interventionists and self.rng.random() < 0.6 else self.rng.choice(pool)
        del self.r.teachers[t.id]
        events = ["users.deleted"]
        detail = ""
        if ":intervention:" in t.role_key:
            for sec in self.r.sections_for_role(t.role_key):
                del self.r.sections[sec.id]
                events.append("sections.deleted")
            detail = "their intervention section was closed"
        else:
            self.r.vacancies.append(t.role_key)
            cover = self.pick_cover(t.school_id, t.role_key)
            for sec in [s for s in self.r.sections.values() if s.teacher_id == t.id]:
                sec.teacher_id = cover.id
                events.append("sections.updated")
            detail = f"{cover.first} {cover.last} covers their sections until the position is filled"
        # Sections they covered for someone else also need a new cover.
        for sec in [s for s in self.r.sections.values() if s.teacher_id == t.id]:
            sec.teacher_id = self.pick_cover(sec.school_id, sec.role_key).id
            events.append("sections.updated")
        self.changes.append(Change("teacher_departed",
                                   f"{t.first} {t.last} ({t.title}, {t.school_id}) left; {detail}", events))
        return True

    def pick_cover(self, school_id: str, role_key: str) -> Teacher:
        kind = role_key.split(":")[1]
        pool = [t for t in self.r.teachers_at(school_id) if t.role_key.split(":")[1] == kind] or self.r.teachers_at(school_id)
        load = {t.id: 0 for t in pool}
        for s in self.r.sections.values():
            if s.teacher_id in load:
                load[s.teacher_id] += 1
        return min(pool, key=lambda t: (load[t.id], self.rng.random()))

    def add_teacher(self) -> None:
        if self.r.vacancies:
            role_key = self.r.vacancies.pop(0)
            school_id = role_key.split(":")[0]
            t = self.f.new_teacher(school_id, role_key)
            self.r.teachers[t.id] = t
            secs = self.r.sections_for_role(role_key)
            for s in secs:
                s.teacher_id = t.id
            self.changes.append(Change("teacher_hired",
                                       f"Hired {t.first} {t.last} ({t.id}) as {t.title} at {school_id}, taking over {len(secs)} sections",
                                       ["users.created"] + ["sections.updated"] * len(secs)))
            return
        counts = {s["id"]: sum(1 for t in self.r.teachers.values()
                               if t.school_id == s["id"] and ":intervention:" in t.role_key) for s in self.cfg["schools"]}
        school_id = min(counts, key=lambda k: (counts[k], self.rng.random()))
        t, sec = self.f.new_intervention(school_id)
        self.r.teachers[t.id] = t
        self.r.sections[sec.id] = sec
        self.changes.append(Change("teacher_hired",
                                   f"Hired {t.first} {t.last} ({t.id}) as {t.title} at {school_id} with a new "
                                   f"{sec.course_name} group of {len(sec.student_ids)} grade {sec.grade} students",
                                   ["users.created", "sections.created"]))

    # ================================================================= updates
    def record_updates(self) -> None:
        kinds = {
            "household_moved": 3, "guardian_contact_changed": 4, "guardian_added": 1.5,
            "emergency_contact_removed": 1, "preferred_name": 1.5, "program_status": 2.5,
            "elective_switch": 1.5, "teacher_email_changed": 0.5,
        }
        n = self.rng.randint(*self.dc["updates_range"])
        for _ in range(n):
            kind = self.rng.choices(list(kinds), weights=list(kinds.values()))[0]
            getattr(self, f"_u_{kind}")()

    def _rand_household(self):
        hs = [h for h in self.r.households.values() if self.r.students_in_household(h.id)]
        return self.rng.choice(hs)

    def _rand_student(self) -> Student:
        return self.rng.choice(list(self.r.students.values()))

    def _u_household_moved(self):
        h = self._rand_household()
        old = h.street
        h.street, _, _, h.zip = self.f.address()
        kids = self.r.students_in_household(h.id)
        self.changes.append(Change("household_moved", f"{h.surname} family moved from {old} to {h.street}, {h.zip}",
                                   ["users.updated"] * len(kids)))

    def _u_guardian_contact_changed(self):
        h = self._rand_household()
        g = self.rng.choice(h.guardians)
        if self.rng.random() < 0.6:
            g.phone, what = self.f.phone(), "phone"
        else:
            g.email, what = self.f.guardian_email(g.first, g.last), "email"
        self.changes.append(Change("guardian_contact_changed", f"{g.full_name} updated their {what}", ["users.updated"]))

    def _u_guardian_added(self):
        h = self._rand_household()
        if len(h.guardians) >= 4:
            return self._u_guardian_contact_changed()
        g = self.f.extra_contact(h)
        h.guardians.append(g)
        self.changes.append(Change("guardian_added", f"Added {g.relationship.lower()} {g.full_name} as an "
                                   f"{g.type.lower()} contact for the {h.surname} family", ["users.created"]))

    def _u_emergency_contact_removed(self):
        hs = [h for h in self.r.households.values()
              if any(g.type == "Emergency" for g in h.guardians) and self.r.students_in_household(h.id)]
        if not hs:
            return self._u_guardian_added()
        h = self.rng.choice(hs)
        g = next(g for g in h.guardians if g.type == "Emergency")
        h.guardians.remove(g)
        self.changes.append(Change("emergency_contact_removed",
                                   f"Removed emergency contact {g.full_name} from the {h.surname} family", ["users.deleted"]))

    def _u_preferred_name(self):
        from .factory import NICKNAMES
        cands = [s for s in self.r.students.values() if s.first in NICKNAMES or s.preferred_first]
        if not cands:
            return self._u_program_status()
        s = self.rng.choice(cands)
        if s.preferred_first:
            old, s.preferred_first = s.preferred_first, ""
            msg = f"{s.first} {s.last} no longer goes by {old}"
        else:
            s.preferred_first = NICKNAMES[s.first]
            msg = f"{s.first} {s.last} now goes by {s.preferred_first}"
        self.changes.append(Change("preferred_name", msg, ["users.updated"]))

    def _u_program_status(self):
        s = self._rand_student()
        opts = []
        if s.ell == "Y":
            opts.append(("ell", "N", "reclassified as English proficient"))
        opts.append(("iep", "N" if s.iep == "Y" else "Y", "IEP " + ("exited" if s.iep == "Y" else "started")))
        opts.append(("frl", self.rng.choice([x for x in "FRN" if x != s.frl]), "lunch status changed"))
        field_, val, msg = self.rng.choice(opts)
        setattr(s, field_, val)
        self.changes.append(Change("program_status", f"{s.first} {s.last}: {msg}", ["users.updated"]))

    def _u_elective_switch(self):
        electives = {c["code"] for sc in self.cfg["schools"] for c in sc.get("electives", [])}
        movers = [(s, sec) for s in self.r.students.values() for sec in self.r.sections_for_student(s.id)
                  if sec.course_code in electives and len(sec.student_ids) > 1]
        if not movers:
            return self._u_program_status()
        st, frm = self.rng.choice(movers)
        to = [x for x in self.r.sections.values() if x.school_id == frm.school_id and x.grade == frm.grade
              and x.course_code in electives and x.id != frm.id]
        if not to:
            return self._u_program_status()
        dest = self.rng.choice(to)
        frm.student_ids.remove(st.id)
        dest.student_ids.append(st.id)
        self.changes.append(Change("elective_switch", f"{st.first} {st.last} switched from {frm.course_name} to {dest.course_name}",
                                   ["sections.updated", "sections.updated"]))

    def _u_teacher_email_changed(self):
        from .factory import ascii_slug
        t = self.rng.choice(list(self.r.teachers.values()))
        new = f"{ascii_slug(t.first)[0]}{ascii_slug(t.last)}@{self.cfg['district']['staff_email_domain']}"
        if new == t.email or new in {x.email for x in self.r.teachers.values()}:
            return self._u_guardian_contact_changed()
        t.email = new
        self.changes.append(Change("teacher_email_changed", f"{t.first} {t.last}'s email changed to {t.email}", ["users.updated"]))
