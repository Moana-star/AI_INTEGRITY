"""Institutional student registry blueprint.

This module extends the existing EIMS student records without changing the
legacy students table or deleting existing data. It intentionally does not
collect biometric templates, face images, or face embeddings.
"""
from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

registry_bp = Blueprint("registry", __name__, url_prefix="/admin/registry")
DATABASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "exam_integrity.db")
ACADEMIC_STATUSES = {"active", "deferred", "suspended", "graduated", "withdrawn"}
CSV_FIELDS = {
    "admission_number", "first_name", "last_name", "course", "year_of_study",
    "faculty", "department", "institutional_email", "phone",
    "academic_status", "academic_year", "semester",
}


def get_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema():
    """Create additive registry tables; safe to run repeatedly on existing DBs."""
    connection = get_connection()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS student_profiles (
            student_id INTEGER PRIMARY KEY,
            faculty TEXT,
            department TEXT,
            institutional_email TEXT UNIQUE,
            phone TEXT,
            academic_status TEXT NOT NULL DEFAULT 'active'
                CHECK (academic_status IN ('active','deferred','suspended','graduated','withdrawn')),
            academic_year TEXT,
            semester TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS academic_units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_code TEXT NOT NULL UNIQUE,
            unit_name TEXT NOT NULL,
            department TEXT,
            faculty TEXT,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS student_unit_enrolments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            unit_id INTEGER NOT NULL,
            academic_year TEXT NOT NULL,
            semester TEXT NOT NULL,
            enrolment_status TEXT NOT NULL DEFAULT 'registered'
                CHECK (enrolment_status IN ('registered','dropped','completed')),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (student_id, unit_id, academic_year, semester),
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (unit_id) REFERENCES academic_units(id)
        );
    """)
    connection.close()


@registry_bp.before_request
def prepare_registry():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))
    ensure_schema()


def _clean(value, limit=160):
    value = " ".join((value or "").split())
    return value[:limit]


def _student_values(source):
    admission = _clean(source.get("admission_number") or source.get("student_number"), 60)
    first_name = _clean(source.get("first_name"), 80)
    last_name = _clean(source.get("last_name"), 80)
    course = _clean(source.get("course"), 160)
    faculty = _clean(source.get("faculty"), 160)
    department = _clean(source.get("department"), 160)
    email = _clean(source.get("institutional_email"), 160).lower() or None
    phone = _clean(source.get("phone"), 40) or None
    status = _clean(source.get("academic_status") or "active", 20).lower()
    academic_year = _clean(source.get("academic_year"), 20) or None
    semester = _clean(source.get("semester"), 40) or None
    raw_year = _clean(source.get("year_of_study"), 2)
    try:
        year_of_study = int(raw_year) if raw_year else None
    except ValueError:
        raise ValueError("Year of study must be a whole number.")
    if not admission or not first_name or not last_name or not course:
        raise ValueError("Admission number, first name, last name and programme are required.")
    if year_of_study is not None and not 1 <= year_of_study <= 10:
        raise ValueError("Year of study must be between 1 and 10.")
    if status not in ACADEMIC_STATUSES:
        raise ValueError("Choose a valid academic status.")
    if email and (len(email) > 160 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)):
        raise ValueError("Enter a valid institutional email address.")
    return (admission, first_name, last_name, course, year_of_study,
            faculty, department, email, phone, status, academic_year, semester)


def _save_student(connection, values, update=False, student_id=None):
    (admission, first_name, last_name, course, year, faculty, department,
     email, phone, status, academic_year, semester) = values
    if update:
        connection.execute("""
            UPDATE students SET student_number=?, first_name=?, last_name=?,
                course=?, year_of_study=? WHERE id=?
        """, (admission, first_name, last_name, course, year, student_id))
        target_id = student_id
    else:
        cursor = connection.execute("""
            INSERT INTO students (student_number, first_name, last_name, course, year_of_study)
            VALUES (?, ?, ?, ?, ?)
        """, (admission, first_name, last_name, course, year))
        target_id = cursor.lastrowid

    connection.execute("""
        INSERT INTO student_profiles
            (student_id, faculty, department, institutional_email, phone,
             academic_status, academic_year, semester, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(student_id) DO UPDATE SET
            faculty=excluded.faculty, department=excluded.department,
            institutional_email=excluded.institutional_email, phone=excluded.phone,
            academic_status=excluded.academic_status,
            academic_year=excluded.academic_year, semester=excluded.semester,
            updated_at=CURRENT_TIMESTAMP
    """, (target_id, faculty or None, department or None, email, phone,
          status, academic_year, semester))
    return target_id


@registry_bp.get("/students")
def students():
    query = _clean(request.args.get("q"), 100)
    connection = get_connection()
    sql = """
        SELECT s.*, p.faculty, p.department, p.institutional_email, p.phone,
               COALESCE(p.academic_status, 'active') AS academic_status,
               p.academic_year, p.semester
        FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id
    """
    params = ()
    if query:
        like = f"%{query}%"
        sql += """ WHERE s.student_number LIKE ? OR s.first_name LIKE ?
                   OR s.last_name LIKE ? OR s.course LIKE ? OR p.department LIKE ?"""
        params = (like, like, like, like, like)
    sql += " ORDER BY s.student_number"
    records = connection.execute(sql, params).fetchall()
    connection.close()
    return render_template("student_registry.html", students=records, query=query)


@registry_bp.route("/students/new", methods=["GET", "POST"])
def new_student():
    if request.method == "POST":
        try:
            values = _student_values(request.form)
            connection = get_connection()
            _save_student(connection, values)
            connection.commit()
            connection.close()
            flash("Student record created in the institutional registry.", "success")
            return redirect(url_for("registry.students"))
        except (ValueError, sqlite3.IntegrityError) as error:
            if "connection" in locals():
                connection.rollback()
                connection.close()
            return render_template("student_registry_form.html", student=None,
                                   error=str(error) if isinstance(error, ValueError)
                                   else "Admission number or institutional email is already registered.")
    return render_template("student_registry_form.html", student=None)


@registry_bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
def edit_student(student_id):
    connection = get_connection()
    if request.method == "GET":
        student = connection.execute("""
            SELECT s.*, p.faculty, p.department, p.institutional_email, p.phone,
                   COALESCE(p.academic_status, 'active') AS academic_status,
                   p.academic_year, p.semester
            FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id
            WHERE s.id=?
        """, (student_id,)).fetchone()
        connection.close()
        if student is None:
            flash("Student record was not found.", "error")
            return redirect(url_for("registry.students"))
        return render_template("student_registry_form.html", student=student)

    try:
        values = _student_values(request.form)
        _save_student(connection, values, update=True, student_id=student_id)
        connection.commit()
        connection.close()
        flash("Student record updated.", "success")
        return redirect(url_for("registry.students"))
    except (ValueError, sqlite3.IntegrityError) as error:
        connection.rollback()
        student = connection.execute("""
            SELECT s.*, p.faculty, p.department, p.institutional_email, p.phone,
                   COALESCE(p.academic_status, 'active') AS academic_status,
                   p.academic_year, p.semester
            FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id
            WHERE s.id=?
        """, (student_id,)).fetchone()
        connection.close()
        message = str(error) if isinstance(error, ValueError) else "Admission number or institutional email is already in use."
        return render_template("student_registry_form.html", student=student, error=message)


@registry_bp.route("/students/import", methods=["GET", "POST"])
def import_students():
    if request.method == "GET":
        return render_template("student_registry_import.html")
    upload = request.files.get("file")
    if not upload or not upload.filename.lower().endswith(".csv"):
        return render_template("student_registry_import.html", error="Choose a CSV file.")
    raw = upload.read(2_000_001)
    if len(raw) > 2_000_000:
        return render_template("student_registry_import.html", error="CSV files must be 2 MB or smaller.")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = {header.strip() for header in (reader.fieldnames or [])}
        missing = CSV_FIELDS - headers
        if missing:
            return render_template("student_registry_import.html",
                error="Missing CSV columns: " + ", ".join(sorted(missing)))
        connection = get_connection()
        imported = 0
        rejected = 0
        for row in reader:
            try:
                normalized = {str(k).strip(): (v or "").strip() for k, v in row.items() if k}
                values = _student_values(normalized)
                _save_student(connection, values)
                imported += 1
            except (ValueError, sqlite3.IntegrityError):
                rejected += 1
        connection.commit()
        connection.close()
        flash(f"CSV import complete: {imported} record(s) imported; {rejected} row(s) skipped. Review the register before operational use.", "success")
        return redirect(url_for("registry.students"))
    except (UnicodeDecodeError, csv.Error):
        return render_template("student_registry_import.html",
                               error="The file could not be read as a UTF-8 CSV. Export it as UTF-8 CSV and try again.")
