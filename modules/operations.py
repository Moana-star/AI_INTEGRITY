"""Operational academic, examination-session and attendance workflows.

Uses the existing SQLite database for the current development increment.
No synthetic biometric result is generated. Attendance identity checks are
manual or student-card checks until an institution approves and configures a
separate biometric provider.
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import date, datetime
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

operations_bp = Blueprint("operations", __name__, url_prefix="/operations")
DATABASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "exam_integrity.db")
SCHEMA_READY = False


def db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema():
    connection = db()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS venues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venue_code TEXT NOT NULL UNIQUE,
            building TEXT,
            room_name TEXT NOT NULL,
            capacity INTEGER NOT NULL CHECK(capacity > 0),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS examination_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_code TEXT NOT NULL UNIQUE,
            examination_id INTEGER NOT NULL,
            unit_id INTEGER,
            academic_year TEXT NOT NULL,
            semester TEXT NOT NULL,
            venue_id INTEGER,
            session_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'scheduled'
                CHECK(status IN ('scheduled','active','completed','cancelled')),
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(examination_id) REFERENCES examinations(id),
            FOREIGN KEY(unit_id) REFERENCES academic_units(id),
            FOREIGN KEY(venue_id) REFERENCES venues(id),
            FOREIGN KEY(created_by) REFERENCES users(id),
            CHECK(end_time > start_time)
        );
        CREATE TABLE IF NOT EXISTS session_invigilators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            invigilator_id INTEGER NOT NULL,
            assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, invigilator_id),
            FOREIGN KEY(session_id) REFERENCES examination_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(invigilator_id) REFERENCES invigilators(id)
        );
        CREATE TABLE IF NOT EXISTS session_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            eligibility_status TEXT NOT NULL DEFAULT 'eligible'
                CHECK(eligibility_status IN ('eligible','pending','ineligible')),
            eligibility_note TEXT,
            seat_label TEXT,
            UNIQUE(session_id, student_id),
            UNIQUE(session_id, seat_label),
            FOREIGN KEY(session_id) REFERENCES examination_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES students(id)
        );
        CREATE TABLE IF NOT EXISTS attendance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('check_in','check_out')),
            verification_method TEXT NOT NULL CHECK(verification_method IN ('manual','student_card')),
            verification_status TEXT NOT NULL CHECK(verification_status IN ('verified','manual_review')),
            recorded_by INTEGER NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES examination_sessions(id),
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(recorded_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS session_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'present'
                CHECK(status IN ('present','absent','late','disputed')),
            check_in_at TEXT,
            check_out_at TEXT,
            verification_method TEXT,
            verification_status TEXT,
            verified_by INTEGER,
            notes TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, student_id),
            FOREIGN KEY(session_id) REFERENCES examination_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(verified_by) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_candidates_session ON session_candidates(session_id);
        CREATE INDEX IF NOT EXISTS idx_attendance_session ON session_attendance(session_id);
        CREATE INDEX IF NOT EXISTS idx_exam_sessions_date ON examination_sessions(session_date);
    """)
    connection.commit()
    connection.close()


def _audit(connection, action, entity, entity_id, summary):
    connection.execute("""
        INSERT INTO audit_events(actor_user_id, action, entity_type, entity_id, summary)
        VALUES (?, ?, ?, ?, ?)
    """, (session.get("user_id"), action, entity, str(entity_id), summary))


def _require_admin():
    return "user_id" in session and session.get("role") == "admin"


def _require_staff():
    return "user_id" in session and session.get("role") in {"admin", "invigilator"}


@operations_bp.before_request
def prepare():
    global SCHEMA_READY
    if not _require_staff():
        return redirect(url_for("login"))
    if not SCHEMA_READY:
        ensure_schema()
        SCHEMA_READY = True


