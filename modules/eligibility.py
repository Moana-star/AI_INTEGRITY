"""Versioned, approval-gated examination eligibility policy engine.

No university-specific eligibility thresholds are assumed. A policy must be
created from an approved institutional rule and approved by a different user
before it can produce an eligible/ineligible decision.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from modules.institutional_registry import ensure_schema as ensure_registry_schema
from modules.operations import ensure_schema as ensure_operations_schema

eligibility_bp = Blueprint("eligibility", __name__, url_prefix="/eligibility")
DATABASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "exam_integrity.db")


def db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema():
    connection = db()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS eligibility_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_code TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version > 0),
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            source_reference TEXT,
            rules_json TEXT NOT NULL,
            approval_status TEXT NOT NULL DEFAULT 'draft'
                CHECK(approval_status IN ('draft','approved','retired')),
            created_by INTEGER NOT NULL,
            approved_by INTEGER,
            approval_reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT,
            UNIQUE(policy_code, version),
            FOREIGN KEY(created_by) REFERENCES users(id),
            FOREIGN KEY(approved_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS eligibility_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            unit_id INTEGER NOT NULL,
            academic_year TEXT NOT NULL,
            semester TEXT NOT NULL,
            policy_id INTEGER,
            result TEXT NOT NULL CHECK(result IN ('eligible','pending','ineligible')),
            reasons_json TEXT NOT NULL,
            evaluated_by INTEGER NOT NULL,
            evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(unit_id) REFERENCES academic_units(id),
            FOREIGN KEY(policy_id) REFERENCES eligibility_policies(id),
            FOREIGN KEY(evaluated_by) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_eligibility_decisions_student
            ON eligibility_decisions(student_id, evaluated_at DESC);
    """)
    policy_columns = {row[1] for row in connection.execute("PRAGMA table_info(eligibility_policies)")}
    if "source_reference" not in policy_columns:
        connection.execute("ALTER TABLE eligibility_policies ADD COLUMN source_reference TEXT")
    connection.commit()
    connection.close()


def validate_rules(rules):
    if not isinstance(rules, dict) or set(rules) != {
        "require_active_student", "require_registered_unit"
    }:
        raise ValueError("Only supported, explicit eligibility rules can be configured.")
    if any(type(value) is not bool for value in rules.values()):
        raise ValueError("Eligibility rule values must be true or false.")
    return rules


def apply_decision_to_scheduled_candidates(connection, student_id, unit_id,
                                                    academic_year, semester,
                                                    result, reasons):
    """Update only future scheduled sessions; never rewrite active/completed history."""
    cursor = connection.execute("""
        UPDATE session_candidates
        SET eligibility_status=?, eligibility_note=?
        WHERE student_id=? AND session_id IN (
            SELECT id FROM examination_sessions
            WHERE unit_id=? AND academic_year=? AND semester=? AND status='scheduled'
        )
    """, (result, " ".join(reasons)[:500], student_id, unit_id,
          academic_year[:20], semester[:40]))
    return cursor.rowcount


