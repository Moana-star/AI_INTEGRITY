"""Institution-approved biometric enrolment and examination attendance integration.

No face image or template is persisted by EIMS. An approved provider owns
biometric templates and returns opaque references. The provider must be
configured by deployment code; there is deliberately no mock/default provider.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from flask import Blueprint, abort, current_app, flash, redirect, request, session, url_for
from modules.database import get_connection
from werkzeug.exceptions import HTTPException
from modules.biometric_verification import (
    BiometricProviderUnavailable,
    BiometricVerificationDisabled,
    verify_one_to_one,
)

biometric_attendance_bp = Blueprint("biometric_attendance", __name__, url_prefix="/biometric")
DATABASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "exam_integrity.db")
MAX_CAPTURE_BYTES = 5 * 1024 * 1024


def db():
    return get_connection(DATABASE)


def ensure_schema():
    connection = db()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS biometric_enrolments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL UNIQUE,
            provider_name TEXT NOT NULL,
            provider_reference TEXT NOT NULL UNIQUE,
            consent_record_id TEXT NOT NULL,
            approval_reference TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
            enrolled_by INTEGER NOT NULL,
            enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked_by INTEGER,
            revoked_at TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(enrolled_by) REFERENCES users(id),
            FOREIGN KEY(revoked_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS biometric_verification_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN ('verified','failed','manual_review','error')),
            provider_name TEXT,
            provider_reference TEXT,
            reason TEXT NOT NULL,
            recorded_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES examination_sessions(id),
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(recorded_by) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_biometric_events_session
            ON biometric_verification_events(session_id, created_at);
        CREATE TRIGGER IF NOT EXISTS biometric_events_no_update
        BEFORE UPDATE ON biometric_verification_events
        BEGIN SELECT RAISE(ABORT, 'Biometric verification history is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS biometric_events_no_delete
        BEFORE DELETE ON biometric_verification_events
        BEGIN SELECT RAISE(ABORT, 'Biometric verification history is append-only'); END;
    """)
    connection.commit()
    connection.close()


def _enabled():
    return (
        current_app.config.get("BIOMETRIC_ENABLED") is True
        and current_app.config.get("BIOMETRIC_INSTITUTIONAL_APPROVAL") is True
    )


def _provider():
    return current_app.config.get("BIOMETRIC_PROVIDER")


def _capture():
    uploaded = request.files.get("capture")
    if uploaded is None:
        raise ValueError("A live camera capture is required.")
    data = uploaded.stream.read(MAX_CAPTURE_BYTES + 1)
    if not data or len(data) > MAX_CAPTURE_BYTES:
        raise ValueError("Capture must be non-empty and no larger than 5 MiB.")
    if uploaded.mimetype not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("Use a JPEG, PNG or WebP image capture.")
    return data


@biometric_attendance_bp.before_request
def prepare():
    if "user_id" not in session or session.get("role") not in {
        "admin", "registrar", "examination_officer", "invigilator"
    }:
        abort(403)
    ensure_schema()