@operations_bp.get("/")
def workspace():
    connection = db()
    units = connection.execute("SELECT * FROM academic_units ORDER BY unit_code").fetchall()
    students = connection.execute("""
        SELECT s.id, s.student_number, s.first_name, s.last_name, s.course
        FROM students s ORDER BY s.student_number
    """).fetchall()
    venues = connection.execute("SELECT * FROM venues WHERE active=1 ORDER BY venue_code").fetchall()
    invigilators = connection.execute("""
        SELECT id, employee_number, first_name, last_name
        FROM invigilators WHERE status='active' ORDER BY employee_number
    """).fetchall()
    sessions = connection.execute("""
        SELECT es.*, e.course_code, e.examination_name, v.venue_code, v.room_name,
               (SELECT COUNT(*) FROM session_candidates c WHERE c.session_id=es.id) AS candidate_count
        FROM examination_sessions es
        JOIN examinations e ON e.id=es.examination_id
        LEFT JOIN venues v ON v.id=es.venue_id
        ORDER BY es.session_date DESC, es.start_time DESC
    """).fetchall()
    exams = connection.execute("SELECT id, course_code, examination_name FROM examinations ORDER BY examination_date DESC").fetchall()
    connection.close()
    return render_template("operations_workspace.html", units=units, students=students,
                           venues=venues, invigilators=invigilators, sessions=sessions,
                           exams=exams, today=date.today().isoformat(), is_admin=_require_admin())


