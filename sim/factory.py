"""Builds roster records: households with guardians, students, teachers, sections.

Used by both the first load (generate.py) and the daily drift (drift.py), so
students added later look exactly like the original ones.
"""
from __future__ import annotations

import random
import unicodedata
from datetime import date, timedelta

from .model import Guardian, Household, Roster, Section, Student, Teacher
from .names import ASIAN_SURNAMES, NameBank

GRADE_NUM = {"Kindergarten": 0, **{str(i): i for i in range(1, 13)}}

NICKNAMES = {
    "Alexander": "Alex", "Benjamin": "Ben", "Christopher": "Chris", "Daniel": "Danny", "Elizabeth": "Liz",
    "Gabriel": "Gabe", "Jonathan": "Jon", "Joseph": "Joey", "Matthew": "Matt", "Michael": "Mikey",
    "Nicholas": "Nick", "Samuel": "Sam", "Theodore": "Teddy", "William": "Will", "Abigail": "Abby",
    "Isabella": "Bella", "Natalie": "Nat", "Samantha": "Sam", "Victoria": "Tori", "Valentina": "Vale",
    "Santiago": "Santi", "Alejandro": "Alex", "Leonardo": "Leo", "Emiliano": "Emi", "Gabriela": "Gabby",
    "Madeline": "Maddie", "Madison": "Maddie", "Penelope": "Penny", "Eleanor": "Nora", "Jacob": "Jake",
}

VIETNAMESE = {"Nguyen", "Tran", "Le", "Pham", "Huynh", "Vo", "Dang", "Bui"}
KOREAN = {"Kim", "Lee", "Park", "Choi", "Jung", "Kang"}
CHINESE = {"Chen", "Wang", "Li", "Zhang", "Liu", "Wong", "Chan", "Huang", "Lin", "Wu", "Yang", "Lam", "Ng"}
SOUTH_ASIAN = {"Patel", "Shah", "Singh", "Kumar", "Reddy", "Gupta", "Rao", "Sharma"}
FILIPINO = {"Santos", "Dela Cruz", "Bautista", "Villanueva", "Mendoza", "Aquino"}
JAPANESE = {"Tanaka", "Nakamura", "Yamamoto", "Sato"}

TEACHER_GROUPS = {"white": 0.58, "hispanic": 0.22, "asian": 0.10, "black": 0.06, "multiracial": 0.04}


def ascii_slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def grade_code(grade: str) -> str:
    return "K" if grade == "Kindergarten" else grade


