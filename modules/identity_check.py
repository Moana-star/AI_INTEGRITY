"""Session-scoped student identity review with camera preview only.

The browser preview never captures, uploads, compares, templates or stores a face.
It is an optional visual aid only. Admission-number and student-card checks remain
manual and must not be confused with eligibility or attendance decisions.
"""
import os
import sqlite3
from flask import Blueprint, abort, render_template, request, session
from modules.institutional_registry import ensure_schema as ensure_registry_schema
from modules.operations import ensure_schema as ensure_operations_schema
from modules.database import get_connection

identity_bp = Blueprint("identity", __name__, url_prefix="/identity")
DATABASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "exam_integrity.db")


def db():
    return get_connection(DATABASE)


@identity_bp.before_request
def authorize():
    if "user_id" not in session or session.get("role") not in {
        "admin", "examination_officer", "invigilator"
    }:
        abort(403)
    ensure_registry_schema()
    ensure_operations_schema()


@identity_bp.get("/sessions/<int:session_id>")
def session_identity(session_id):
    connection = db()
    target = connection.execute("""
        SELECT es.*, e.course_code, e.examination_name
        FROM examination_sessions es
        JOIN examinations e ON e.id=es.examination_id
        WHERE es.id=?
    """, (session_id,)).fetchone()
    if not target:
        connection.close()
        abort(404)
    if session.get("role") == "invigilator":
        assigned = connection.execute("""
            SELECT 1 FROM session_invigilators si
            JOIN invigilators i ON i.id=si.invigilator_id
            WHERE si.session_id=? AND i.user_id=?
            UNION
            SELECT 1 FROM examinations e
            JOIN invigilators i ON i.id=e.invigilator_id
            WHERE e.id=? AND i.user_id=?
            LIMIT 1
        """, (session_id,session["user_id"],target["examination_id"],session["user_id"])).fetchone()
        if not assigned:
            connection.close()
            abort(403)
    query = " ".join((request.args.get("q") or "").split())[:100]
    sql = """
        SELECT s.id,s.student_number,s.first_name,s.last_name,
               c.eligibility_status,c.seat_label,
               COALESCE(p.academic_status,'active') AS academic_status,
               a.status AS attendance_status
        FROM session_candidates c
        JOIN students s ON s.id=c.student_id
        LEFT JOIN student_profiles p ON p.student_id=s.id
        LEFT JOIN session_attendance a ON a.session_id=c.session_id AND a.student_id=c.student_id
        WHERE c.session_id=?
    """
    params = [session_id]
    if query:
        sql += " AND (s.student_number LIKE ? OR s.first_name LIKE ? OR s.last_name LIKE ?)"
        like = f"%{query}%"
        params.extend([like,like,like])
    sql += " ORDER BY c.seat_label,s.student_number"
    candidates = connection.execute(sql,params).fetchall()
    connection.close()
    return render_template("identity_session.html", exam_session=target,
                           candidates=candidates, query=query)