@biometric_attendance_bp.post("/students/<int:student_id>/enrol")
def enrol_student(student_id):
    """Enroll through the approved provider; only opaque provider reference is stored."""
    if session.get("role") not in {"admin", "registrar"}:
        abort(403)
    if not _enabled():
        abort(503, description="Biometric enrolment is disabled pending institutional approval.")
    provider = _provider()
    if provider is None or not callable(getattr(provider, "enrol_one_to_one", None)):
        abort(503, description="No approved provider with enrolment support is configured.")
    consent_id = (request.form.get("consent_record_id") or "").strip()
    approval_ref = (request.form.get("approval_reference") or "").strip()
    if not consent_id or len(approval_ref) < 8:
        abort(400, description="A consent/alternative-process record and approval reference are required.")
    capture = _capture()
    connection = db()
    student = connection.execute(
        "SELECT id FROM students WHERE id=?", (student_id,)
    ).fetchone()
    if not student:
        connection.close()
        abort(404)
    try:
        result = provider.enrol_one_to_one(
            capture=capture, student_reference=str(student_id),
            purpose="institution-approved-student-biometric-enrolment",
            consent_record_id=consent_id,
        )
        if not isinstance(result, dict) or not result.get("reference_id"):
            raise BiometricProviderUnavailable("Provider returned no valid enrolment reference.")
        provider_name = str(result.get("provider") or "approved-provider")[:100]
        provider_reference = str(result["reference_id"])[:255]
        connection.execute("""
            INSERT INTO biometric_enrolments
            (student_id,provider_name,provider_reference,consent_record_id,
             approval_reference,enrolled_by)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(student_id) DO UPDATE SET
              provider_name=excluded.provider_name,
              provider_reference=excluded.provider_reference,
              consent_record_id=excluded.consent_record_id,
              approval_reference=excluded.approval_reference,
              status='active', enrolled_by=excluded.enrolled_by,
              enrolled_at=CURRENT_TIMESTAMP, revoked_by=NULL, revoked_at=NULL
        """, (student_id,provider_name,provider_reference,consent_id,
              approval_ref,session["user_id"]))
        connection.execute("""
            INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
            VALUES (?,?,?,?,?)
        """, (session["user_id"],"biometric_enrolment","student",str(student_id),
              "Provider-managed biometric enrolment reference recorded; no face image stored by EIMS."))
        connection.commit()
        flash("Biometric enrolment completed by the configured provider.", "success")
    except HTTPException:
        raise
    except Exception:
        connection.rollback()
        current_app.logger.exception("Biometric enrolment failed")
        flash("Biometric enrolment failed. Use the approved manual identity process.", "error")
    finally:
        connection.close()
    return redirect(request.referrer or url_for("registry.students"))


