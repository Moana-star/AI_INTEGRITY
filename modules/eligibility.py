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
        CREATE TABLE IF NOT EXISTS annual_progression_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            academic_year TEXT NOT NULL,
            total_courses INTEGER NOT NULL,
            failed_courses INTEGER NOT NULL,
            supplementary_failed_courses INTEGER NOT NULL DEFAULT 0,
            supplementary_fee_paid INTEGER NOT NULL CHECK(supplementary_fee_paid IN (0,1)),
            pathway TEXT NOT NULL,
            failed_percentage REAL NOT NULL,
            source_reference TEXT NOT NULL,
            evaluated_by INTEGER NOT NULL,
            evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(evaluated_by) REFERENCES users(id)
        );
        CREATE TRIGGER IF NOT EXISTS annual_progression_reviews_no_update
        BEFORE UPDATE ON annual_progression_reviews
        BEGIN SELECT RAISE(ABORT, 'Annual progression reviews are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS annual_progression_reviews_no_delete
        BEFORE DELETE ON annual_progression_reviews
        BEGIN SELECT RAISE(ABORT, 'Annual progression reviews are append-only'); END;
        CREATE TABLE IF NOT EXISTS eligibility_evidence_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            unit_id INTEGER NOT NULL,
            academic_year TEXT NOT NULL,
            semester TEXT NOT NULL,
            lectures_total INTEGER NOT NULL,
            lectures_attended INTEGER NOT NULL,
            cats_required INTEGER NOT NULL,
            cats_sat INTEGER NOT NULL,
            fees_cleared INTEGER NOT NULL,
            evidence_reference TEXT NOT NULL,
            recorded_by INTEGER NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(unit_id) REFERENCES academic_units(id),
            FOREIGN KEY(recorded_by) REFERENCES users(id)
        );
        CREATE TRIGGER IF NOT EXISTS eligibility_evidence_history_no_update
        BEFORE UPDATE ON eligibility_evidence_history
        BEGIN SELECT RAISE(ABORT, 'Eligibility evidence history is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS eligibility_evidence_history_no_delete
        BEFORE DELETE ON eligibility_evidence_history
        BEGIN SELECT RAISE(ABORT, 'Eligibility evidence history is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS eligibility_decisions_no_update
        BEFORE UPDATE ON eligibility_decisions
        BEGIN SELECT RAISE(ABORT, 'Eligibility decisions are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS eligibility_decisions_no_delete
        BEFORE DELETE ON eligibility_decisions
        BEGIN SELECT RAISE(ABORT, 'Eligibility decisions are append-only'); END;
        CREATE TABLE IF NOT EXISTS eligibility_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            unit_id INTEGER NOT NULL,
            academic_year TEXT NOT NULL,
            semester TEXT NOT NULL,
            lectures_total INTEGER NOT NULL CHECK(lectures_total >= 0),
            lectures_attended INTEGER NOT NULL CHECK(lectures_attended >= 0 AND lectures_attended <= lectures_total),
            cats_required INTEGER NOT NULL CHECK(cats_required >= 0),
            cats_sat INTEGER NOT NULL CHECK(cats_sat >= 0 AND cats_sat <= cats_required),
            fees_cleared INTEGER NOT NULL CHECK(fees_cleared IN (0,1)),
            evidence_reference TEXT NOT NULL,
            verified_by INTEGER NOT NULL,
            verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id,unit_id,academic_year,semester),
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(unit_id) REFERENCES academic_units(id),
            FOREIGN KEY(verified_by) REFERENCES users(id)
        );
    """)
    policy_columns = {row[1] for row in connection.execute("PRAGMA table_info(eligibility_policies)")}
    if "source_reference" not in policy_columns:
        connection.execute("ALTER TABLE eligibility_policies ADD COLUMN source_reference TEXT")
    connection.commit()
    connection.close()


def validate_rules(rules):
    required = {
        "require_active_student", "require_registered_unit",
        "require_fee_clearance", "minimum_attendance_percentage",
        "minimum_cats_required"
    }
    if not isinstance(rules, dict) or set(rules) != required:
        raise ValueError("Eligibility policy must define the complete Kisii University examination rule set.")
    for key in ("require_active_student", "require_registered_unit", "require_fee_clearance"):
        if type(rules[key]) is not bool or not rules[key]:
            raise ValueError(f"The approved Kisii University policy must enforce {key}.")
    if type(rules["minimum_attendance_percentage"]) not in (int, float) or not 0 <= rules["minimum_attendance_percentage"] <= 100:
        raise ValueError("Minimum lecture attendance must be between 0 and 100 percent.")
    if type(rules["minimum_cats_required"]) is not int or not 1 <= rules["minimum_cats_required"] <= 20:
        raise ValueError("Minimum CAT count must be between 1 and 20.")
    return rules


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
        try:
            rules = validate_rules(json.loads(policy["rules_json"]))
        except (ValueError, TypeError, json.JSONDecodeError):
            reasons.append("The approved policy version is incomplete or invalid for the current Kisii rule set; manual policy review is required.")
            rules = None
        student = connection.execute("""
            SELECT s.id, COALESCE(p.academic_status,'active') AS academic_status
            FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id
            WHERE s.id=?
        """, (student_id,)).fetchone()
        unit = connection.execute("SELECT id, active FROM academic_units WHERE id=?", (unit_id,)).fetchone()
        enrolment = connection.execute("""
            SELECT 1 FROM student_unit_enrolments
            WHERE student_id=? AND unit_id=? AND academic_year=?
              AND semester=? AND enrolment_status='registered'
        """, (student_id, unit_id, academic_year, semester)).fetchone()
        evidence = connection.execute("""
            SELECT * FROM eligibility_evidence
            WHERE student_id=? AND unit_id=? AND academic_year=? AND semester=?
        """, (student_id, unit_id, academic_year, semester)).fetchone()
        if rules is None:
            pass
        elif not student or not unit:
            reasons.append("Student or academic unit could not be verified against the institutional registry.")
        elif not unit["active"]:
            result = "ineligible"
            reasons.append("The academic unit is inactive.")
        elif rules["require_active_student"] and student["academic_status"] != "active":
            result = "ineligible"
            reasons.append("The student's academic status is not active.")
        elif rules["require_registered_unit"] and not enrolment:
            result = "ineligible"
            reasons.append("No registered enrolment exists for this unit, academic year and semester.")
        elif not evidence:
            reasons.append("Verified course-level fee, lecture-attendance and CAT evidence has not been recorded.")
        else:
            failures = []
            attendance_pct = (100.0 * evidence["lectures_attended"] / evidence["lectures_total"]) if evidence["lectures_total"] else 0.0
            if rules["require_fee_clearance"] and not evidence["fees_cleared"]:
                failures.append("Fee-clearance evidence indicates outstanding fees.")
            if attendance_pct < rules["minimum_attendance_percentage"]:
                failures.append(f"Lecture attendance is {attendance_pct:.1f}%; the approved minimum is {rules['minimum_attendance_percentage']}%.")
            if evidence["cats_required"] < rules["minimum_cats_required"]:
                failures.append("The recorded course assessment plan does not meet the policy's minimum CAT count.")
            if evidence["cats_sat"] < rules["minimum_cats_required"]:
                failures.append(f"Only {evidence['cats_sat']} of the required CATs were sat.")
            if failures:
                result = "ineligible"
                reasons.extend(failures)
            else:
                result = "eligible"
                reasons.append(
                    f"Approved policy {policy['policy_code']} v{policy['version']} satisfied: registered unit, active status, fee clearance, {attendance_pct:.1f}% lecture attendance and {evidence['cats_sat']} CATs sat."
                )
    cursor = connection.execute("""
        INSERT INTO eligibility_decisions
            (student_id,unit_id,academic_year,semester,policy_id,result,reasons_json,evaluated_by)
        VALUES (?,?,?,?,?,?,?,?)
    """, (student_id, unit_id, academic_year, semester,
          policy["id"] if policy else None, result,
          json.dumps(reasons, ensure_ascii=False), actor_id))
    return cursor.lastrowid, result, reasons, policy


def evaluate_annual_progression(total_courses, failed_courses, supplementary_fee_paid,
                               supplementary_failed_courses=0):
    """Calculate a review pathway from the published 2019 handbook; never changes status."""
    values = (total_courses,failed_courses,supplementary_failed_courses)
    if any(type(value) is not int for value in values):
        raise ValueError("Course counts must be whole numbers.")
    if total_courses < 1 or not 0 <= failed_courses <= total_courses:
        raise ValueError("Total courses must be positive and failed courses must be within the total.")
    if not 0 <= supplementary_failed_courses <= failed_courses:
        raise ValueError("Supplementary failed-course count cannot exceed the original failed-course count.")
    if failed_courses == 0:
        return {"pathway":"all_courses_passed","failed_percentage":0.0,
                "requires_institutional_approval":True,
                "note":"All recorded courses are passed; verify all other progression requirements."}
    if supplementary_failed_courses:
        return {"pathway":"repeat_failed_courses","failed_percentage":100.0*supplementary_failed_courses/total_courses,
                "requires_institutional_approval":True,
                "note":"The handbook states that failed supplementary courses must be repeated when next offered."}
    failed_percentage=100.0*failed_courses/total_courses
    if failed_percentage <= 25.0:
        pathway="supplementary_eligible" if supplementary_fee_paid else "pending_supplementary_fee"
        note=("Within the handbook's maximum 25% failed-course threshold; supplementary fee evidence is present."
              if supplementary_fee_paid else
              "Within the 25% threshold, but supplementary fee clearance has not been evidenced.")
    elif failed_percentage <= 50.0:
        pathway="repeat_academic_year"
        note="Within the handbook's up-to-50% failed-course band; repeat-year treatment requires institutional confirmation."
    else:
        pathway="discontinuation_review_required"
        note="Above the handbook's 50% threshold; refer for formal institutional discontinuation review, not automatic discontinuation."
    return {"pathway":pathway,"failed_percentage":failed_percentage,
            "requires_institutional_approval":True,"note":note}


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


@eligibility_bp.before_request
def authorize():
    if "user_id" not in session or session.get("role") not in {"admin", "registrar", "examination_officer"}:
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
    progression_reviews = connection.execute("""
        SELECT r.*,s.student_number,s.first_name,s.last_name
        FROM annual_progression_reviews r JOIN students s ON s.id=r.student_id
        ORDER BY r.evaluated_at DESC LIMIT 50
    """).fetchall()
    connection.close()
    return render_template("eligibility_workspace.html", policies=policies,
                           students=students, units=units, decisions=decisions,
                           progression_reviews=progression_reviews)


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
    try:
        rules = validate_rules({
            "require_active_student": request.form.get("require_active_student") == "on",
            "require_registered_unit": request.form.get("require_registered_unit") == "on",
            "require_fee_clearance": request.form.get("require_fee_clearance") == "on",
            "minimum_attendance_percentage": float(request.form.get("minimum_attendance_percentage", "80")),
            "minimum_cats_required": int(request.form.get("minimum_cats_required", "2")),
        })
    except (ValueError, TypeError) as error:
        flash(str(error), "error")
        return redirect(url_for("eligibility.workspace"))
    if not code or len(code) > 60 or version < 1 or len(reason) < 10:
        flash("Provide a policy code, positive version and official policy/source reference.", "error")
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


@eligibility_bp.post("/progression/evaluate")
def evaluate_progression():
    if session.get("role") not in {"admin","registrar","examination_officer"}:
        abort(403)
    try:
        student_id=int(request.form.get("student_id",""))
        total=int(request.form.get("total_courses",""))
        failed=int(request.form.get("failed_courses",""))
        supplementary_failed=int(request.form.get("supplementary_failed_courses","0"))
    except (TypeError,ValueError):
        flash("Enter valid course counts and select a student.","error")
        return redirect(url_for("eligibility.workspace"))
    year=" ".join((request.form.get("academic_year") or "").split())[:20]
    reference=" ".join((request.form.get("source_reference") or "").split())[:500]
    fee_paid=request.form.get("supplementary_fee_paid")=="yes"
    if not year or len(reference)<8:
        flash("Provide the academic year and an official results/fee source reference.","error")
        return redirect(url_for("eligibility.workspace"))
    try:
        result=evaluate_annual_progression(total,failed,fee_paid,supplementary_failed)
    except ValueError as error:
        flash(str(error),"error")
        return redirect(url_for("eligibility.workspace"))
    connection=db()
    if not connection.execute("SELECT 1 FROM students WHERE id=?",(student_id,)).fetchone():
        connection.close()
        abort(404)
    cursor=connection.execute("""
        INSERT INTO annual_progression_reviews
            (student_id,academic_year,total_courses,failed_courses,supplementary_failed_courses,
             supplementary_fee_paid,pathway,failed_percentage,source_reference,evaluated_by)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """,(student_id,year,total,failed,supplementary_failed,int(fee_paid),result["pathway"],
          result["failed_percentage"],reference,session["user_id"]))
    review_id=cursor.lastrowid
    connection.execute("""
        INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
        VALUES(?,'evaluate_progression','annual_progression_review',?,?)
    """,(session["user_id"],str(review_id),f"Recorded non-adjudicative annual pathway: {result['pathway']}."))
    connection.commit()
    connection.close()
    flash(f"Annual pathway recorded: {result['pathway'].replace('_',' ').upper()}. {result['note']} No student status was changed; formal institutional approval is required.","success")
    return redirect(url_for("eligibility.workspace"))


@eligibility_bp.post("/evidence")
def record_evidence():
    if session.get("role") not in {"admin", "registrar", "examination_officer"}:
        abort(403)
    try:
        student_id = int(request.form.get("student_id", ""))
        unit_id = int(request.form.get("unit_id", ""))
        lectures_total = int(request.form.get("lectures_total", ""))
        lectures_attended = int(request.form.get("lectures_attended", ""))
        cats_required = int(request.form.get("cats_required", ""))
        cats_sat = int(request.form.get("cats_sat", ""))
    except (TypeError, ValueError):
        flash("Enter valid whole-number attendance and CAT evidence.", "error")
        return redirect(url_for("eligibility.workspace"))
    year = " ".join((request.form.get("academic_year") or "").split())[:20]
    semester = " ".join((request.form.get("semester") or "").split())[:40]
    reference = " ".join((request.form.get("evidence_reference") or "").split())[:500]
    fees_cleared = request.form.get("fees_cleared") == "yes"
    if not year or not semester or len(reference) < 8 or lectures_total < 1 or not 0 <= lectures_attended <= lectures_total or not 1 <= cats_required <= 20 or not 0 <= cats_sat <= cats_required:
        flash("Evidence must include a source reference, valid lecture counts and CAT counts.", "error")
        return redirect(url_for("eligibility.workspace"))
    connection = db()
    if not connection.execute("SELECT 1 FROM students WHERE id=?", (student_id,)).fetchone() or not connection.execute("SELECT 1 FROM academic_units WHERE id=?", (unit_id,)).fetchone():
        connection.close()
        abort(404)
    connection.execute("""
        INSERT INTO eligibility_evidence_history
            (student_id,unit_id,academic_year,semester,lectures_total,lectures_attended,
             cats_required,cats_sat,fees_cleared,evidence_reference,recorded_by)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """, (student_id,unit_id,year,semester,lectures_total,lectures_attended,
          cats_required,cats_sat,int(fees_cleared),reference,session["user_id"]))
    connection.execute("""
        INSERT INTO eligibility_evidence
            (student_id,unit_id,academic_year,semester,lectures_total,lectures_attended,
             cats_required,cats_sat,fees_cleared,evidence_reference,verified_by)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(student_id,unit_id,academic_year,semester) DO UPDATE SET
            lectures_total=excluded.lectures_total, lectures_attended=excluded.lectures_attended,
            cats_required=excluded.cats_required, cats_sat=excluded.cats_sat,
            fees_cleared=excluded.fees_cleared, evidence_reference=excluded.evidence_reference,
            verified_by=excluded.verified_by, verified_at=CURRENT_TIMESTAMP
    """, (student_id,unit_id,year,semester,lectures_total,lectures_attended,
          cats_required,cats_sat,int(fees_cleared),reference,session["user_id"]))
    connection.execute("""
        INSERT INTO audit_events(actor_user_id,action,entity_type,entity_id,summary)
        VALUES(?,'record_evidence','eligibility_evidence',?,?)
    """, (session["user_id"],f"{student_id}:{unit_id}:{year}:{semester}",
          "Recorded source-referenced fee, lecture attendance and CAT evidence; re-evaluation is required."))
    connection.commit()
    connection.close()
    flash("Eligibility evidence saved. Re-evaluate the candidate to produce a new policy decision.", "success")
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
