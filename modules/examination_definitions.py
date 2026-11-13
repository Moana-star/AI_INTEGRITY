"""Governed examination-definition management.

The examinations table remains the stable parent identity referenced by
existing examination sessions and incident records. Session-specific dates,
times, venues and invigilator assignments remain in examination_sessions and
its relationship tables; this module deliberately does not schedule sessions.
Legacy schedule columns are retained for compatibility with existing rows.
"""
from __future__ import annotations

import re
import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from modules.access_control import has_permission
from modules.institutional_registry import ensure_schema as ensure_registry_schema
from modules.integrity import ensure_schema as ensure_integrity_schema
from modules.operations import ensure_schema as ensure_operations_schema, _audit, db as operations_db

examination_definitions_bp = Blueprint(
    "examination_definitions", __name__, url_prefix="/admin/examinations"
)
SCHEMA_READY = False
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9./_-]{1,24}$")


def db():
    return operations_db()


def ensure_schema():
    """Add definition lifecycle metadata without rebuilding or deleting records."""
    ensure_registry_schema()
    ensure_operations_schema()
    ensure_integrity_schema()
    connection = db()
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(examinations)").fetchall()
    }
    additions = {
        "definition_status": (
            "TEXT NOT NULL DEFAULT 'active' "
            "CHECK (definition_status IN ('active','archived'))"
        ),
        "definition_created_by": "INTEGER REFERENCES users(id)",
        "definition_updated_at": "TEXT",
        "definition_archived_at": "TEXT",
        "definition_archived_by": "INTEGER REFERENCES users(id)",
        "definition_archive_reason": "TEXT",
    }
    for name, declaration in additions.items():
        if name not in columns:
            connection.execute(
                f"ALTER TABLE examinations ADD COLUMN {name} {declaration}"
            )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_examinations_definition_status "
        "ON examinations(definition_status, course_code)"
    )
    connection.commit()
    connection.close()


def _authorized():
    return "user_id" in session and has_permission(session.get("role"), "exams.write")


def _values(source):
    code = " ".join((source.get("course_code") or "").split()).upper()
    name = " ".join((source.get("examination_name") or "").split())
    if not CODE_PATTERN.fullmatch(code):
        raise ValueError(
            "Enter a valid examination/unit code (2–25 characters; letters, "
            "numbers, dots, slashes, underscores and hyphens only)."
        )
    if not 3 <= len(name) <= 160:
        raise ValueError("Examination name must contain 3–160 characters.")
    return code, name


def _duplicate(connection, code, name, exclude_id=None):
    sql = """
        SELECT id FROM examinations
        WHERE UPPER(course_code)=? AND LOWER(examination_name)=LOWER(?)
    """
    params = [code, name]
    if exclude_id is not None:
        sql += " AND id<>?"
        params.append(exclude_id)
    return connection.execute(sql + " LIMIT 1", tuple(params)).fetchone()


def _insert_definition(connection, code, name, actor_id):
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(examinations)").fetchall()
    }
    # The original schema requires legacy schedule columns. Keep inert
    # compatibility values; real sittings are recorded in examination_sessions.
    values = {
        "course_code": code,
        "examination_name": name,
        "examination_date": "1900-01-01",
        "start_time": "00:00",
        "end_time": "00:01",
        "venue": None,
        "invigilator_id": None,
        "status": "scheduled",
        "definition_status": "active",
        "definition_created_by": actor_id,
        "definition_updated_at": None,
    }
    selected = [(key, value) for key, value in values.items() if key in columns]
    names = ", ".join(key for key, _ in selected)
    placeholders = ", ".join("?" for _ in selected)
    cursor = connection.execute(
        f"INSERT INTO examinations ({names}) VALUES ({placeholders})",
        tuple(value for _, value in selected),
    )
    return cursor.lastrowid


@examination_definitions_bp.before_request
def prepare_examination_definitions():
    global SCHEMA_READY
    if not _authorized():
        abort(403)
    if not SCHEMA_READY:
        ensure_schema()
        SCHEMA_READY = True


