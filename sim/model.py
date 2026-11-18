"""The roster: households, students, teachers, sections. Persisted as state/roster.json.

Git is the source of truth, so the JSON is written deterministically (sorted keys)
and each day's drift shows up as a reviewable diff.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1


@dataclass
class Guardian:
    id: str                 # Contact_sis_id; stable, shared across siblings
    first: str
    last: str
    relationship: str       # Parent | Grandparent | Aunt/Uncle | Other
    type: str               # Parent/Guardian | Emergency | Family
    phone: str              # 10 digits
    phone_type: str         # Cell | Home | Work
    email: str

    @property
    def full_name(self) -> str:
        return f"{self.first} {self.last}"


@dataclass
class Household:
    id: str
    group: str              # demographic group, drives names/language
    surname: str            # the children's surname
    street: str
    city: str
    state: str
    zip: str
    home_language: str
    guardians: list[Guardian] = field(default_factory=list)


@dataclass
class Student:
    id: str                 # Student_id == Student_number (also the login)
    state_id: str
    first: str
    middle: str
    last: str
    preferred_first: str
    grade: str              # "Kindergarten" or "1".."8"
    school_id: str
    gender: str             # M | F | X
    dob: str                # ISO date
    race: str               # A B I M P W
    hispanic: str           # Y | N
    ell: str
    frl: str                # F | R | N
    iep: str
    gifted: str
    s504: str
    email: str
    household_id: str
    created_on: str         # ISO date the record first appeared in an upload


@dataclass
class Teacher:
    id: str                 # Teacher_id == Teacher_number (also the login)
    state_id: str
    first: str
    middle: str
    last: str
    email: str
    title: str
    school_id: str
    role_key: str           # e.g. "ES01:homeroom:3", "MS01:subject:MATH", "MS01:intervention:2"
    created_on: str


@dataclass
class Section:
    id: str
    school_id: str
    role_key: str           # the teaching role this section belongs to
    teacher_id: str         # current primary teacher (role holder, or a cover teacher)
    course_code: str
    course_name: str
    course_number: str
    subject: str
    grade: str
    period: str
    student_ids: list[str] = field(default_factory=list)
    created_on: str = ""


@dataclass
class Roster:
    schema_version: int = SCHEMA_VERSION
    seed: int = 0
    last_drift_date: str = ""          # Pacific date of the last applied drift
    last_upload_at: str = ""           # UTC ISO timestamp of the last SFTP upload
    households: dict[str, Household] = field(default_factory=dict)
    students: dict[str, Student] = field(default_factory=dict)
    teachers: dict[str, Teacher] = field(default_factory=dict)
    sections: dict[str, Section] = field(default_factory=dict)
    vacancies: list[str] = field(default_factory=list)   # role_keys with no permanent teacher
    used_ids: list[str] = field(default_factory=list)    # never reuse an id, even after removal
    counters: dict[str, int] = field(default_factory=dict)

    # ---------- queries ----------
    def students_in_household(self, hid: str) -> list[Student]:
        return [s for s in self.students.values() if s.household_id == hid]

    def sections_for_role(self, role_key: str) -> list[Section]:
        return [s for s in self.sections.values() if s.role_key == role_key]

    def sections_for_student(self, sid: str) -> list[Section]:
        return [s for s in self.sections.values() if sid in s.student_ids]

    def students_in_grade(self, school_id: str, grade: str) -> list[Student]:
        return [s for s in self.students.values() if s.school_id == school_id and s.grade == grade]

    def teachers_at(self, school_id: str) -> list[Teacher]:
        return [t for t in self.teachers.values() if t.school_id == school_id]

    def role_holder(self, role_key: str) -> Teacher | None:
        for t in self.teachers.values():
            if t.role_key == role_key:
                return t
        return None

    # ---------- persistence ----------
    def to_json(self) -> str:
        data = asdict(self)
        data["used_ids"] = sorted(set(self.used_ids))
        return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Roster":
        d = json.loads(text)
        r = cls(
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            seed=d.get("seed", 0),
            last_drift_date=d.get("last_drift_date", ""),
            last_upload_at=d.get("last_upload_at", ""),
            vacancies=d.get("vacancies", []),
            used_ids=d.get("used_ids", []),
            counters=d.get("counters", {}),
        )
        for k, h in d.get("households", {}).items():
            gs = [Guardian(**g) for g in h.pop("guardians", [])]
            r.households[k] = Household(**h, guardians=gs)
        r.students = {k: Student(**v) for k, v in d.get("students", {}).items()}
        r.teachers = {k: Teacher(**v) for k, v in d.get("teachers", {}).items()}
        r.sections = {k: Section(**v) for k, v in d.get("sections", {}).items()}
        return r

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())

    @classmethod
    def load(cls, path: Path) -> "Roster":
        return cls.from_json(path.read_text())