def evaluate(connection, student_id, unit_id, academic_year, semester, actor_id):
    today = date.today().isoformat()
    policy = connection.execute("""
        SELECT * FROM eligibility_policies
        WHERE approval_status='approved' AND effective_from<=?
          AND (effective_to IS NULL OR effective_to>=?)
        ORDER BY effective_from DESC, version DESC LIMIT 1
    """, (today, today)).fetchone()
    reasons = []
    result = "pending"
    if policy is None:
        reasons.append("No currently effective, institution-approved eligibility policy is configured.")
    else:
        rules = validate_rules(json.loads(policy["rules_json"]))
        student = connection.execute("""
            SELECT s.id, COALESCE(p.academic_status,'active') AS academic_status
            FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id
            WHERE s.id=?
        """, (student_id,)).fetchone()
        unit = connection.execute("SELECT id, active FROM academic_units WHERE id=?", (unit_id,)).fetchone()
        if not student or not unit:
            result = "pending"
            reasons.append("Student or academic unit could not be verified against the institutional registry.")
        else:
            failures = []
            if not unit["active"]:
                failures.append("The academic unit is inactive.")
            if rules["require_active_student"] and student["academic_status"] != "active":
                failures.append("The student's academic status is not active.")
            if rules["require_registered_unit"]:
                enrolment = connection.execute("""
                    SELECT 1 FROM student_unit_enrolments
                    WHERE student_id=? AND unit_id=? AND academic_year=?
                      AND semester=? AND enrolment_status='registered'
                """, (student_id, unit_id, academic_year, semester)).fetchone()
                if not enrolment:
                    failures.append("No registered enrolment exists for this unit, academic year and semester.")
            if failures:
                result = "ineligible"
                reasons.extend(failures)
            else:
                result = "eligible"
                reasons.append("All conditions in the approved policy version were satisfied.")
    cursor = connection.execute("""
        INSERT INTO eligibility_decisions
            (student_id,unit_id,academic_year,semester,policy_id,result,reasons_json,evaluated_by)
        VALUES (?,?,?,?,?,?,?,?)
    """, (student_id, unit_id, academic_year, semester,
          policy["id"] if policy else None, result,
          json.dumps(reasons, ensure_ascii=False), actor_id))
    return cursor.lastrowid, result, reasons, policy


@eligibility_bp.before_request
def authorize():
    if "user_id" not in session or session.get("role") not in {"admin", "examination_officer"}:
        abort(403)
    ensure_registry_schema()
    ensure_operations_schema()
    ensure_schema()


@eligibility_bp.get("/")
def workspace():
    connection = db()
    policies = connection.execute("""
        SELECT p.*, u.username AS creator, a.username AS approver
        FROM eligibility_policies p
        JOIN users u ON u.id=p.created_by
        LEFT JOIN users a ON a.id=p.approved_by
        ORDER BY p.created_at DESC
    """).fetchall()
    students = connection.execute("SELECT id,student_number,first_name,last_name FROM students ORDER BY student_number").fetchall()
    units = connection.execute("SELECT id,unit_code,unit_name FROM academic_units WHERE active=1 ORDER BY unit_code").fetchall()
    decisions = connection.execute("""
        SELECT d.*,s.student_number,u.unit_code
        FROM eligibility_decisions d JOIN students s ON s.id=d.student_id
        JOIN academic_units u ON u.id=d.unit_id
        ORDER BY d.evaluated_at DESC LIMIT 50
    """).fetchall()
    connection.close()
    return render_template("eligibility_workspace.html", policies=policies,
                           students=students, units=units, decisions=decisions)