class Factory:
    def __init__(self, cfg: dict, roster: Roster, rng: random.Random, today: date):
        self.cfg = cfg
        self.roster = roster
        self.rng = rng
        self.today = today
        self.names = NameBank(rng)
        self.names.load_existing([h.surname for h in roster.households.values()])
        self.d = cfg["district"]
        self.term_start = date.fromisoformat(cfg["term"]["start"])
        self.schools = {s["id"]: s for s in cfg["schools"]}

    # ------------------------------------------------------------------ ids
    def _unique(self, make) -> str:
        used = set(self.roster.used_ids)
        for _ in range(10_000):
            v = make()
            if v not in used:
                self.roster.used_ids.append(v)
                return v
        raise RuntimeError("could not find a free id")

    def student_id(self) -> str:
        return self._unique(lambda: str(self.rng.randint(300000, 699999)))

    def teacher_id(self) -> str:
        return self._unique(lambda: str(self.rng.randint(70000, 89999)))

    def contact_id(self) -> str:
        return self._unique(lambda: f"C{self.rng.randint(100000, 999999)}")

    def counter(self, name: str) -> int:
        n = self.roster.counters.get(name, 0) + 1
        self.roster.counters[name] = n
        return n

    # ------------------------------------------------------------------ helpers
    def group(self, weights: dict | None = None) -> str:
        w = weights or self.cfg["demographics"]
        return self.rng.choices(list(w), weights=list(w.values()))[0]

    def phone(self) -> str:
        # 555-01XX is the range reserved for fictional use.
        area = self.rng.choice(self.d["phone_area_codes"])
        return f"{area}55501{self.rng.randint(0, 99):02d}"

    def guardian_email(self, first: str, last: str) -> str:
        r = self.rng.random()
        f, l = ascii_slug(first), ascii_slug(last)
        local = f"{f}.{l}" if r < 0.4 else f"{f}{l}{self.rng.randint(1, 99)}" if r < 0.8 else f"{f[0]}{l}{self.rng.randint(70, 99)}"
        return f"{local}@{self.rng.choice(self.d['guardian_email_domains'])}"

    def home_language(self, group: str, surname: str) -> str:
        r = self.rng.random()
        if group == "hispanic":
            return "Spanish" if r < 0.55 else "English"
        if group == "asian":
            if surname in VIETNAMESE:
                return "Vietnamese" if r < 0.45 else "English"
            if surname in CHINESE:
                return self.rng.choice(["Chinese", "Cantonese"]) if r < 0.40 else "English"
            if surname in KOREAN:
                return "Korean" if r < 0.35 else "English"
            if surname in SOUTH_ASIAN:
                return self.rng.choice(["Punjabi", "Hindi", "Telugu", "Gujarati"]) if r < 0.30 else "English"
            if surname in FILIPINO:
                return "Tagalog" if r < 0.20 else "English"
            if surname in JAPANESE:
                return "Japanese" if r < 0.15 else "English"
        return "English"

    def address(self) -> tuple[str, str, str, str]:
        num = self.rng.randint(100, 9899)
        street = self.rng.choice([
            "Oak", "Maple", "Cedar", "Pine", "Walnut", "Sycamore", "Madrone", "Redwood", "Laurel", "Willow",
            "Vineyard", "Sonoma", "Mission", "Valley View", "Hillcrest", "Orchard", "Meadow", "Creekside",
            "Brookwood", "Sunset", "Del Monte", "Alameda", "Las Palmas", "Fairview", "Elm", "Juniper",
        ])
        suffix = self.rng.choice(["St", "Ave", "Dr", "Ct", "Ln", "Way", "Pl", "Cir"])
        unit = f" Apt {self.rng.randint(1, 40)}" if self.rng.random() < 0.18 else ""
        return f"{num} {street} {suffix}{unit}", self.d["city"], self.d["state"], self.rng.choice(self.d["zips"])

    # ------------------------------------------------------------------ households
    def new_guardian(self, group: str, first_female: bool, last: str, relationship: str, ctype: str) -> Guardian:
        first = self.names.adult_first(group, first_female)
        return Guardian(
            id=self.contact_id(), first=first, last=last, relationship=relationship, type=ctype,
            phone=self.phone(), phone_type=self.rng.choices(["Cell", "Home", "Work"], [0.82, 0.12, 0.06])[0],
            email=self.guardian_email(first, last) if self.rng.random() < 0.92 else "",
        )

    def new_household(self, group: str | None = None) -> Household:
        rng = self.rng
        group = group or self.group()
        surname = self.names.surname(group)
        street, city, state, zip_ = self.address()
        h = Household(
            id=f"H{self.counter('household'):05d}", group=group, surname=surname,
            street=street, city=city, state=state, zip=zip_,
            home_language=self.home_language(group, surname),
        )
        other_group = group if rng.random() < 0.85 else self.group()
        r = rng.random()
        mother_keeps_name = 0.30 if group == "hispanic" else 0.12
        if r < 0.78:  # two-parent household
            same_gender = rng.random() < 0.04
            mother_first = rng.random() < 0.7
            mother_last = surname
            if rng.random() < mother_keeps_name:
                mother_last = self.names.surname(other_group, claim=False)
            p1 = self.new_guardian(group, True, mother_last, "Parent", "Parent/Guardian")
            p2 = self.new_guardian(other_group, same_gender, surname, "Parent", "Parent/Guardian")
            h.guardians = [p1, p2] if mother_first else [p2, p1]
        elif r < 0.92:  # single parent, same surname
            h.guardians = [self.new_guardian(group, rng.random() < 0.8, surname, "Parent", "Parent/Guardian")]
        else:  # single guardian with a different surname
            rel = rng.choices(["Parent", "Grandparent", "Aunt/Uncle", "Other"], [0.45, 0.30, 0.18, 0.07])[0]
            last = self.names.surname(other_group, claim=False)
            h.guardians = [self.new_guardian(other_group, rng.random() < 0.8, last, rel, "Parent/Guardian")]
        if rng.random() < 0.30:  # extra emergency contact
            h.guardians.append(self.extra_contact(h))
        return h

    def extra_contact(self, h: Household) -> Guardian:
        rel = self.rng.choices(["Grandparent", "Aunt/Uncle", "Other"], [0.55, 0.35, 0.10])[0]
        last = h.surname if (rel != "Other" and self.rng.random() < 0.5) else self.names.surname(h.group, claim=False)
        return self.new_guardian(h.group, self.rng.random() < 0.65, last, rel, "Emergency")

    def sibling_count(self) -> int:
        return self.rng.choices([1, 2, 3, 4], [0.45, 0.37, 0.14, 0.04])[0]

    # ------------------------------------------------------------------ students
    def school_for_grade(self, grade: str) -> str:
        for s in self.cfg["schools"]:
            if grade in s["grades"]:
                return s["id"]
        raise ValueError(f"no school serves grade {grade}")

    def all_grades(self) -> list[str]:
        return [g for s in self.cfg["schools"] for g in s["grades"]]

    def grade_targets(self) -> dict[str, int]:
        return {g: s["students_per_grade"] for s in self.cfg["schools"] for g in s["grades"]}

    def dob_for_grade(self, grade: str) -> str:
        age = GRADE_NUM[grade] + 5  # age on Sept 1 of the school year
        cutoff = date(self.term_start.year, 9, 1)
        latest = date(cutoff.year - age, 9, 1)
        d = latest - timedelta(days=self.rng.randint(0, 364))
        if self.rng.random() < 0.04:  # a few held back a year
            d -= timedelta(days=365)
        return d.isoformat()

    def new_student(self, h: Household, grade: str) -> Student:
        rng = self.rng
        gender = rng.choices(["F", "M", "X"], [0.49, 0.495, 0.015])[0]
        first = self.names.child_first(h.group, gender)
        siblings = {s.first for s in self.roster.students_in_household(h.id)}
        for _ in range(10):
            if first not in siblings:
                break
            first = self.names.child_first(h.group, gender)
        last = h.surname
        mother = next((g for g in h.guardians if g.relationship == "Parent" and g.last != h.surname), None)
        if mother and h.group == "hispanic" and rng.random() < 0.12:
            last = f"{h.surname}-{mother.last}"
        race, hisp = self.race(h.group)
        sid = self.student_id()
        ell = "N"
        if h.home_language != "English":
            ell = "Y" if rng.random() < max(0.15, 0.6 - 0.06 * GRADE_NUM[grade]) else "N"
        preferred = NICKNAMES.get(first, "") if rng.random() < 0.3 else ""
        email = f"{ascii_slug(first)[:1]}{ascii_slug(last)[:12]}{sid[-3:]}@{self.d['student_email_domain']}"
        middle = self.names.middle(h.group, gender)
        while middle and (middle == first or middle == last or middle in last.split("-")):
            middle = self.names.middle(h.group, gender)
        return Student(
            id=sid, state_id=str(rng.randint(10**9, 10**10 - 1)), first=first,
            middle=middle, last=last, preferred_first=preferred,
            grade=grade, school_id=self.school_for_grade(grade), gender=gender,
            dob=self.dob_for_grade(grade), race=race, hispanic=hisp, ell=ell,
            frl=rng.choices(["F", "R", "N"], [0.36, 0.08, 0.56])[0],
            iep="Y" if rng.random() < 0.13 else "N",
            gifted="Y" if rng.random() < 0.07 else "N",
            s504="Y" if rng.random() < 0.03 else "N",
            email=email, household_id=h.id, created_on=self.today.isoformat(),
        )

    def race(self, group: str) -> tuple[str, str]:
        rng = self.rng
        if group == "hispanic":
            return rng.choices(["W", "M", "I", "B"], [0.72, 0.18, 0.06, 0.04])[0], "Y"
        if group == "asian":
            return ("P" if rng.random() < 0.04 else "A"), "N"
        if group == "black":
            return "B", "N"
        if group == "multiracial":
            return "M", ("Y" if rng.random() < 0.2 else "N")
        if group == "native":
            return rng.choice(["I", "P"]), ("Y" if rng.random() < 0.25 else "N")
        return "W", "N"

    def sibling_grades(self, first_grade: str, n: int, taken: set[str] | None = None) -> list[str]:
        """Grades for n-1 siblings of a child in first_grade, staying inside K-8."""
        grades = self.all_grades()
        idx = grades.index(first_grade)
        out, taken = [], set(taken or {first_grade})
        for _ in range(n - 1):
            for _ in range(10):
                off = self.rng.choice([-4, -3, -2, -2, -1, 1, 2, 2, 3, 4])
                j = idx + off
                if 0 <= j < len(grades) and grades[j] not in taken:
                    out.append(grades[j])
                    taken.add(grades[j])
                    break
        return out

    # ------------------------------------------------------------------ teachers
    def new_teacher(self, school_id: str, role_key: str) -> Teacher:
        rng = self.rng
        group = self.group(TEACHER_GROUPS)
        female = rng.random() < 0.76
        first = self.names.adult_first(group, female)
        last = self.names.surname(group, claim=False)
        tid = self.teacher_id()
        base = f"{ascii_slug(first)}.{ascii_slug(last)}"
        existing = {t.email for t in self.roster.teachers.values()}
        email, n = f"{base}@{self.d['staff_email_domain']}", 2
        while email in existing:
            email, n = f"{base}{n}@{self.d['staff_email_domain']}", n + 1
        return Teacher(
            id=tid, state_id=str(rng.randint(10**7, 10**8 - 1)), first=first,
            middle=(self.names.adult_first(group, female)[0] if rng.random() < 0.6 else ""), last=last,
            email=email, title=self.title_for(role_key), school_id=school_id, role_key=role_key,
            created_on=self.today.isoformat(),
        )

    def title_for(self, role_key: str) -> str:
        school_id, kind, detail = role_key.split(":")
        school = self.schools[school_id]
        if kind == "homeroom":
            return "Kindergarten Teacher" if detail == "Kindergarten" else f"Grade {detail} Teacher"
        if kind == "subject":
            course = next(c for c in school.get("core", []) + school.get("electives", []) if c["code"] == detail)
            return f"{course['name']} Teacher"
        return "Intervention Teacher"

    # ------------------------------------------------------------------ sections
    def section(self, sid: str, school_id: str, role_key: str, teacher_id: str, code: str, name: str,
                subject: str, grade: str, period: str) -> Section:
        return Section(
            id=sid, school_id=school_id, role_key=role_key, teacher_id=teacher_id, course_code=code,
            course_name=name, course_number=f"{school_id}-{code}-{grade_code(grade)}", subject=subject,
            grade=grade, period=period, created_on=self.today.isoformat(),
        )

    def enroll(self, st: Student) -> list[Section]:
        """Put a student into the standard sections for their school and grade."""
        school = self.schools[st.school_id]
        joined = []
        for sec in self.roster.sections.values():
            if sec.school_id != st.school_id or sec.grade != st.grade:
                continue
            kind = sec.role_key.split(":")[1]
            if kind == "homeroom" or (kind == "subject" and sec.course_code in {c["code"] for c in school.get("core", [])}):
                sec.student_ids.append(st.id)
                joined.append(sec)
        electives = [s for s in self.roster.sections.values()
                     if s.school_id == st.school_id and s.grade == st.grade
                     and s.course_code in {c["code"] for c in school.get("electives", [])}]
        if electives:
            pick = min(electives, key=lambda s: (len(s.student_ids), self.rng.random()))
            pick.student_ids.append(st.id)
            joined.append(pick)
        return joined

    def new_intervention(self, school_id: str) -> tuple[Teacher, Section]:
        n = self.counter(f"intervention:{school_id}")
        role_key = f"{school_id}:intervention:{n}"
        t = self.new_teacher(school_id, role_key)
        school = self.schools[school_id]
        grade = self.rng.choice(school["grades"])
        focus = self.rng.choice([("RINT", "Reading Intervention"), ("MINT", "Math Intervention")])
        t.title = f"{focus[1]} Teacher"
        sec = self.section(f"{school_id}-{focus[0]}{n}", school_id, role_key, t.id, focus[0], focus[1],
                           "Interventions/online learning", grade, str(self.rng.randint(1, 6)))
        sec.course_number = f"{school_id}-{focus[0]}{n}"
        pool = [s.id for s in self.roster.students_in_grade(school_id, grade)]
        sec.student_ids = sorted(self.rng.sample(pool, k=min(len(pool), self.rng.randint(6, 10))))
        return t, sec
