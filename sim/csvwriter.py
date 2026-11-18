"""Render the roster as the five Clever SFTP files.

Header names follow Clever's own sample sandbox files (underscored, e.g. School_id).
Each guardian is its own row in students.csv; Contact_sis_id keeps a guardian
shared across siblings as a single contact in Clever.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

from .model import Roster

SCHOOL_COLS = ["School_id", "School_name", "School_number", "State_id", "Low_grade", "High_grade",
               "Principal", "Principal_email", "School_address", "School_city", "School_state",
               "School_zip", "School_phone"]
STUDENT_COLS = ["School_id", "Student_id", "Student_number", "State_id", "Last_name", "Middle_name",
                "First_name", "Preferred_first_name", "Grade", "Gender", "DOB", "Race", "Hispanic_Latino",
                "Home_language", "Ell_status", "Frl_status", "IEP_status", "Gifted_status",
                "Section_504_status", "Graduation_year", "Student_street", "Student_city", "Student_state",
                "Student_zip", "Student_email", "Contact_relationship", "Contact_type", "Contact_name",
                "Contact_phone", "Contact_phone_type", "Contact_email", "Contact_sis_id", "Username", "Password"]
TEACHER_COLS = ["School_id", "Teacher_id", "Teacher_number", "State_teacher_id", "Teacher_email",
                "First_name", "Middle_name", "Last_name", "Title", "Username", "Password"]
SECTION_COLS = ["School_id", "Section_id", "Teacher_id", "Name", "Section_number", "Grade", "Course_name",
                "Course_number", "Period", "Subject", "Term_name", "Term_start", "Term_end"]
ENROLLMENT_COLS = ["School_id", "Section_id", "Student_id"]

FILES = ["schools.csv", "students.csv", "teachers.csv", "sections.csv", "enrollments.csv"]

PRINCIPALS = {  # fixed, so schools.csv never churns
    "ES01": ("Dana Whitfield", "dana.whitfield"),
    "MS01": ("Marcus Ortega", "marcus.ortega"),
}


def us_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


def graduation_year(cfg: dict, grade: str) -> str:
    from .factory import GRADE_NUM
    start = date.fromisoformat(cfg["term"]["start"]).year
    return str(start + 1 + (12 - GRADE_NUM[grade]))


def _rows_to_csv(cols: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    return buf.getvalue()


def render(cfg: dict, roster: Roster) -> dict[str, str]:
    d = cfg["district"]
    term = cfg["term"]

    schools = []
    for s in cfg["schools"]:
        pname, pslug = PRINCIPALS.get(s["id"], ("", ""))
        schools.append({
            "School_id": s["id"], "School_name": s["name"], "School_number": s["number"],
            "State_id": s.get("state_id", ""), "Low_grade": s["grades"][0], "High_grade": s["grades"][-1],
            "Principal": pname, "Principal_email": f"{pslug}@{d['staff_email_domain']}" if pslug else "",
            "School_address": s.get("address", ""), "School_city": d["city"], "School_state": d["state"],
            "School_zip": s.get("zip", ""), "School_phone": s.get("phone", ""),
        })

    students = []
    for st in sorted(roster.students.values(), key=lambda x: (x.school_id, x.last, x.first, x.id)):
        h = roster.households[st.household_id]
        base = {
            "School_id": st.school_id, "Student_id": st.id, "Student_number": st.id, "State_id": st.state_id,
            "Last_name": st.last, "Middle_name": st.middle, "First_name": st.first,
            "Preferred_first_name": st.preferred_first, "Grade": st.grade, "Gender": st.gender,
            "DOB": us_date(st.dob), "Race": st.race, "Hispanic_Latino": st.hispanic,
            "Home_language": h.home_language, "Ell_status": st.ell, "Frl_status": st.frl,
            "IEP_status": st.iep, "Gifted_status": st.gifted, "Section_504_status": st.s504,
            "Graduation_year": graduation_year(cfg, st.grade), "Student_street": h.street,
            "Student_city": h.city, "Student_state": h.state, "Student_zip": h.zip, "Student_email": st.email,
            # Login pattern: username and password are both the student number.
            "Username": st.id, "Password": st.id,
        }
        for g in h.guardians:
            students.append({**base,
                             "Contact_relationship": g.relationship, "Contact_type": g.type,
                             "Contact_name": g.full_name, "Contact_phone": g.phone,
                             "Contact_phone_type": g.phone_type, "Contact_email": g.email,
                             "Contact_sis_id": g.id})
        if not h.guardians:
            students.append(base)

    teachers = [{
        "School_id": t.school_id, "Teacher_id": t.id, "Teacher_number": t.id, "State_teacher_id": t.state_id,
        "Teacher_email": t.email, "First_name": t.first, "Middle_name": t.middle, "Last_name": t.last,
        "Title": t.title, "Username": t.id, "Password": t.id,
    } for t in sorted(roster.teachers.values(), key=lambda x: (x.school_id, x.last, x.id))]

    sections, enrollments = [], []
    for sec in sorted(roster.sections.values(), key=lambda x: x.id):
        t = roster.teachers[sec.teacher_id]
        sections.append({
            "School_id": sec.school_id, "Section_id": sec.id, "Teacher_id": sec.teacher_id,
            "Name": f"{sec.course_name} - {t.last} - {sec.period}", "Section_number": sec.id.split("-", 1)[1],
            "Grade": sec.grade, "Course_name": sec.course_name, "Course_number": sec.course_number,
            "Period": sec.period, "Subject": sec.subject, "Term_name": term["name"],
            "Term_start": us_date(term["start"]), "Term_end": us_date(term["end"]),
        })
        for sid in sorted(sec.student_ids):
            enrollments.append({"School_id": sec.school_id, "Section_id": sec.id, "Student_id": sid})

    return {
        "schools.csv": _rows_to_csv(SCHOOL_COLS, schools),
        "students.csv": _rows_to_csv(STUDENT_COLS, students),
        "teachers.csv": _rows_to_csv(TEACHER_COLS, teachers),
        "sections.csv": _rows_to_csv(SECTION_COLS, sections),
        "enrollments.csv": _rows_to_csv(ENROLLMENT_COLS, enrollments),
    }


def write(files: dict[str, str], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in files.items():
        p = out_dir / name
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    return paths
