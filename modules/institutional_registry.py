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
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from modules.database import get_connection as open_database_connection

registry_bp = Blueprint("registry", __name__, url_prefix="/admin/registry")
DATABASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "exam_integrity.db")
ACADEMIC_STATUSES = {"active", "deferred", "suspended", "graduated", "withdrawn"}
CSV_FIELDS = {
    "admission_number", "first_name", "last_name", "course", "year_of_study",
    "faculty", "department", "institutional_email", "phone",
    "academic_status", "academic_year", "semester",
}


def get_connection():
    return open_database_connection(DATABASE)


_schema_ready = False


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

        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            summary TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (actor_user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS academic_history_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN
                ('programme_change','progression','academic_status_change','deferment','suspension','graduation')),
            effective_date TEXT NOT NULL,
            previous_value TEXT,
            new_value TEXT,
            reason TEXT NOT NULL,
            recorded_by INTEGER NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE RESTRICT,
            FOREIGN KEY(recorded_by) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_academic_history_student_date
            ON academic_history_events(student_id, effective_date DESC, id DESC);
        CREATE TRIGGER IF NOT EXISTS academic_history_no_update
        BEFORE UPDATE ON academic_history_events
        BEGIN SELECT RAISE(ABORT, 'Academic history events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS academic_history_no_delete
        BEFORE DELETE ON academic_history_events
        BEGIN SELECT RAISE(ABORT, 'Academic history events are append-only'); END;

        -- Deprecated legacy examination_attendance storage is intentionally
        -- not created for new installations. Existing tables and rows are
        -- left untouched until a separately reviewed archival migration.
    """)
    connection.close()


@registry_bp.before_request
def prepare_registry():
    global _schema_ready
    if "user_id" not in session or session.get("role") not in {"admin", "registrar"}:
        return redirect(url_for("login"))
    if not _schema_ready:
        ensure_schema()
        _schema_ready = True


def _record_audit(connection, action, entity_type, entity_id, summary):
    connection.execute("""
        INSERT INTO audit_events (actor_user_id, action, entity_type, entity_id, summary)
        VALUES (?, ?, ?, ?, ?)
    """, (session.get("user_id"), action, entity_type, str(entity_id) if entity_id is not None else None, summary))


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


@registry_bp.get("/students/<int:student_id>")
def student_detail(student_id):
    """Read-only consolidated view of the student record and unit history."""
    connection = get_connection()
    student = connection.execute("""
        SELECT s.*, p.faculty, p.department, p.institutional_email, p.phone,
               COALESCE(p.academic_status, 'active') AS academic_status,
               p.academic_year, p.semester, p.updated_at AS profile_updated_at
        FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id
        WHERE s.id=?
    """, (student_id,)).fetchone()
    if student is None:
        connection.close()
        from flask import abort
        abort(404)
    enrolments = connection.execute("""
        SELECT e.id, e.academic_year, e.semester, e.enrolment_status,
               e.created_at, u.unit_code, u.unit_name, u.department, u.faculty
        FROM student_unit_enrolments e
        JOIN academic_units u ON u.id=e.unit_id
        WHERE e.student_id=?
        ORDER BY e.academic_year DESC, e.semester DESC, u.unit_code
    """, (student_id,)).fetchall()
    history_count = connection.execute(
        "SELECT COUNT(*) FROM academic_history_events WHERE student_id=?",
        (student_id,),
    ).fetchone()[0]
    connection.close()
    return render_template("student_record.html", student=student,
                           enrolments=enrolments, history_count=history_count)


@registry_bp.route("/students/new", methods=["GET", "POST"])
def new_student():
    if request.method == "POST":
        try:
            values = _student_values(request.form)
            connection = get_connection()
            student_id = _save_student(connection, values)
            _record_audit(connection, "create", "student", student_id,
                          "Student record created through the institutional registry.")
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
        _record_audit(connection, "update", "student", student_id,
                      "Student record updated through the institutional registry.")
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


def _validate_student_csv(raw, connection):
    """Validate the complete CSV before writing any student rows.

    Returns (valid_rows, row_errors). A single invalid row blocks the whole
    import so an operator cannot mistake a partial import for a complete one.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("The file must be a UTF-8 CSV.")

    reader = csv.DictReader(io.StringIO(text))
    headers = {header.strip() for header in (reader.fieldnames or []) if header and header.strip()}
    missing = CSV_FIELDS - headers
    if missing:
        raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
    if not reader.fieldnames:
        raise ValueError("The CSV file is empty or has no header row.")

    valid_rows = []
    row_errors = []
    seen_admissions = set()
    seen_emails = set()
    for row_number, row in enumerate(reader, start=2):
        if None in row:
            row_errors.append({"row": row_number, "message": "The row contains more values than the header."})
            continue
        normalized = {str(key).strip(): (value or "").strip()
                      for key, value in row.items() if key}
        try:
            values = _student_values(normalized)
            admission, email = values[0], values[7]
            if admission in seen_admissions:
                raise ValueError("Duplicate admission number within this CSV.")
            if email and email in seen_emails:
                raise ValueError("Duplicate institutional email within this CSV.")
            if connection.execute(
                "SELECT 1 FROM students WHERE student_number=?", (admission,)
            ).fetchone():
                raise ValueError("Admission number already exists in the registry.")
            if email and connection.execute(
                "SELECT 1 FROM student_profiles WHERE lower(institutional_email)=lower(?)",
                (email,),
            ).fetchone():
                raise ValueError("Institutional email already exists in the registry.")
            seen_admissions.add(admission)
            if email:
                seen_emails.add(email)
            valid_rows.append(values)
        except (ValueError, sqlite3.IntegrityError) as error:
            row_errors.append({"row": row_number, "message": str(error)})
    if not valid_rows and not row_errors:
        row_errors.append({"row": 0, "message": "The CSV contains no student data rows."})
    return valid_rows, row_errors


@registry_bp.route("/students/import", methods=["GET", "POST"])
def import_students():
    if request.method == "GET":
        return render_template("student_registry_import.html")
    upload = request.files.get("file")
    if not upload or not upload.filename or not upload.filename.lower().endswith(".csv"):
        return render_template("student_registry_import.html", error="Choose a CSV file.")
    raw = upload.read(2_000_001)
    if len(raw) > 2_000_000:
        return render_template("student_registry_import.html", error="CSV files must be 2 MB or smaller.")

    connection = get_connection()
    try:
        valid_rows, row_errors = _validate_student_csv(raw, connection)
        if row_errors:
            connection.rollback()
            return render_template(
                "student_registry_import.html",
                error="No records were imported. Correct the reported rows and upload the complete file again.",
                row_errors=row_errors,
                valid_count=len(valid_rows),
            )
        for values in valid_rows:
            student_id = _save_student(connection, values)
            _record_audit(connection, "create", "student", student_id,
                          "Student record created through the validated institutional CSV import.")
        _record_audit(connection, "import", "student_registry", None,
                      f"Validated CSV import completed: {len(valid_rows)} student record(s) created.")
        connection.commit()
        flash(f"CSV import complete: {len(valid_rows)} student record(s) created. Review the register before operational use.", "success")
        return redirect(url_for("registry.students"))
    except (ValueError, sqlite3.IntegrityError) as error:
        connection.rollback()
        return render_template("student_registry_import.html",
                               error=f"No records were imported. Import validation failed: {error}")
    finally:
        connection.close()


HISTORY_EVENT_TYPES = {
    "programme_change", "progression", "academic_status_change",
    "deferment", "suspension", "graduation",
}


@registry_bp.route("/students/<int:student_id>/history", methods=["GET", "POST"])
def academic_history(student_id):
    """Registrar-managed, append-only academic history for one student."""
    connection = get_connection()
    student = connection.execute("""
        SELECT s.id, s.student_number, s.first_name, s.last_name, s.course,
               COALESCE(p.academic_status, 'active') AS academic_status
        FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id
        WHERE s.id=?
    """, (student_id,)).fetchone()
    if not student:
        connection.close()
        from flask import abort
        abort(404)

    if request.method == "POST":
        event_type = _clean(request.form.get("event_type"), 40).lower()
        effective_date = _clean(request.form.get("effective_date"), 10)
        previous_value = _clean(request.form.get("previous_value"), 240) or None
        new_value = _clean(request.form.get("new_value"), 240) or None
        reason = _clean(request.form.get("reason"), 1000)
        try:
            from datetime import date
            date.fromisoformat(effective_date)
        except (TypeError, ValueError):
            connection.close()
            return render_template("academic_history.html", student=student, events=[],
                event_types=sorted(HISTORY_EVENT_TYPES),
                error="Enter an effective date in YYYY-MM-DD format.")
        if event_type not in HISTORY_EVENT_TYPES or len(reason) < 10:
            connection.close()
            return render_template("academic_history.html", student=student, events=[],
                event_types=sorted(HISTORY_EVENT_TYPES),
                error="Choose a valid history event and provide a reason of at least 10 characters.")
        if event_type == "academic_status_change" and new_value not in ACADEMIC_STATUSES:
            connection.close()
            return render_template("academic_history.html", student=student, events=[],
                event_types=sorted(HISTORY_EVENT_TYPES),
                error="The new academic status must be an approved status value.")
        try:
            connection.execute("""
                INSERT INTO academic_history_events
                    (student_id,event_type,effective_date,previous_value,new_value,reason,recorded_by)
                VALUES (?,?,?,?,?,?,?)
            """, (student_id,event_type,effective_date,previous_value,new_value,reason,session["user_id"]))
            if event_type == "academic_status_change":
                connection.execute("""
                    INSERT INTO student_profiles(student_id,academic_status,updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(student_id) DO UPDATE SET
                      academic_status=excluded.academic_status, updated_at=CURRENT_TIMESTAMP
                """, (student_id,new_value))
            _record_audit(connection,"append","academic_history",student_id,
                          f"Recorded {event_type} effective {effective_date}.")
            connection.commit()
            flash("Academic history event recorded. Existing history entries cannot be edited or deleted.", "success")
            connection.close()
            return redirect(url_for("registry.academic_history", student_id=student_id))
        except sqlite3.IntegrityError:
            connection.rollback()
            connection.close()
            return render_template("academic_history.html", student=student, events=[],
                event_types=sorted(HISTORY_EVENT_TYPES),
                error="The history event could not be recorded. Check the supplied details and try again.")

    events = connection.execute("""
        SELECT h.*, u.username AS recorded_by_username
        FROM academic_history_events h JOIN users u ON u.id=h.recorded_by
        WHERE h.student_id=?
        ORDER BY h.effective_date DESC, h.id DESC
    """, (student_id,)).fetchall()
    connection.close()
    return render_template("academic_history.html", student=student, events=events,
                           event_types=sorted(HISTORY_EVENT_TYPES))