@eligibility_bp.post("/policies")
def create_policy():
    code = " ".join((request.form.get("policy_code") or "").split()).upper()
    reason = " ".join((request.form.get("source_reference") or "").split())
    try:
        version = int(request.form.get("version", ""))
        effective_from = date.fromisoformat(request.form.get("effective_from", "")).isoformat()
    except (TypeError, ValueError):
        flash("Enter a positive version and valid effective date.", "error")
        return redirect(url_for("eligibility.workspace"))
    rules = {
        "require_active_student": request.form.get("require_active_student") == "on",
        "require_registered_unit": request.form.get("require_registered_unit") == "on",
    }
    if not code or len(code) > 60 or version < 1 or len(reason) < 10 or not all(rules.values()):
        flash("Provide a policy code, positive version, official policy/source reference, and both active-student and registered-unit checks.", "error")
        return redirect(url_for("eligibility.workspace"))
    connection = db()
    try:
        connection.execute("""
            INSERT INTO eligibility_policies
                (policy_code,version,effective_from,source_reference,rules_json,created_by)
            VALUES (?,?,?,?,?,?)
        """, (code,version,effective_from,reason,json.dumps(rules),session["user_id"]))
        policy_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute("""INSERT INTO audit_events
            (actor_user_id,action,entity_type,entity_id,summary)
            VALUES (?,'create','eligibility_policy',?,'Created an eligibility policy draft requiring independent approval.')""",
            (session["user_id"], str(policy_id)))
        connection.commit()
        flash("Policy draft saved. It cannot affect eligibility until a different administrator approves it.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("That policy code and version already exist.", "error")
    finally:
        connection.close()
    return redirect(url_for("eligibility.workspace"))


@eligibility_bp.post("/policies/<int:policy_id>/approve")
def approve_policy(policy_id):
    if session.get("role") != "admin":
        abort(403)
    reason = " ".join((request.form.get("approval_reason") or "").split())
    connection = db()
    policy = connection.execute("SELECT * FROM eligibility_policies WHERE id=?", (policy_id,)).fetchone()
    if not policy:
        connection.close()
        abort(404)
    if policy["created_by"] == session["user_id"] or policy["approval_status"] != "draft" or len(reason) < 10:
        connection.close()
        abort(403, description="Policy approval requires a different administrator and a meaningful approval reason.")
    connection.execute("""
        UPDATE eligibility_policies SET approval_status='retired'
        WHERE policy_code=? AND approval_status='approved'
    """, (policy["policy_code"],))
    connection.execute("""
        UPDATE eligibility_policies SET approval_status='approved', approved_by=?,
            approval_reason=?, approved_at=CURRENT_TIMESTAMP WHERE id=?
    """, (session["user_id"],reason,policy_id))
    connection.execute("""INSERT INTO audit_events
        (actor_user_id,action,entity_type,entity_id,summary)
        VALUES (?,'approve','eligibility_policy',?,'Eligibility policy independently approved.')""",
        (session["user_id"],str(policy_id)))
    connection.commit()
    connection.close()
    flash("Eligibility policy approved with independent administrator review.", "success")
    return redirect(url_for("eligibility.workspace"))


@eligibility_bp.post("/evaluate")
def evaluate_candidate():
    try:
        student_id = int(request.form.get("student_id", ""))
        unit_id = int(request.form.get("unit_id", ""))
    except (TypeError, ValueError):
        flash("Select a valid student and academic unit.", "error")
        return redirect(url_for("eligibility.workspace"))
    year = " ".join((request.form.get("academic_year") or "").split())
    semester = " ".join((request.form.get("semester") or "").split())
    if not year or not semester:
        flash("Academic year and semester are required.", "error")
        return redirect(url_for("eligibility.workspace"))
    connection = db()
    valid_student = connection.execute("SELECT 1 FROM students WHERE id=?", (student_id,)).fetchone()
    valid_unit = connection.execute("SELECT 1 FROM academic_units WHERE id=?", (unit_id,)).fetchone()
    if not valid_student or not valid_unit:
        connection.close()
        flash("The selected student or academic unit does not exist in the institutional registry.", "error")
        return redirect(url_for("eligibility.workspace"))
    try:
        decision_id, result, reasons, policy = evaluate(
            connection, student_id, unit_id, year[:20], semester[:40], session["user_id"])
        apply_decision_to_scheduled_candidates(
            connection, student_id, unit_id, year, semester, result, reasons)
        connection.execute("""INSERT INTO audit_events
            (actor_user_id,action,entity_type,entity_id,summary)
            VALUES (?,'evaluate','eligibility_decision',?,?)""",
            (session["user_id"],str(decision_id),f"Eligibility evaluation recorded with result {result}."))
        connection.commit()
        flash(f"Eligibility decision {decision_id}: {result.upper()} — " + " ".join(reasons), "success" if result == "eligible" else "error")
    except (ValueError, json.JSONDecodeError):
        connection.rollback()
        flash("The approved policy configuration is invalid. No eligibility result was issued.", "error")
    finally:
        connection.close()
    return redirect(url_for("eligibility.workspace"))
