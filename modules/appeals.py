"""Independent student appeals for examination incident outcomes.

Appeals are separate from the original incident review. The original reporter
and the last recorded case reviewer cannot decide the appeal. An appeal outcome
is recorded separately and never silently rewrites the original case record.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from modules.integrity import ensure_schema as ensure_integrity_schema
from modules.institutional_registry import ensure_schema as ensure_registry_schema

appeals_bp = Blueprint("appeals", __name__, url_prefix="/appeals")
DATABASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "exam_integrity.db")
FINAL_CASE_STATUSES = {"resolved", "dismissed", "referred"}
APPEAL_OUTCOMES = {"decision_upheld", "decision_overturned", "referred"}


def within_senate_review_period(communicated_at, submitted_at):
    """The handbook permits review within 21 calendar days after communication."""
    from datetime import date
    try:
        communicated = date.fromisoformat(communicated_at)
        submitted = date.fromisoformat(submitted_at)
    except (TypeError, ValueError):
        return False
    return communicated <= submitted <= communicated + timedelta(days=21)


def db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema():
    connection = db()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS incident_appeals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL UNIQUE,
            student_id INTEGER NOT NULL,
            appeal_text TEXT NOT NULL,
            appeal_status TEXT NOT NULL DEFAULT 'submitted'
                CHECK(appeal_status IN ('submitted','under_review','decision_upheld','decision_overturned','referred')),
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_by INTEGER,
            decision_reason TEXT,
            decided_at TEXT,
            FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY(reviewed_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS incident_appeal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appeal_id INTEGER NOT NULL,
            actor_user_id INTEGER,
            actor_student_id INTEGER,
            from_status TEXT,
            to_status TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(appeal_id) REFERENCES incident_appeals(id) ON DELETE CASCADE,
            FOREIGN KEY(actor_user_id) REFERENCES users(id),
            FOREIGN KEY(actor_student_id) REFERENCES students(id),
            CHECK ((actor_user_id IS NOT NULL AND actor_student_id IS NULL) OR
                   (actor_user_id IS NULL AND actor_student_id IS NOT NULL))
        );
        CREATE TRIGGER IF NOT EXISTS incident_appeal_events_no_update
        BEFORE UPDATE ON incident_appeal_events
        BEGIN SELECT RAISE(ABORT, 'Appeal history events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS incident_appeal_events_no_delete
        BEFORE DELETE ON incident_appeal_events
        BEGIN SELECT RAISE(ABORT, 'Appeal history events are append-only'); END;
        CREATE TABLE IF NOT EXISTS senate_disciplinary_verdicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL UNIQUE,
            student_id INTEGER NOT NULL,
            verdict_reference TEXT NOT NULL,
            verdict_summary TEXT NOT NULL,
            communicated_at TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            recorded_by INTEGER NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES incidents(id),
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(recorded_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS senate_review_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verdict_id INTEGER NOT NULL UNIQUE,
            student_id INTEGER NOT NULL,
            request_text TEXT NOT NULL,
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'submitted'
                CHECK(status IN ('submitted','referred_to_senate','decision_recorded')),
            FOREIGN KEY(verdict_id) REFERENCES senate_disciplinary_verdicts(id),
            FOREIGN KEY(student_id) REFERENCES students(id)
        );
        CREATE TABLE IF NOT EXISTS senate_review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            actor_user_id INTEGER,
            actor_student_id INTEGER,
            from_status TEXT,
            to_status TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(request_id) REFERENCES senate_review_requests(id),
            FOREIGN KEY(actor_user_id) REFERENCES users(id),
            FOREIGN KEY(actor_student_id) REFERENCES students(id),
            CHECK ((actor_user_id IS NOT NULL AND actor_student_id IS NULL) OR
                   (actor_user_id IS NULL AND actor_student_id IS NOT NULL))
        );
        CREATE TRIGGER IF NOT EXISTS senate_review_events_no_update
        BEFORE UPDATE ON senate_review_events
        BEGIN SELECT RAISE(ABORT, 'Senate review events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS senate_review_events_no_delete
        BEFORE DELETE ON senate_review_events
        BEGIN SELECT RAISE(ABORT, 'Senate review events are append-only'); END;
    """)
    connection.commit()
    connection.close()


@appeals_bp.before_request
def prepare():
    role = session.get("role")
    if role not in {"admin", "registrar", "examination_officer", "student"}:
        abort(403)
    ensure_registry_schema()
    ensure_integrity_schema()
    ensure_schema()



