import csv
import io
from collections import Counter
from datetime import date

import pytest

from sim.config import load_config
from sim.csvwriter import FILES, render
from sim.generate import generate
from sim.model import Roster
from sim.validate import validate


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def roster(cfg):
    return generate(cfg, date(2026, 11, 18))


def test_sizes_match_config(cfg, roster):
    expected = sum(s["students_per_grade"] * len(s["grades"]) for s in cfg["schools"])
    assert abs(len(roster.students) - expected) <= 2
    assert len(roster.teachers) == 12
    assert len(roster.sections) == 30


def test_valid(cfg, roster):
    assert validate(cfg, roster) == []


def test_generation_is_deterministic(cfg, roster):
    again = generate(cfg, date(2026, 11, 18))
    assert again.to_json() == roster.to_json()


def test_json_round_trip(roster):
    assert Roster.from_json(roster.to_json()).to_json() == roster.to_json()


def test_no_surname_dominates(roster):
    top = Counter(h.surname for h in roster.households.values()).most_common(1)[0][1]
    assert top <= 4, "no surname should cover more than a handful of families"
    assert len({h.surname for h in roster.households.values()}) > len(roster.households) * 0.7


def test_families_mostly_share_surname(roster):
    hs = list(roster.households.values())
    shared = sum(1 for h in hs if any(g.last == h.surname for g in h.guardians))
    assert shared / len(hs) > 0.8
    assert shared < len(hs), "some guardians should have a different surname"
    for h in hs:
        for s in roster.students_in_household(h.id):
            assert s.last.split("-")[0] == h.surname


def test_siblings_share_contacts(cfg, roster):
    files = render(cfg, roster)
    rows = list(csv.DictReader(io.StringIO(files["students.csv"])))
    by_contact = {}
    for r in rows:
        by_contact.setdefault(r["Contact_sis_id"], set()).add(r["Student_id"])
    assert any(len(v) > 1 for v in by_contact.values()), "a guardian of siblings should appear for each child"


def test_csv_headers_match_clever_sample(cfg, roster):
    """Header spellings follow Clever's own sample sandbox files."""
    files = render(cfg, roster)
    assert set(files) == set(FILES)
    heads = {k: v.splitlines()[0].split(",") for k, v in files.items()}
    assert heads["enrollments.csv"] == ["School_id", "Section_id", "Student_id"]
    for col in ["School_id", "Student_id", "Student_number", "Last_name", "First_name", "Grade",
                "Contact_name", "Contact_type", "Contact_relationship", "Contact_phone", "Contact_email",
                "Username", "Password"]:
        assert col in heads["students.csv"]
    for col in ["School_id", "Teacher_id", "Teacher_number", "Last_name", "First_name", "Username", "Password"]:
        assert col in heads["teachers.csv"]
    for col in ["School_id", "Section_id", "Teacher_id", "Course_name", "Term_name"]:
        assert col in heads["sections.csv"]


def test_login_pattern(cfg, roster):
    files = render(cfg, roster)
    for r in csv.DictReader(io.StringIO(files["students.csv"])):
        assert r["Username"] == r["Password"] == r["Student_number"] == r["Student_id"]
    for r in csv.DictReader(io.StringIO(files["teachers.csv"])):
        assert r["Username"] == r["Password"] == r["Teacher_number"] == r["Teacher_id"]


def test_referential_integrity_in_csv(cfg, roster):
    f = render(cfg, roster)
    students = {r["Student_id"] for r in csv.DictReader(io.StringIO(f["students.csv"]))}
    teachers = {r["Teacher_id"] for r in csv.DictReader(io.StringIO(f["teachers.csv"]))}
    sections = {r["Section_id"]: r for r in csv.DictReader(io.StringIO(f["sections.csv"]))}
    assert all(s["Teacher_id"] in teachers for s in sections.values())
    enr = list(csv.DictReader(io.StringIO(f["enrollments.csv"])))
    assert all(e["Student_id"] in students and e["Section_id"] in sections for e in enr)
    assert {e["Section_id"] for e in enr} == set(sections), "every section has students"


def test_only_reserved_email_domains(cfg, roster):
    for h in roster.households.values():
        for g in h.guardians:
            assert not g.email or g.email.split("@")[1] in cfg["district"]["guardian_email_domains"]
            assert g.phone[3:8] == "55501", "fictional 555-01XX numbers only"
    for t in roster.teachers.values():
        assert t.email.endswith(".example")
    for s in roster.students.values():
        assert s.email.endswith(".example")


def test_ages_fit_grades(roster):
    from sim.factory import GRADE_NUM
    for s in roster.students.values():
        age = 2026 - date.fromisoformat(s.dob).year
        assert GRADE_NUM[s.grade] + 4 <= age <= GRADE_NUM[s.grade] + 7