@examination_definitions_bp.get("")
def list_definitions():
    status = (request.args.get("status") or "active").strip().lower()
    if status not in {"active", "archived"}:
        status = "active"
    connection = db()
    definitions = connection.execute(
        """
        SELECT e.id, e.course_code, e.examination_name, e.definition_status,
               e.definition_created_by, e.definition_updated_at,
               e.definition_archived_at, e.definition_archive_reason,
               (SELECT COUNT(*) FROM examination_sessions s
                WHERE s.examination_id=e.id) AS session_count,
               (SELECT COUNT(*) FROM examination_sessions s
                WHERE s.examination_id=e.id
                  AND s.status IN ('scheduled','active')) AS open_session_count
        FROM examinations e
        WHERE e.definition_status=?
        ORDER BY e.course_code, e.examination_name, e.id
        """,
        (status,),
    ).fetchall()
    connection.close()
    return render_template(
        "examination_definitions.html",
        definitions=definitions,
        selected_status=status,
    )


@examination_definitions_bp.route("/add", methods=["GET", "POST"])
def create_definition():
    if request.method == "GET":
        return render_template(
            "examination_definition_form.html", examination=None, error=None
        )
    try:
        code, name = _values(request.form)
    except ValueError as error:
        return (
            render_template(
                "examination_definition_form.html",
                examination=None,
                error=str(error),
            ),
            400,
        )
    connection = db()
    try:
        if _duplicate(connection, code, name):
            connection.close()
            return (
                render_template(
                    "examination_definition_form.html",
                    examination=None,
                    error="An examination with this code and name already exists.",
                ),
                409,
            )
        examination_id = _insert_definition(
            connection, code, name, session.get("user_id")
        )
        _audit(
            connection,
            "create",
            "examination_definition",
            examination_id,
            f"Created examination definition {code}: {name}.",
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        connection.close()
        return (
            render_template(
                "examination_definition_form.html",
                examination=None,
                error="The examination definition could not be saved because it conflicts with an existing record.",
            ),
            409,
        )
    connection.close()
    flash("Examination definition created. Create its actual sitting under Academic Operations.", "success")
    return redirect(url_for("examination_definitions.list_definitions"))


@examination_definitions_bp.route("/edit/<int:examination_id>", methods=["GET", "POST"])
def edit_definition(examination_id):
    connection = db()
    examination = connection.execute(
        "SELECT * FROM examinations WHERE id=?", (examination_id,)
    ).fetchone()
    if examination is None:
        connection.close()
        abort(404)
    if examination["definition_status"] != "active":
        connection.close()
        flash("Archived examination definitions cannot be edited. Restore the definition first.", "warning")
        return redirect(url_for("examination_definitions.list_definitions", status="archived"))
    if request.method == "GET":
        connection.close()
        return render_template(
            "examination_definition_form.html", examination=examination, error=None
        )
    try:
        code, name = _values(request.form)
    except ValueError as error:
        connection.close()
        return (
            render_template(
                "examination_definition_form.html",
                examination=examination,
                error=str(error),
            ),
            400,
        )
    if _duplicate(connection, code, name, examination_id):
        connection.close()
        return (
            render_template(
                "examination_definition_form.html",
                examination=examination,
                error="Another examination with this code and name already exists.",
            ),
            409,
        )
    changed = (
        code != examination["course_code"]
        or name != examination["examination_name"]
    )
    if changed:
        connection.execute(
            """
            UPDATE examinations
            SET course_code=?, examination_name=?, definition_updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND definition_status='active'
            """,
            (code, name, examination_id),
        )
        _audit(
            connection,
            "update",
            "examination_definition",
            examination_id,
            f"Updated examination definition from {examination['course_code']}: "
            f"{examination['examination_name']} to {code}: {name}.",
        )
        connection.commit()
    connection.close()
    flash("Examination definition updated." if changed else "No changes were needed.", "success")
    return redirect(url_for("examination_definitions.list_definitions"))


@examination_definitions_bp.post("/archive/<int:examination_id>")
def archive_definition(examination_id):
    reason = " ".join((request.form.get("reason") or "").split())
    if not 10 <= len(reason) <= 500:
        flash("Provide an archive reason of 10–500 characters.", "error")
        return redirect(url_for("examination_definitions.list_definitions"))
    connection = db()
    examination = connection.execute(
        "SELECT id, course_code, examination_name, definition_status "
        "FROM examinations WHERE id=?",
        (examination_id,),
    ).fetchone()
    if examination is None:
        connection.close()
        abort(404)
    if examination["definition_status"] == "archived":
        connection.close()
        flash("This examination definition is already archived.", "warning")
        return redirect(url_for("examination_definitions.list_definitions", status="archived"))
    active_sessions = connection.execute(
        """
        SELECT COUNT(*) FROM examination_sessions
        WHERE examination_id=? AND status IN ('scheduled','active')
        """,
        (examination_id,),
    ).fetchone()[0]
    if active_sessions:
        connection.close()
        flash(
            "Archive blocked: cancel or complete all scheduled/active sessions first. Existing session and incident history is preserved.",
            "error",
        )
        return redirect(url_for("examination_definitions.list_definitions"))
    connection.execute(
        """
        UPDATE examinations
        SET definition_status='archived', definition_archived_at=CURRENT_TIMESTAMP,
            definition_archived_by=?, definition_archive_reason=?,
            definition_updated_at=CURRENT_TIMESTAMP
        WHERE id=? AND definition_status='active'
        """,
        (session.get("user_id"), reason, examination_id),
    )
    _audit(
        connection,
        "archive",
        "examination_definition",
        examination_id,
        f"Archived examination definition {examination['course_code']}: "
        f"{examination['examination_name']}. Reason: {reason}",
    )
    connection.commit()
    connection.close()
    flash("Examination definition archived. Historical sessions and incidents were retained.", "success")
    return redirect(url_for("examination_definitions.list_definitions"))


@examination_definitions_bp.post("/restore/<int:examination_id>")
def restore_definition(examination_id):
    reason = " ".join((request.form.get("reason") or "").split())
    if not 10 <= len(reason) <= 500:
        flash("Provide a restoration reason of 10–500 characters.", "error")
        return redirect(url_for("examination_definitions.list_definitions", status="archived"))
    connection = db()
    examination = connection.execute(
        "SELECT id, course_code, examination_name, definition_status "
        "FROM examinations WHERE id=?",
        (examination_id,),
    ).fetchone()
    if examination is None:
        connection.close()
        abort(404)
    if examination["definition_status"] != "archived":
        connection.close()
        flash("Only archived examination definitions can be restored.", "warning")
        return redirect(url_for("examination_definitions.list_definitions"))
    connection.execute(
        """
        UPDATE examinations
        SET definition_status='active', definition_archived_at=NULL,
            definition_archived_by=NULL, definition_archive_reason=NULL,
            definition_updated_at=CURRENT_TIMESTAMP
        WHERE id=? AND definition_status='archived'
        """,
        (examination_id,),
    )
    _audit(
        connection,
        "restore",
        "examination_definition",
        examination_id,
        f"Restored examination definition {examination['course_code']}: "
        f"{examination['examination_name']}. Reason: {reason}",
    )
    connection.commit()
    connection.close()
    flash("Examination definition restored. Review its sessions before scheduling further sittings.", "success")
    return redirect(url_for("examination_definitions.list_definitions"))


@examination_definitions_bp.post("/delete/<int:examination_id>")
def disable_legacy_delete(examination_id):
    """Keep the old URL safe: never physically delete examination definitions."""
    flash("Direct examination deletion is disabled. Use the audited archive action instead.", "warning")
    return redirect(url_for("examination_definitions.list_definitions"), code=303)
