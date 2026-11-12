"""Student self-service portal and controlled incident response."""
from __future__ import annotations

import os
import secrets
import sqlite3
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from modules.institutional_registry import ensure_schema as ensure_registry_schema
from modules.operations import ensure_schema as ensure_operations_schema
from modules.integrity import ensure_schema as ensure_integrity_schema

student_bp = Blueprint("student_portal", __name__, url_prefix="/student")
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
        CREATE TABLE IF NOT EXISTS student_portal_accounts (
            student_id INTEGER PRIMARY KEY,
            password_hash TEXT NOT NULL,
            must_change_password INTEGER NOT NULL DEFAULT 1 CHECK(must_change_password IN (0,1)),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS incident_case_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL UNIQUE,
            student_id INTEGER NOT NULL,
            response_text TEXT NOT NULL,
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        );
    """)
    connection.commit()
    connection.close()


def is_student():
    return session.get("role") == "student" and session.get("student_id")


@student_bp.before_request
def prepare():
    global SCHEMA_READY
    if not SCHEMA_READY:
        ensure_registry_schema()
        ensure_operations_schema()
        ensure_integrity_schema()
        ensure_schema()
        SCHEMA_READY = True


@student_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("student_login.html")
    admission = " ".join((request.form.get("admission_number") or "").split())
    password = request.form.get("password") or ""
    connection = db()
    account = connection.execute("""
        SELECT a.*, s.student_number FROM student_portal_accounts a
        JOIN students s ON s.id=a.student_id
        WHERE s.student_number=? AND a.active=1
    """, (admission,)).fetchone()
    valid = account and check_password_hash(account["password_hash"], password)
    if not valid:
        connection.close()
        return render_template("student_login.html", error="Admission number or password is incorrect.")
    connection.execute("UPDATE student_portal_accounts SET last_login_at=CURRENT_TIMESTAMP WHERE student_id=?",
                       (account["student_id"],))
    connection.commit()
    connection.close()
    session.clear()
    session["student_id"] = account["student_id"]
    session["username"] = account["student_number"]
    session["role"] = "student"
    if account["must_change_password"]:
        return redirect(url_for("student_portal.change_password"))
    return redirect(url_for("student_portal.portal"))


@student_bp.get("/portal")
def portal():
    if not is_student():
        return redirect(url_for("student_portal.login"))
    connection = db()
    student = connection.execute("""
        SELECT s.*, p.faculty, p.department, p.institutional_email, p.phone,
               COALESCE(p.academic_status,'active') AS academic_status
        FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id
        WHERE s.id=?
    """, (session["student_id"],)).fetchone()
    enrolments = connection.execute("""
        SELECT u.unit_code, u.unit_name, e.academic_year, e.semester, e.enrolment_status
        FROM student_unit_enrolments e JOIN academic_units u ON u.id=e.unit_id
        WHERE e.student_id=? ORDER BY e.academic_year DESC, e.semester, u.unit_code
    """, (session["student_id"],)).fetchall()
    examinations = connection.execute("""
        SELECT es.session_code, es.session_date, es.start_time, es.end_time, es.status,
               ex.course_code, ex.examination_name, v.venue_code, v.room_name,
               a.status AS attendance_status, a.check_in_at, a.check_out_at
        FROM session_candidates c
        JOIN examination_sessions es ON es.id=c.session_id
        JOIN examinations ex ON ex.id=es.examination_id
        LEFT JOIN venues v ON v.id=es.venue_id
        LEFT JOIN session_attendance a ON a.session_id=es.id AND a.student_id=c.student_id
        WHERE c.student_id=? ORDER BY es.session_date DESC, es.start_time
    """, (session["student_id"],)).fetchall()
    incidents = connection.execute("""
        SELECT i.id, i.incident_type, i.description, i.severity, i.reported_at,
               w.case_status, w.student_response_due, r.submitted_at AS response_submitted_at
        FROM incidents i LEFT JOIN incident_case_workflow w ON w.incident_id=i.id
        LEFT JOIN incident_case_responses r ON r.incident_id=i.id
        WHERE i.student_id=? ORDER BY i.reported_at DESC
    """, (session["student_id"],)).fetchall()
    account = connection.execute("SELECT must_change_password FROM student_portal_accounts WHERE student_id=?",
                                 (session["student_id"],)).fetchone()
    connection.close()
    return render_template("student_portal.html", student=student, enrolments=enrolments,
                           examinations=examinations, incidents=incidents,
                           must_change=bool(account["must_change_password"]))


@student_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    if not is_student():
        return redirect(url_for("student_portal.login"))
    if request.method == "GET":
        return render_template("student_change_password.html")
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""
    if len(password) < 12 or password != confirm:
        return render_template("student_change_password.html",
                               error="Use at least 12 characters and make sure both passwords match.")
    connection = db()
    connection.execute("""
        UPDATE student_portal_accounts SET password_hash=?, must_change_password=0
        WHERE student_id=?
    """, (generate_password_hash(password), session["student_id"]))
    connection.commit()
    connection.close()
    flash("Password changed successfully.", "success")
    return redirect(url_for("student_portal.portal"))


@student_bp.post("/incidents/<int:incident_id>/respond")
def respond_to_incident(incident_id):
    if not is_student():
        return redirect(url_for("student_portal.login"))
    response = " ".join((request.form.get("response_text") or "").split())
    if not 30 <= len(response) <= 5000:
        flash("Your response must contain between 30 and 5,000 characters.", "error")
        return redirect(url_for("student_portal.portal"))
    connection = db()
    case = connection.execute("""
        SELECT w.case_status FROM incidents i
        JOIN incident_case_workflow w ON w.incident_id=i.id
        WHERE i.id=? AND i.student_id=?
    """, (incident_id, session["student_id"])).fetchone()
    if not case or case["case_status"] != "student_response_requested":
        connection.close()
        abort(403)
    try:
        connection.execute("""
            INSERT INTO incident_case_responses(incident_id, student_id, response_text)
            VALUES (?, ?, ?)
        """, (incident_id, session["student_id"], response))
        connection.execute("""
            INSERT INTO audit_events(actor_user_id, action, entity_type, entity_id, summary)
            VALUES (NULL, 'student_response', 'incident', ?, 'Student submitted a response through the authenticated portal.')
        """, (str(incident_id),))
        connection.commit()
        flash("Your response has been submitted and cannot be silently overwritten.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("A response has already been submitted for this incident.", "error")
    finally:
        connection.close()
    return redirect(url_for("student_portal.portal"))


@student_bp.post("/admin/students/<int:student_id>/provision")
def provision_account(student_id):
    if session.get("role") != "admin" or not session.get("user_id"):
        abort(403)
    connection = db()
    student = connection.execute("SELECT student_number FROM students WHERE id=?", (student_id,)).fetchone()
    if not student:
        connection.close()
        abort(404)
    temporary_password = secrets.token_urlsafe(15)
    connection.execute("""
        INSERT INTO student_portal_accounts(student_id, password_hash, must_change_password, active)
        VALUES (?, ?, 1, 1)
        ON CONFLICT(student_id) DO UPDATE SET password_hash=excluded.password_hash,
          must_change_password=1, active=1
    """, (student_id, generate_password_hash(temporary_password)))
    connection.execute("""
        INSERT INTO audit_events(actor_user_id, action, entity_type, entity_id, summary)
        VALUES (?, 'provision_portal_access', 'student', ?, 'Student portal credentials provisioned or reset.')
    """, (session["user_id"], str(student_id)))
    connection.commit()
    connection.close()
    # Display once in the administrator's immediate response; never store it in a flash cookie or log.
    return render_template("student_portal_credential.html", admission_number=student["student_number"],
                           temporary_password=temporary_password)


@student_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))