@operations_bp.post("/units")
def create_unit():
    if not _require_admin():
        return redirect(url_for("login"))
    code = (request.form.get("unit_code") or "").strip().upper()
    name = " ".join((request.form.get("unit_name") or "").split())
    department = " ".join((request.form.get("department") or "").split())
    faculty = " ".join((request.form.get("faculty") or "").split())
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9./_-]{1,24}", code) or not name:
        flash("Enter a valid unit code and unit name.", "error")
        return redirect(url_for("operations.workspace"))
    connection = db()
    try:
        cursor = connection.execute("""
            INSERT INTO academic_units(unit_code, unit_name, department, faculty)
            VALUES (?, ?, ?, ?)
        """, (code, name[:160], department[:160] or None, faculty[:160] or None))
        _audit(connection, "create", "academic_unit", cursor.lastrowid, f"Created unit {code}.")
        connection.commit()
        flash("Academic unit created.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("That unit code already exists.", "error")
    finally:
        connection.close()
    return redirect(url_for("operations.workspace"))


@operations_bp.post("/enrolments")
def enrol_student():
    if not _require_admin():
        return redirect(url_for("login"))
    try:
        student_id = int(request.form.get("student_id", ""))
        unit_id = int(request.form.get("unit_id", ""))
    except ValueError:
        flash("Choose a valid student and academic unit.", "error")
        return redirect(url_for("operations.workspace"))
    year = (request.form.get("academic_year") or "").strip()
    semester = (request.form.get("semester") or "").strip()
    if not year or not semester:
        flash("Academic year and semester are required.", "error")
        return redirect(url_for("operations.workspace"))
    connection = db()
    student = connection.execute("""
        SELECT s.id, COALESCE(p.academic_status,'active') AS academic_status
        FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id WHERE s.id=?
    """, (student_id,)).fetchone()
    unit = connection.execute("SELECT id FROM academic_units WHERE id=? AND active=1", (unit_id,)).fetchone()
    if not student or not unit or student["academic_status"] != "active":
        connection.close()
        flash("Only active students can be enrolled in an active unit.", "error")
        return redirect(url_for("operations.workspace"))
    try:
        cursor = connection.execute("""
            INSERT INTO student_unit_enrolments(student_id, unit_id, academic_year, semester)
            VALUES (?, ?, ?, ?)
        """, (student_id, unit_id, year[:20], semester[:40]))
        _audit(connection, "create", "student_unit_enrolment", cursor.lastrowid,
               f"Enrolled student ID {student_id} in unit ID {unit_id} for {year}, {semester}.")
        connection.commit()
        flash("Student enrolment recorded.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("This student is already enrolled in that unit, academic year and semester.", "error")
    finally:
        connection.close()
    return redirect(url_for("operations.workspace"))


@operations_bp.post("/venues")
def create_venue():
    if not _require_admin():
        return redirect(url_for("login"))
    code = (request.form.get("venue_code") or "").strip().upper()
    room = " ".join((request.form.get("room_name") or "").split())
    building = " ".join((request.form.get("building") or "").split())
    try:
        capacity = int(request.form.get("capacity", ""))
        if capacity < 1 or capacity > 10000 or not code or not room:
            raise ValueError
    except ValueError:
        flash("Enter a venue code, room name and capacity between 1 and 10,000.", "error")
        return redirect(url_for("operations.workspace"))
    connection = db()
    try:
        cursor = connection.execute("""
            INSERT INTO venues(venue_code, building, room_name, capacity)
            VALUES (?, ?, ?, ?)
        """, (code[:30], building[:100] or None, room[:100], capacity))
        _audit(connection, "create", "venue", cursor.lastrowid, f"Created venue {code}.")
        connection.commit()
        flash("Examination venue created.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("That venue code already exists.", "error")
    finally:
        connection.close()
    return redirect(url_for("operations.workspace"))


@operations_bp.post("/sessions")
def create_session():
    if not _require_admin():
        return redirect(url_for("login"))
    form = request.form
    code = (form.get("session_code") or "").strip().upper()
    try:
        examination_id = int(form.get("examination_id", ""))
        unit_id = int(form.get("unit_id", "")) if form.get("unit_id") else None
        venue_id = int(form.get("venue_id", "")) if form.get("venue_id") else None
        capacity = int(form.get("capacity", "0"))
        session_date = datetime.strptime(form.get("session_date", ""), "%Y-%m-%d").date()
        start = datetime.strptime(form.get("start_time", ""), "%H:%M").time()
        end = datetime.strptime(form.get("end_time", ""), "%H:%M").time()
        if end <= start or not code:
            raise ValueError
    except (ValueError, TypeError):
        flash("Complete the session details and ensure the end time is after the start time.", "error")
        return redirect(url_for("operations.workspace"))
    year = (form.get("academic_year") or "").strip()
    semester = (form.get("semester") or "").strip()
    if not year or not semester:
        flash("Academic year and semester are required.", "error")
        return redirect(url_for("operations.workspace"))
    connection = db()
    exam = connection.execute("SELECT id FROM examinations WHERE id=?", (examination_id,)).fetchone()
    unit = connection.execute("SELECT id FROM academic_units WHERE id=? AND active=1", (unit_id,)).fetchone() if unit_id else None
    venue = connection.execute("SELECT capacity FROM venues WHERE id=? AND active=1", (venue_id,)).fetchone() if venue_id else None
    if not exam or (unit_id and not unit) or (venue_id and not venue):
        connection.close()
        flash("Select an existing examination, active unit and active venue.", "error")
        return redirect(url_for("operations.workspace"))
    if venue and capacity > venue["capacity"]:
        connection.close()
        flash("Expected candidate count cannot exceed venue capacity.", "error")
        return redirect(url_for("operations.workspace"))
    try:
        cursor = connection.execute("""
            INSERT INTO examination_sessions
            (session_code, examination_id, unit_id, academic_year, semester, venue_id,
             session_date, start_time, end_time, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (code, examination_id, unit_id, year[:20], semester[:40], venue_id,
              session_date.isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M"), session.get("user_id")))
        session_id = cursor.lastrowid
        # Candidate list is derived from actual active student enrolments, not a demo list.
        if unit_id:
            candidates = connection.execute("""
                SELECT e.student_id FROM student_unit_enrolments e
                JOIN students s ON s.id=e.student_id
                LEFT JOIN student_profiles p ON p.student_id=s.id
                WHERE e.unit_id=? AND e.academic_year=? AND e.semester=?
                  AND e.enrolment_status='registered'
                  AND COALESCE(p.academic_status,'active')='active'
            """, (unit_id, year, semester)).fetchall()
            for candidate in candidates:
                connection.execute("""
                    INSERT INTO session_candidates(session_id, student_id, eligibility_status)
                    VALUES (?, ?, 'eligible')
                """, (session_id, candidate["student_id"]))
        _audit(connection, "create", "examination_session", session_id,
               f"Created examination session {code}; candidate list derived from registered enrolments.")
        connection.commit()
        flash(f"Examination session created with {len(candidates) if unit_id else 0} eligible candidate(s).", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("Session code already exists or the session conflicts with a database constraint.", "error")
    finally:
        connection.close()
    return redirect(url_for("operations.workspace"))


@operations_bp.post("/sessions/<int:session_id>/assign-invigilator")
def assign_invigilator(session_id):
    if not _require_admin():
        return redirect(url_for("login"))
    try:
        invigilator_id = int(request.form.get("invigilator_id", ""))
    except ValueError:
        flash("Choose a valid invigilator.", "error")
        return redirect(url_for("operations.workspace"))
    connection = db()
    try:
        cursor = connection.execute("""
            INSERT INTO session_invigilators(session_id, invigilator_id) VALUES (?, ?)
        """, (session_id, invigilator_id))
        _audit(connection, "assign", "session_invigilator", cursor.lastrowid,
               f"Assigned invigilator {invigilator_id} to session {session_id}.")
        connection.commit()
        flash("Invigilator assigned.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("Assignment is invalid or already exists.", "error")
    finally:
        connection.close()
    return redirect(url_for("operations.workspace"))


@operations_bp.get("/sessions/<int:session_id>/attendance")
def attendance(session_id):
    connection = db()
    session_row = connection.execute("""
        SELECT es.*, e.course_code, e.examination_name, v.venue_code, v.room_name
        FROM examination_sessions es JOIN examinations e ON e.id=es.examination_id
        LEFT JOIN venues v ON v.id=es.venue_id WHERE es.id=?
    """, (session_id,)).fetchone()
    if not session_row:
        connection.close()
        flash("Examination session not found.", "error")
        return redirect(url_for("operations.workspace"))
    if session.get("role") == "invigilator":
        assignment = connection.execute("""
            SELECT 1 FROM session_invigilators si
            JOIN invigilators i ON i.id=si.invigilator_id
            WHERE si.session_id=? AND i.user_id=?
        """, (session_id, session.get("user_id"))).fetchone()
        if not assignment:
            connection.close()
            flash("You are not assigned to this examination session.", "error")
            return redirect(url_for("invigilator_dashboard"))
    candidates = connection.execute("""
        SELECT c.student_id, c.eligibility_status, c.eligibility_note, c.seat_label,
               s.student_number, s.first_name, s.last_name, a.status, a.check_in_at,
               a.check_out_at, a.verification_method, a.verification_status
        FROM session_candidates c JOIN students s ON s.id=c.student_id
        LEFT JOIN session_attendance a ON a.session_id=c.session_id AND a.student_id=c.student_id
        WHERE c.session_id=? ORDER BY s.student_number
    """, (session_id,)).fetchall()
    connection.close()
    return render_template("session_attendance.html", exam_session=session_row, candidates=candidates)


@operations_bp.post("/sessions/<int:session_id>/attendance/<int:student_id>")
def record_attendance(session_id, student_id):
    if not _require_staff():
        return redirect(url_for("login"))
    connection = db()
    session_row = connection.execute("SELECT * FROM examination_sessions WHERE id=?", (session_id,)).fetchone()
    if not session_row:
        connection.close()
        flash("Examination session not found.", "error")
        return redirect(url_for("operations.workspace"))
    if session.get("role") == "invigilator":
        assignment = connection.execute("""
            SELECT 1 FROM session_invigilators si JOIN invigilators i ON i.id=si.invigilator_id
            WHERE si.session_id=? AND i.user_id=?
        """, (session_id, session.get("user_id"))).fetchone()
        if not assignment:
            connection.close()
            flash("You are not assigned to this examination session.", "error")
            return redirect(url_for("invigilator_dashboard"))
    candidate = connection.execute("""
        SELECT 1 FROM session_candidates WHERE session_id=? AND student_id=?
          AND eligibility_status='eligible'
    """, (session_id, student_id)).fetchone()
    if not candidate:
        connection.close()
        flash("Attendance cannot be recorded: this student is not an eligible candidate for the session.", "error")
        return redirect(url_for("operations.attendance", session_id=session_id))
    event = (request.form.get("event_type") or "").strip()
    method = (request.form.get("verification_method") or "").strip()
    notes = " ".join((request.form.get("notes") or "").split())[:500]
    if event not in {"check_in", "check_out"} or method not in {"manual", "student_card"}:
        connection.close()
        flash("Choose a supported attendance event and verification method.", "error")
        return redirect(url_for("operations.attendance", session_id=session_id))
    now = datetime.now().isoformat(timespec="seconds")
    current = connection.execute("""
        SELECT * FROM session_attendance WHERE session_id=? AND student_id=?
    """, (session_id, student_id)).fetchone()
    if event == "check_in":
        if current and current["check_in_at"]:
            connection.close()
            flash("A check-in is already recorded. Duplicate check-in was prevented.", "error")
            return redirect(url_for("operations.attendance", session_id=session_id))
        status = "late" if now[11:16] > session_row["start_time"] else "present"
        connection.execute("""
            INSERT INTO session_attendance
            (session_id, student_id, status, check_in_at, verification_method,
             verification_status, verified_by, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, 'verified', ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id, student_id) DO UPDATE SET
              status=excluded.status, check_in_at=excluded.check_in_at,
              verification_method=excluded.verification_method,
              verification_status='verified', verified_by=excluded.verified_by,
              notes=excluded.notes, updated_at=CURRENT_TIMESTAMP
        """, (session_id, student_id, status, now, method, session.get("user_id"), notes or None))
    else:
        if not current or not current["check_in_at"]:
            connection.close()
            flash("A check-out requires an existing check-in.", "error")
            return redirect(url_for("operations.attendance", session_id=session_id))
        if current["check_out_at"]:
            connection.close()
            flash("A check-out is already recorded. Duplicate check-out was prevented.", "error")
            return redirect(url_for("operations.attendance", session_id=session_id))
        connection.execute("""
            UPDATE session_attendance SET check_out_at=?, notes=COALESCE(?, notes),
                updated_at=CURRENT_TIMESTAMP WHERE session_id=? AND student_id=?
        """, (now, notes or None, session_id, student_id))
    connection.execute("""
        INSERT INTO attendance_events(session_id, student_id, event_type, verification_method,
            verification_status, recorded_by, notes)
        VALUES (?, ?, ?, ?, 'verified', ?, ?)
    """, (session_id, student_id, event, method, session.get("user_id"), notes or None))
    _audit(connection, event, "session_attendance", f"{session_id}:{student_id}",
           f"{event.replace('_',' ')} recorded using {method} verification.")
    connection.commit()
    connection.close()
    flash("Attendance event recorded and audit logged.", "success")
    return redirect(url_for("operations.attendance", session_id=session_id))


@operations_bp.post("/sessions/<int:session_id>/candidates/import-enrolments")
def refresh_candidates(session_id):
    if not _require_admin():
        return redirect(url_for("login"))
    connection = db()
    session_row = connection.execute("SELECT * FROM examination_sessions WHERE id=?", (session_id,)).fetchone()
    if not session_row or not session_row["unit_id"]:
        connection.close()
        flash("This session has no linked academic unit.", "error")
        return redirect(url_for("operations.workspace"))
    candidates = connection.execute("""
        SELECT e.student_id FROM student_unit_enrolments e
        JOIN students s ON s.id=e.student_id
        LEFT JOIN student_profiles p ON p.student_id=s.id
        WHERE e.unit_id=? AND e.academic_year=? AND e.semester=?
          AND e.enrolment_status='registered'
          AND COALESCE(p.academic_status,'active')='active'
    """, (session_row["unit_id"], session_row["academic_year"], session_row["semester"])).fetchall()
    added = 0
    for candidate in candidates:
        cursor = connection.execute("""
            INSERT OR IGNORE INTO session_candidates(session_id, student_id, eligibility_status)
            VALUES (?, ?, 'eligible')
        """, (session_id, candidate["student_id"]))
        added += cursor.rowcount
    _audit(connection, "refresh_candidates", "examination_session", session_id,
           f"Added {added} eligible candidates from current enrolments.")
    connection.commit()
    connection.close()
    flash(f"Candidate list refreshed. {added} new eligible candidate(s) added.", "success")
    return redirect(url_for("operations.workspace"))
