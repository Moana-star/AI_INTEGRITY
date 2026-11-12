"""Evidence-controlled examination incident review workflow."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from pathlib import Path
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from modules.institutional_registry import ensure_schema as ensure_registry_schema

integrity_bp = Blueprint("integrity", __name__, url_prefix="/integrity")
DATABASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "exam_integrity.db")
EVIDENCE_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance", "evidence")
MAX_EVIDENCE_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
CASE_STATUSES = {
    "reported", "under_review", "student_response_requested",
    "reviewed", "resolved", "dismissed", "referred"
}


def db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema():
    connection = db()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS incident_case_workflow (
            incident_id INTEGER PRIMARY KEY,
            case_status TEXT NOT NULL DEFAULT 'reported'
                CHECK(case_status IN ('reported','under_review','student_response_requested','reviewed','resolved','dismissed','referred')),
            student_response_due TEXT,
            updated_by INTEGER,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
            FOREIGN KEY(updated_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS incident_review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            actor_user_id INTEGER NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            review_note TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
            FOREIGN KEY(actor_user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS incident_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            uploaded_by INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            media_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
            FOREIGN KEY(uploaded_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS evidence_access_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evidence_id INTEGER NOT NULL,
            actor_user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(evidence_id) REFERENCES incident_evidence(id) ON DELETE CASCADE,
            FOREIGN KEY(actor_user_id) REFERENCES users(id)
        );
    """)
    connection.execute("""
        INSERT OR IGNORE INTO incident_case_workflow(incident_id, case_status)
        SELECT id, CASE WHEN status='resolved' THEN 'resolved' ELSE 'reported' END FROM incidents
    """)
    connection.commit()
    connection.close()


SCHEMA_READY = False


def staff():
    return "user_id" in session and session.get("role") in {"admin", "invigilator"}


@integrity_bp.before_request
def prepare():
    global SCHEMA_READY
    if not staff():
        return redirect(url_for("login"))
    if not SCHEMA_READY:
        ensure_registry_schema()
        ensure_schema()
        SCHEMA_READY = True


@integrity_bp.get("/incidents/<int:incident_id>")
def case_detail(incident_id):
    connection = db()
    incident = connection.execute("""
        SELECT i.*, s.student_number, s.first_name, s.last_name, e.course_code,
               e.examination_name, w.case_status, w.student_response_due
        FROM incidents i
        LEFT JOIN students s ON s.id=i.student_id
        LEFT JOIN examinations e ON e.id=i.examination_id
        LEFT JOIN incident_case_workflow w ON w.incident_id=i.id
        WHERE i.id=?
    """, (incident_id,)).fetchone()
    if not incident:
        connection.close()
        abort(404)
    if session.get("role") == "invigilator":
        assigned = connection.execute("""
            SELECT 1 FROM examinations e
            JOIN invigilators v ON v.id=e.invigilator_id
            WHERE e.id=? AND v.user_id=?
        """, (incident["examination_id"], session.get("user_id"))).fetchone()
        if not assigned:
            connection.close()
            abort(403)
    evidence = connection.execute("""
        SELECT id, original_filename, media_type, file_size, sha256, description, created_at
        FROM incident_evidence WHERE incident_id=? ORDER BY created_at DESC
    """, (incident_id,)).fetchall()
    events = connection.execute("""
        SELECT r.*, u.username FROM incident_review_events r
        JOIN users u ON u.id=r.actor_user_id
        WHERE r.incident_id=? ORDER BY r.created_at DESC
    """, (incident_id,)).fetchall()
    student_response = connection.execute("""
        SELECT response_text, submitted_at FROM incident_case_responses WHERE incident_id=?
    """, (incident_id,)).fetchone()
    connection.close()
    return render_template("incident_case.html", incident=incident, evidence=evidence,
                           events=events, student_response=student_response,
                           statuses=sorted(CASE_STATUSES), is_admin=session.get("role")=="admin")


@integrity_bp.post("/incidents/<int:incident_id>/status")
def update_case_status(incident_id):
    if session.get("role") != "admin":
        abort(403)
    status = (request.form.get("case_status") or "").strip()
    note = " ".join((request.form.get("review_note") or "").split())
    due = (request.form.get("student_response_due") or "").strip() or None
    if status not in CASE_STATUSES or len(note) < 10:
        flash("Choose a valid review status and provide a meaningful review note (at least 10 characters).", "error")
        return redirect(url_for("integrity.case_detail", incident_id=incident_id))
    connection = db()
    exists = connection.execute("SELECT id FROM incidents WHERE id=?", (incident_id,)).fetchone()
    if not exists:
        connection.close()
        abort(404)
    current = connection.execute("SELECT case_status FROM incident_case_workflow WHERE incident_id=?", (incident_id,)).fetchone()
    previous = current["case_status"] if current else "reported"
    connection.execute("""
        INSERT INTO incident_case_workflow(incident_id, case_status, student_response_due, updated_by, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(incident_id) DO UPDATE SET case_status=excluded.case_status,
          student_response_due=excluded.student_response_due, updated_by=excluded.updated_by,
          updated_at=CURRENT_TIMESTAMP
    """, (incident_id, status, due, session["user_id"]))
    connection.execute("""
        INSERT INTO incident_review_events(incident_id, actor_user_id, from_status, to_status, review_note)
        VALUES (?, ?, ?, ?, ?)
    """, (incident_id, session["user_id"], previous, status, note))
    if status in {"resolved", "dismissed", "referred"}:
        legacy_status = "resolved"
        connection.execute("UPDATE incidents SET status=? WHERE id=?", (legacy_status, incident_id))
    elif status in {"reported", "under_review", "student_response_requested", "reviewed"}:
        connection.execute("UPDATE incidents SET status='open' WHERE id=?", (incident_id,))
    connection.execute("""
        INSERT INTO audit_events(actor_user_id, action, entity_type, entity_id, summary)
        VALUES (?, 'review_status', 'incident', ?, ?)
    """, (session["user_id"], str(incident_id), f"Case status changed from {previous} to {status}."))
    connection.commit()
    connection.close()
    flash("Incident review status and audit history updated.", "success")
    return redirect(url_for("integrity.case_detail", incident_id=incident_id))