@biometric_attendance_bp.post("/sessions/<int:session_id>/students/<int:student_id>/verify")
def verify_exam_attendance(session_id, student_id):
    """Verify one claimed identity and atomically record examination check-in."""
    if session.get("role") not in {"admin", "examination_officer", "invigilator"}:
        abort(403)
    if not _enabled():
        abort(503, description="Live biometric verification is disabled pending institutional approval.")
    provider = _provider()
    if provider is None:
        abort(503, description="No approved biometric provider is configured.")
    capture = _capture()
    connection = db()
    try:
        target = connection.execute("""
            SELECT es.*, c.eligibility_status, s.student_number,
                   be.provider_reference, be.provider_name, be.consent_record_id,
                   be.status AS enrolment_status
            FROM examination_sessions es
            JOIN session_candidates c ON c.session_id=es.id AND c.student_id=?
            JOIN students s ON s.id=c.student_id
            LEFT JOIN biometric_enrolments be ON be.student_id=s.id
            WHERE es.id=?
        """, (student_id,session_id)).fetchone()
        if not target:
            abort(404, description="Student is not a candidate for this examination session.")
        if session.get("role") == "invigilator":
            assigned = connection.execute("""
                SELECT 1 FROM session_invigilators si
                JOIN invigilators i ON i.id=si.invigilator_id
                WHERE si.session_id=? AND i.user_id=?
            """, (session_id,session["user_id"])).fetchone()
            if not assigned:
                abort(403)
        if target["status"] not in {"scheduled","active"}:
            abort(409, description="Attendance is closed for this examination session.")
        if target["eligibility_status"] != "eligible":
            abort(409, description="Candidate eligibility is not confirmed; refer to the examination officer.")
        if target["enrolment_status"] != "active" or not target["provider_reference"]:
            abort(409, description="No active biometric enrolment exists; use manual identity review.")
        current = connection.execute("""
            SELECT check_in_at FROM session_attendance
            WHERE session_id=? AND student_id=?
        """, (session_id,student_id)).fetchone()
        if current and current["check_in_at"]:
            abort(409, description="A check-in already exists for this student and session.")
        outcome = verify_one_to_one(
            provider=provider, capture=capture,
            reference_id=target["provider_reference"],
            purpose="examination-entry-identity-verification",
            consent_record_id=target["consent_record_id"],
            deployment_enabled=True, institutional_approval=True,
        )
        connection.execute("""
            INSERT INTO biometric_verification_events
            (session_id,student_id,outcome,provider_name,provider_reference,reason,recorded_by)
            VALUES (?,?,?,?,?,?,?)
        """, (session_id,student_id,outcome.status,outcome.provider,
              outcome.provider_reference,outcome.reason,session["user_id"]))
        if outcome.status != "verified":
            connection.commit()
            flash("Face verification was not confirmed. No attendance was recorded; use manual review.", "warning")
            return redirect(url_for("identity.session_identity",session_id=session_id))
        now_dt = datetime.now()
        scheduled_start = datetime.fromisoformat(
            f"{target['session_date']}T{target['start_time']}"
        )
        attendance_status = "late" if now_dt > scheduled_start else "present"
        now = now_dt.isoformat(timespec="seconds")
        connection.execute("""
            INSERT INTO session_attendance
            (session_id,student_id,status,check_in_at,verification_method,
             verification_status,verified_by,notes,updated_at)
            VALUES (?,?,?,?,'biometric','verified',?,
                    'Approved provider verified one-to-one identity and liveness.',
                    CURRENT_TIMESTAMP)
        """, (session_id,student_id,attendance_status,now,session["user_id"]))
        connection.execute("""
            INSERT INTO attendance_events
            (session_id,student_id,event_type,verification_method,
             verification_status,recorded_by,notes)
            VALUES (?,?,'check_in','biometric','verified',?,
                    'Approved provider verified one-to-one identity and liveness.')
        """, (session_id,student_id,session["user_id"]))
        connection.execute("""
            INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
            VALUES (?,?,?,?,?)
        """, (session["user_id"],"biometric_check_in","session_attendance",
              f"{session_id}:{student_id}",
              "Attendance recorded after approved provider one-to-one face and liveness verification."))
        connection.commit()
        flash("Identity verified and examination attendance recorded.", "success")
    except HTTPException:
        raise
    except (BiometricVerificationDisabled, BiometricProviderUnavailable, ValueError) as exc:
        connection.rollback()
        # Keep a minimal operational record for provider errors after the
        # candidate/session authorization checks. Never retain the capture.
        if isinstance(exc, BiometricProviderUnavailable):
            try:
                connection.execute("""
                    INSERT INTO biometric_verification_events
                    (session_id,student_id,outcome,provider_name,reason,recorded_by)
                    VALUES(?,?,'error',?,?,?)
                """, (session_id,student_id,
                      getattr(provider, "name", None),
                      str(exc)[:500],session["user_id"]))
                connection.execute("""
                    INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
                    VALUES (?,?,?,?,?)
                """, (session["user_id"],"biometric_verification_error",
                      "session_candidate",f"{session_id}:{student_id}",
                      "Biometric provider error; no attendance was recorded."))
                connection.commit()
            except Exception:
                connection.rollback()
                current_app.logger.exception("Could not persist biometric provider error audit")
        flash(str(exc) + " No attendance was recorded.", "error")
    except Exception:
        connection.rollback()
        current_app.logger.exception("Biometric examination check-in failed")
        flash("Verification could not be completed. No attendance was recorded; use manual review.", "error")
    finally:
        connection.close()
    return redirect(url_for("identity.session_identity",session_id=session_id))


@biometric_attendance_bp.post("/students/<int:student_id>/revoke")
def revoke_enrolment(student_id):
    if session.get("role") not in {"admin", "registrar"}:
        abort(403)
    reason = " ".join((request.form.get("reason") or "").split())[:300]
    if len(reason) < 10:
        abort(400, description="Provide a reason for revoking biometric enrolment.")
    connection = db()
    row = connection.execute(
        "SELECT id FROM biometric_enrolments WHERE student_id=? AND status='active'",
        (student_id,),
    ).fetchone()
    if row:
        connection.execute("""
            UPDATE biometric_enrolments SET status='revoked',revoked_by=?,revoked_at=CURRENT_TIMESTAMP
            WHERE student_id=?
        """, (session["user_id"],student_id))
        connection.execute("""
            INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
            VALUES (?,?,?,?,?)
        """, (session["user_id"],"biometric_enrolment_revoked","student",str(student_id),reason))
        connection.commit()
    connection.close()
    flash("Biometric enrolment revoked. The manual identity process remains available.", "success")
    return redirect(request.referrer or url_for("registry.students"))