@appeals_bp.post("/senate-verdicts/<int:incident_id>")
def record_senate_verdict(incident_id):
    if session.get("role") not in {"admin", "registrar"}:
        abort(403)
    from datetime import date
    communicated_at = (request.form.get("communicated_at") or "").strip()
    verdict_reference = " ".join((request.form.get("verdict_reference") or "").split())[:120]
    verdict_summary = " ".join((request.form.get("verdict_summary") or "").split())[:1000]
    source_reference = " ".join((request.form.get("source_reference") or "").split())[:500]
    try:
        date.fromisoformat(communicated_at)
    except ValueError:
        flash("Enter the date the Senate verdict was communicated to the student.", "error")
        return redirect(url_for("appeals.senate_review_queue"))
    if len(verdict_reference) < 3 or len(verdict_summary) < 20 or len(source_reference) < 8:
        flash("Provide the official verdict reference, summary and source record.", "error")
        return redirect(url_for("appeals.senate_review_queue"))
    connection = db()
    incident = connection.execute("SELECT student_id FROM incidents WHERE id=?", (incident_id,)).fetchone()
    if not incident:
        connection.close()
        abort(404)
    try:
        cursor = connection.execute("""
            INSERT INTO senate_disciplinary_verdicts
                (incident_id,student_id,verdict_reference,verdict_summary,communicated_at,source_reference,recorded_by)
            VALUES(?,?,?,?,?,?,?)
        """, (incident_id,incident["student_id"],verdict_reference,verdict_summary,
              communicated_at,source_reference,session["user_id"]))
        verdict_id = cursor.lastrowid
        connection.execute("""
            INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
            VALUES(?,'record_senate_verdict','senate_disciplinary_verdict',?,
                   'Recorded Senate verdict communication date and source reference.')
        """, (session["user_id"],str(verdict_id)))
        connection.commit()
        flash("Senate verdict communication record saved. The 21-day review period is now traceable.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("A Senate verdict is already recorded for this incident. Use the formal correction process rather than overwriting it.", "error")
    finally:
        connection.close()
    return redirect(url_for("appeals.senate_review_queue"))


@appeals_bp.post("/senate-verdicts/<int:verdict_id>/review")
def submit_senate_review(verdict_id):
    if session.get("role") != "student" or not session.get("student_id"):
        abort(403)
    request_text = " ".join((request.form.get("request_text") or "").split())
    if not 50 <= len(request_text) <= 5000:
        flash("Your Senate review request must contain between 50 and 5,000 characters.", "error")
        return redirect(url_for("student_portal.portal"))
    connection = db()
    verdict = connection.execute("""
        SELECT * FROM senate_disciplinary_verdicts
        WHERE id=? AND student_id=?
    """, (verdict_id,session["student_id"])).fetchone()
    if not verdict:
        connection.close()
        abort(404)
    today = date.today().isoformat()
    if not within_senate_review_period(verdict["communicated_at"],today):
        connection.close()
        abort(403, description="The 21-calendar-day Senate review period has expired or the communication date is invalid.")
    try:
        cursor = connection.execute("""
            INSERT INTO senate_review_requests(verdict_id,student_id,request_text)
            VALUES(?,?,?)
        """, (verdict_id,session["student_id"],request_text))
        request_id = cursor.lastrowid
        connection.execute("""
            INSERT INTO senate_review_events
                (request_id,actor_student_id,from_status,to_status,reason)
            VALUES(?,?,NULL,'submitted','Student submitted a Senate verdict review request within the recorded 21-day period.')
        """, (request_id,session["student_id"]))
        connection.execute("""
            INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
            VALUES(NULL,'senate_review_submitted','senate_review_request',?,
                   'Student submitted a review request within the 21-day period.')
        """, (str(request_id),))
        connection.commit()
        flash("Your Senate review request has been recorded for institutional processing.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("A review request has already been submitted for this Senate verdict.", "error")
    finally:
        connection.close()
    return redirect(url_for("student_portal.portal"))


@appeals_bp.get("/senate-reviews")
def senate_review_queue():
    if session.get("role") not in {"admin", "registrar", "examination_officer"}:
        abort(403)
    connection = db()
    verdicts = connection.execute("""
        SELECT v.*,s.student_number,s.first_name,s.last_name,r.id AS request_id,
               r.request_text,r.status AS request_status,r.submitted_at
        FROM senate_disciplinary_verdicts v
        JOIN students s ON s.id=v.student_id
        LEFT JOIN senate_review_requests r ON r.verdict_id=v.id
        ORDER BY v.communicated_at DESC
    """).fetchall()
    connection.close()
    return render_template("senate_review_queue.html",verdicts=verdicts)


@appeals_bp.get("/")
def staff_queue():
    if session.get("role") not in {"admin", "examination_officer"}:
        abort(403)
    connection = db()
    appeals = connection.execute("""
        SELECT a.*, i.incident_type, i.severity, s.student_number,
               s.first_name, s.last_name, w.reported_by, w.updated_by AS original_reviewer
        FROM incident_appeals a
        JOIN incidents i ON i.id=a.incident_id
        JOIN students s ON s.id=a.student_id
        LEFT JOIN incident_case_workflow w ON w.incident_id=i.id
        ORDER BY CASE a.appeal_status WHEN 'submitted' THEN 0 WHEN 'under_review' THEN 1 ELSE 2 END,
                 a.submitted_at
    """).fetchall()
    connection.close()
    return render_template("appeal_queue.html", appeals=appeals)


@appeals_bp.post("/incidents/<int:incident_id>")
def submit_appeal(incident_id):
    if session.get("role") != "student" or not session.get("student_id"):
        abort(403)
    appeal_text = " ".join((request.form.get("appeal_text") or "").split())
    if not 50 <= len(appeal_text) <= 5000:
        flash("Your appeal must contain between 50 and 5,000 characters.", "error")
        return redirect(url_for("student_portal.portal"))
    connection = db()
    case = connection.execute("""
        SELECT w.case_status FROM incidents i
        JOIN incident_case_workflow w ON w.incident_id=i.id
        WHERE i.id=? AND i.student_id=?
    """, (incident_id,session["student_id"])).fetchone()
    if not case or case["case_status"] not in FINAL_CASE_STATUSES:
        connection.close()
        abort(403, description="An appeal can be submitted only for a final recorded case outcome belonging to the signed-in student.")
    try:
        cursor = connection.execute("""
            INSERT INTO incident_appeals(incident_id,student_id,appeal_text)
            VALUES(?,?,?)
        """, (incident_id,session["student_id"],appeal_text))
        appeal_id = cursor.lastrowid
        connection.execute("""
            INSERT INTO incident_appeal_events
                (appeal_id,actor_student_id,from_status,to_status,reason)
            VALUES(?,?,NULL,'submitted','Student submitted an appeal through the authenticated portal.')
        """, (appeal_id,session["student_id"]))
        connection.execute("""
            INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
            VALUES(NULL,'appeal_submitted','incident_appeal',?,
                   'Student submitted an appeal through their authenticated portal.')
        """, (str(appeal_id),))
        connection.commit()
        flash("Your appeal has been submitted as a separate review record.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("An appeal has already been submitted for this incident.", "error")
    finally:
        connection.close()
    return redirect(url_for("student_portal.portal"))


@appeals_bp.post("/<int:appeal_id>/decision")
def decide_appeal(appeal_id):
    if session.get("role") not in {"admin", "examination_officer"}:
        abort(403)
    outcome = (request.form.get("outcome") or "").strip()
    reason = " ".join((request.form.get("decision_reason") or "").split())
    if outcome not in APPEAL_OUTCOMES or len(reason) < 30:
        flash("Choose a valid appeal outcome and provide a reason of at least 30 characters.", "error")
        return redirect(url_for("appeals.staff_queue"))
    connection = db()
    appeal = connection.execute("""
        SELECT a.*, w.reported_by, w.updated_by AS original_reviewer
        FROM incident_appeals a
        LEFT JOIN incident_case_workflow w ON w.incident_id=a.incident_id
        WHERE a.id=?
    """, (appeal_id,)).fetchone()
    if not appeal:
        connection.close()
        abort(404)
    if appeal["reviewed_by"] is not None or session["user_id"] in {
        appeal["reported_by"], appeal["original_reviewer"]
    }:
        connection.close()
        abort(403, description="The original reporter or case reviewer cannot decide this appeal, and an appeal may be decided only once.")
    connection.execute("""
        UPDATE incident_appeals SET appeal_status=?, reviewed_by=?,
            decision_reason=?, decided_at=CURRENT_TIMESTAMP WHERE id=?
    """, (outcome,session["user_id"],reason,appeal_id))
    connection.execute("""
        INSERT INTO incident_appeal_events
            (appeal_id,actor_user_id,from_status,to_status,reason)
        VALUES(?,?,? ,?,?)
    """, (appeal_id,session["user_id"],appeal["appeal_status"],outcome,reason))
    connection.execute("""
        INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
        VALUES (?,'appeal_decided','incident_appeal',?,?)
    """, (session["user_id"],str(appeal_id),f"Independent appeal outcome recorded: {outcome}."))
    connection.commit()
    connection.close()
    flash("Independent appeal outcome recorded. The original incident record remains unchanged.", "success")
    return redirect(url_for("appeals.staff_queue"))