@integrity_bp.post("/incidents/<int:incident_id>/evidence")
def upload_evidence(incident_id):
    upload = request.files.get("evidence")
    description = " ".join((request.form.get("description") or "").split())
    if not upload or not upload.filename or not description:
        flash("Choose an evidence file and provide a description.", "error")
        return redirect(url_for("integrity.case_detail", incident_id=incident_id))
    original = Path(upload.filename).name[:180]
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        flash("Only PDF, PNG and JPEG evidence files are accepted.", "error")
        return redirect(url_for("integrity.case_detail", incident_id=incident_id))
    raw = upload.read(MAX_EVIDENCE_BYTES + 1)
    if not raw or len(raw) > MAX_EVIDENCE_BYTES:
        flash("Evidence must be non-empty and no larger than 5 MB.", "error")
        return redirect(url_for("integrity.case_detail", incident_id=incident_id))
    if extension == ".pdf" and not raw.startswith(b"%PDF-"):
        flash("The uploaded file does not have a valid PDF signature.", "error")
        return redirect(url_for("integrity.case_detail", incident_id=incident_id))
    if extension in {".jpg", ".jpeg"} and not raw.startswith(b"\xff\xd8\xff"):
        flash("The uploaded file does not have a valid JPEG signature.", "error")
        return redirect(url_for("integrity.case_detail", incident_id=incident_id))
    if extension == ".png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        flash("The uploaded file does not have a valid PNG signature.", "error")
        return redirect(url_for("integrity.case_detail", incident_id=incident_id))
    connection = db()
    incident = connection.execute("SELECT examination_id FROM incidents WHERE id=?", (incident_id,)).fetchone()
    if not incident:
        connection.close()
        abort(404)
    if session.get("role") == "invigilator":
        assigned = connection.execute("""
            SELECT 1 FROM examinations e JOIN invigilators v ON v.id=e.invigilator_id
            WHERE e.id=? AND v.user_id=?
        """, (incident["examination_id"], session.get("user_id"))).fetchone()
        if not assigned:
            connection.close()
            abort(403)
    os.makedirs(EVIDENCE_ROOT, mode=0o700, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{extension}"
    target = os.path.join(EVIDENCE_ROOT, stored)
    with open(target, "xb") as handle:
        handle.write(raw)
    media_type = {".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg"}[extension]
    digest = hashlib.sha256(raw).hexdigest()
    try:
        connection.execute("""
            INSERT INTO incident_evidence(incident_id, uploaded_by, original_filename,
                stored_filename, media_type, file_size, sha256, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (incident_id, session["user_id"], original, stored, media_type,
              len(raw), digest, description[:500]))
        connection.execute("""
            INSERT INTO audit_events(actor_user_id, action, entity_type, entity_id, summary)
            VALUES (?, 'evidence_upload', 'incident', ?, ?)
        """, (session["user_id"], str(incident_id), f"Evidence uploaded: {original}; SHA-256 {digest}."))
        connection.commit()
    except Exception:
        connection.rollback()
        connection.close()
        os.remove(target)
        raise
    connection.close()
    flash("Evidence stored outside the public web directory and its SHA-256 recorded.", "success")
    return redirect(url_for("integrity.case_detail", incident_id=incident_id))


@integrity_bp.get("/evidence/<int:evidence_id>")
def download_evidence(evidence_id):
    if session.get("role") != "admin":
        abort(403)
    connection = db()
    record = connection.execute("SELECT * FROM incident_evidence WHERE id=?", (evidence_id,)).fetchone()
    connection.close()
    if not record:
        abort(404)
    path = os.path.join(EVIDENCE_ROOT, record["stored_filename"])
    if not os.path.isfile(path):
        abort(404)
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest != record["sha256"]:
        current_app.logger.error("Evidence checksum mismatch for evidence ID %s", evidence_id)
        abort(500)
    audit = db()
    audit.execute("INSERT INTO evidence_access_events(evidence_id, actor_user_id, action) VALUES (?, ?, 'download')",
                  (evidence_id, session["user_id"]))
    audit.execute("INSERT INTO audit_events(actor_user_id, action, entity_type, entity_id, summary) VALUES (?, 'evidence_download', 'incident_evidence', ?, 'Evidence file downloaded by authorized administrator.')",
                  (session["user_id"], str(evidence_id)))
    audit.commit()
    audit.close()
    return send_file(path, mimetype=record["media_type"], as_attachment=True,
                     download_name=record["original_filename"], conditional=True)
