from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from flask_wtf.csrf import CSRFProtect
from modules.security import limiter
import sqlite3
import os
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash
from modules.institutional_registry import registry_bp
from modules.operations import operations_bp
from modules.examination_definitions import examination_definitions_bp
from modules.integrity import integrity_bp
from modules.student_portal import student_bp
from modules.eligibility import eligibility_bp
from modules.appeals import appeals_bp
from modules.identity_check import identity_bp
from modules.biometric_attendance import biometric_attendance_bp
from modules.access_control import (STAFF_ROLES, effective_user_role, ensure_role_schema, legacy_role_for)
from modules.database import get_connection, is_postgres

app = Flask(__name__)
if os.environ.get("FLASK_ENV") == "production":
    if not is_postgres():
        raise RuntimeError("Production requires DATABASE_URL pointing to PostgreSQL; SQLite is local-development only.")
    if not os.environ.get("FLASK_SECRET_KEY") or len(os.environ["FLASK_SECRET_KEY"]) < 32:
        raise RuntimeError("Production requires a securely generated FLASK_SECRET_KEY of at least 32 characters.")
    if not os.environ.get("RATELIMIT_STORAGE_URI", "").startswith(("redis://", "rediss://")):
        raise RuntimeError("Production requires Redis-backed rate-limit storage; in-memory limits are not multi-worker safe.")
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
CSRFProtect(app)
rate_limit_storage = os.environ.get("RATELIMIT_STORAGE_URI")
app.config["RATELIMIT_STORAGE_URI"] = rate_limit_storage or "memory://"
limiter.init_app(app)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("FLASK_HTTPS", "1" if os.environ.get("FLASK_ENV") == "production" else "0") == "1",
                  MAX_CONTENT_LENGTH=6 * 1024 * 1024)

app.register_blueprint(registry_bp)
app.register_blueprint(examination_definitions_bp)
app.register_blueprint(operations_bp)
app.register_blueprint(integrity_bp)
app.register_blueprint(student_bp)
app.register_blueprint(eligibility_bp)
app.register_blueprint(appeals_bp)
app.register_blueprint(identity_bp)
app.register_blueprint(biometric_attendance_bp)


@app.after_request
def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
    if os.environ.get("FLASK_ENV") == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


DATABASE = os.path.join(os.path.dirname(__file__), "database", "exam_integrity.db")


@app.get("/healthz")
def health_check():
    """Minimal readiness probe; never returns database details or secrets."""
    connection = None
    try:
        connection = get_db_connection()
        connection.execute("SELECT 1").fetchone()
        return jsonify({"status": "ok"}), 200
    except Exception:
        app.logger.exception("Health check failed")
        return jsonify({"status": "unavailable"}), 503
    finally:
        if connection is not None:
            connection.close()


def get_db_connection():
    return get_connection(DATABASE)


def get_student_risk_records(connection):
    rows = connection.execute("""
        SELECT students.student_number, students.first_name, students.last_name,
               COUNT(incidents.id) AS incident_count,
               SUM(CASE WHEN incidents.severity = 'high' THEN 1 ELSE 0 END) AS high_count,
               SUM(CASE WHEN incidents.severity = 'medium' THEN 1 ELSE 0 END) AS medium_count,
               SUM(CASE WHEN incidents.severity = 'low' THEN 1 ELSE 0 END) AS low_count
        FROM students JOIN incidents ON incidents.student_id = students.id
        GROUP BY students.id ORDER BY incident_count DESC, students.student_number
    """).fetchall()

    flagged = []
    summary = {"Watch": 0, "High": 0, "Critical": 0}
    for row in rows:
        if row["high_count"]:
            level = "Critical"
            highest = "High"
            reason = "Flagged as Critical because at least one high-severity incident is recorded."
        elif row["incident_count"] >= 2:
            level = "High"
            highest = "Medium" if row["medium_count"] else "Low"
            reason = "Flagged as High because two or more incidents have been recorded."
        else:
            level = "Watch"
            highest = "Medium" if row["medium_count"] else "Low"
            reason = "Flagged as Watch because one lower-severity incident has been recorded."
        summary[level] += 1
        flagged.append({
            "student_number": row["student_number"],
            "name": f'{row["first_name"]} {row["last_name"]}',
            "incident_count": row["incident_count"],
            "high_severity_count": row["high_count"],
            "highest_severity": highest,
            "risk_level": level,
            "reason": reason,
        })
    return flagged, summary


# ============================================================
# ACCESS CONTROL HELPERS
# ============================================================

def admin_required():
    return "user_id" in session and session.get("role") == "admin"


def invigilator_required():
    return "user_id" in session and session.get("role") == "invigilator"


# ============================================================
# HOME / LOGIN / LOGOUT
# ============================================================

@app.route("/")
def home():
    if admin_required():
        return redirect(url_for("admin_dashboard"))
    if invigilator_required():
        return redirect(url_for("invigilator_dashboard"))
    role = session.get("role")
    if role == "registrar":
        return redirect(url_for("registry.students"))
    if role == "examination_officer":
        return redirect(url_for("operations.workspace"))
    if role == "student" and session.get("student_id"):
        return redirect(url_for("student_portal.portal"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    requested_role = (request.form.get("role") or "").strip().lower()

    if not username or not password or not requested_role:
        return render_template("login.html", error="Please complete all login fields.")
    if requested_role not in STAFF_ROLES:
        return render_template("login.html", error="Invalid username or password.")

    connection = get_db_connection()
    try:
        ensure_role_schema(connection)
        user = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        actual_role = effective_user_role(user)
    finally:
        connection.close()

    if user is None or not check_password_hash(user["password"], password) or actual_role != requested_role:
        return render_template("login.html", error="Invalid username or password.")

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = actual_role

    if actual_role == "admin":
        return redirect(url_for("admin_dashboard"))
    if actual_role == "invigilator":
        return redirect(url_for("invigilator_dashboard"))
    if actual_role == "registrar":
        return redirect(url_for("registry.students"))
    return redirect(url_for("operations.workspace"))


@app.route("/register", methods=["GET", "POST"])
def register():
    # Staff access is institution-controlled. Public self-registration would
    # let an unaffiliated person claim an invigilator identity.
    return render_template(
        "register.html",
        error="Staff accounts are provisioned by an authorized EIMS administrator. Contact your institution's system administrator."
    )


@app.route("/admin/institutional-users", methods=["GET", "POST"])
def institutional_users():
    if not admin_required():
        return redirect(url_for("login"))
    connection = get_db_connection()
    ensure_role_schema(connection)
    if request.method == "POST":
        full_name = " ".join((request.form.get("full_name") or "").split())
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "").strip().lower()
        employee_number = (request.form.get("employee_number") or "").strip().upper()
        department = " ".join((request.form.get("department") or "").split()) or None
        reason = " ".join((request.form.get("reason") or "").split())
        valid_username = 3 <= len(username) <= 32 and all(ch.isalnum() or ch in "._-" for ch in username)
        if (not full_name or len(full_name) > 100 or not valid_username or
                role not in STAFF_ROLES or len(password) < 12 or len(reason) < 10 or
                (role == "invigilator" and not employee_number)):
            connection.close()
            return render_template("institutional_users.html", users=[],
                error="Provide a valid name, username, role, 12-character password and reason. Invigilators also require an employee number.")
        try:
            legacy_role = legacy_role_for(role)
            cursor = connection.execute(
                "INSERT INTO users(username,password,role,institutional_role) VALUES(?,?,?,?)",
                (username, generate_password_hash(password), legacy_role, role))
            user_id = cursor.lastrowid
            if role == "invigilator":
                parts = full_name.split()
                connection.execute("""INSERT INTO invigilators
                    (user_id,employee_number,first_name,last_name,status)
                    VALUES(?,?,?,?, 'active')""",
                    (user_id, employee_number, parts[0], " ".join(parts[1:]) or parts[0]))
            else:
                connection.execute("""INSERT INTO institutional_staff_profiles
                    (user_id,full_name,employee_number,department) VALUES(?,?,?,?)""",
                    (user_id, full_name, employee_number or None, department))
            connection.execute("""INSERT INTO institutional_role_audit
                (actor_user_id,target_user_id,previous_role,new_role,reason)
                VALUES(?,?,NULL,?,?)""", (session["user_id"], user_id, role, reason))
            connection.commit()
            flash("Institutional staff account created. Provide its credentials through the institution's approved secure channel.", "success")
        except sqlite3.IntegrityError:
            connection.rollback()
            flash("That username or employee number is already in use.", "error")
        finally:
            connection.close()
        return redirect(url_for("institutional_users"))
    users = connection.execute("""SELECT u.id,u.username,u.institutional_role,
        COALESCE(p.full_name, i.first_name || ' ' || i.last_name, u.username) AS full_name
        FROM users u LEFT JOIN institutional_staff_profiles p ON p.user_id=u.id
        LEFT JOIN invigilators i ON i.user_id=u.id ORDER BY u.username""").fetchall()
    connection.close()
    return render_template("institutional_users.html", users=users)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    # Password recovery is intentionally unavailable until a verified institutional
    # identity/recovery channel is integrated. Never let username knowledge authorize
    # a password change.
    return render_template(
        "forgot_password.html",
        error="Self-service password recovery is not enabled. Contact your institution's authorized system administrator through its verified support process."
    )


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    # Reject legacy/local reset attempts. The former username-only flow allowed
    # account takeover because no email, MFA, or identity verification was performed.
    return render_template(
        "reset_password.html",
        error="Password reset cannot be completed here. Use your institution's verified account-recovery process."
    )


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("login"))

    from modules.examination_definitions import ensure_schema as ensure_examination_definition_schema
    ensure_examination_definition_schema()
    connection = get_db_connection()

    total_students = connection.execute("SELECT COUNT(*) AS total FROM students").fetchone()["total"]
    total_examinations = connection.execute("SELECT COUNT(*) AS total FROM examinations WHERE definition_status='active'").fetchone()["total"]
    total_invigilators = connection.execute("SELECT COUNT(*) AS total FROM invigilators").fetchone()["total"]
    open_incidents = connection.execute(
        "SELECT COUNT(*) AS total FROM incidents WHERE status = 'open'"
    ).fetchone()["total"]
    resolved_incidents = connection.execute(
        "SELECT COUNT(*) AS total FROM incidents WHERE status = 'resolved'"
    ).fetchone()["total"]
    high_severity_incidents = connection.execute(
        "SELECT COUNT(*) AS total FROM incidents WHERE severity = 'high'"
    ).fetchone()["total"]
    examination_statuses = {row["status"]: row["total"] for row in connection.execute(
        """SELECT CASE status WHEN 'active' THEN 'ongoing' ELSE status END AS status,
                  COUNT(*) AS total
           FROM examination_sessions
           GROUP BY CASE status WHEN 'active' THEN 'ongoing' ELSE status END"""
    ).fetchall()}
    flagged_students, risk_summary = get_student_risk_records(connection)

    examinations = connection.execute(
        """SELECT es.id, e.course_code, e.examination_name,
                  es.session_date AS examination_date, es.start_time, es.end_time,
                  v.room_name AS venue,
                  (SELECT i.first_name FROM session_invigilators si
                   JOIN invigilators i ON i.id=si.invigilator_id
                   WHERE si.session_id=es.id ORDER BY si.id LIMIT 1) AS inv_first,
                  (SELECT i.last_name FROM session_invigilators si
                   JOIN invigilators i ON i.id=si.invigilator_id
                   WHERE si.session_id=es.id ORDER BY si.id LIMIT 1) AS inv_last,
                  CASE es.status WHEN 'active' THEN 'ongoing' ELSE es.status END AS status
           FROM examination_sessions es
           JOIN examinations e ON e.id=es.examination_id
           LEFT JOIN venues v ON v.id=es.venue_id
           ORDER BY CASE es.status WHEN 'active' THEN 0 WHEN 'scheduled' THEN 1 ELSE 2 END,
                    es.session_date, es.start_time LIMIT 8"""
    ).fetchall()

    incidents = connection.execute("""
        SELECT incidents.*, students.student_number, students.first_name, students.last_name,
               examinations.course_code
        FROM incidents
        LEFT JOIN students ON incidents.student_id = students.id
        LEFT JOIN examinations ON incidents.examination_id = examinations.id
        ORDER BY incidents.reported_at DESC
        LIMIT 5
    """).fetchall()

    connection.close()

    return render_template(
        "admin_dashboard.html",
        total_students=total_students,
        total_examinations=total_examinations,
        total_invigilators=total_invigilators,
        open_incidents=open_incidents,
        resolved_incidents=resolved_incidents,
        high_severity_incidents=high_severity_incidents,
        examination_statuses=examination_statuses,
        risk_summary=risk_summary,
        risk_total=len(flagged_students),
        examinations=examinations,
        incidents=incidents
    )


# ============================================================
# LEGACY STUDENT URL COMPATIBILITY
# The institutional registry is the single authoritative student
# management workflow. These aliases prevent older forms from bypassing
# profile validation, audit logging and registrar authorization.
# ============================================================

@app.route("/admin/students")
def admin_students():
    if not admin_required():
        return redirect(url_for("login"))
    return redirect(url_for("registry.students"))


@app.route("/admin/students/add", methods=["GET", "POST"])
def add_student():
    if not admin_required():
        return redirect(url_for("login"))
    status_code = 303 if request.method == "POST" else 302
    return redirect(url_for("registry.new_student"), code=status_code)


@app.route("/admin/students/edit/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):
    if not admin_required():
        return redirect(url_for("login"))
    status_code = 303 if request.method == "POST" else 302
    return redirect(url_for("registry.edit_student", student_id=student_id), code=status_code)


@app.route("/admin/students/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if not admin_required():
        return redirect(url_for("login"))
    # Student deletion is intentionally disabled in the legacy interface.
    # Use governed academic status/history workflows; preserve linked evidence.
    flash("Direct student deletion is disabled. Update the academic status through the Institutional Registry.", "warning")
    return redirect(url_for("registry.students"), code=303)


# ============================================================
# EXAMINATION MANAGEMENT (full CRUD)
# ============================================================

@app.route("/admin/examinations")
def admin_examinations():
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    examinations = connection.execute("""
        SELECT examinations.*, invigilators.first_name AS inv_first, invigilators.last_name AS inv_last
        FROM examinations
        LEFT JOIN invigilators ON examinations.invigilator_id = invigilators.id
        ORDER BY CASE examinations.status WHEN 'ongoing' THEN 0 WHEN 'scheduled' THEN 1 ELSE 2 END, examination_date, start_time
    """).fetchall()
    connection.close()

    return render_template("examinations.html", examinations=examinations)


@app.route("/admin/examinations/add", methods=["GET", "POST"])
def add_examination():
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()

    if request.method == "GET":
        invigilators = connection.execute("SELECT * FROM invigilators ORDER BY first_name").fetchall()
        connection.close()
        return render_template("examination_form.html", examination=None, invigilators=invigilators)

    course_code = request.form.get("course_code")
    examination_name = request.form.get("examination_name")
    examination_date = request.form.get("examination_date")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")
    venue = request.form.get("venue")
    invigilator_id = request.form.get("invigilator_id") or None
    status = request.form.get("status")

    if not all((course_code, examination_name, examination_date, start_time, end_time, status)) or end_time <= start_time or status not in {"scheduled", "ongoing", "completed", "cancelled"}:
        connection.close()
        lookup = get_db_connection()
        invigilators = lookup.execute("SELECT * FROM invigilators ORDER BY first_name").fetchall()
        lookup.close()
        return render_template("examination_form.html", examination=None, invigilators=invigilators, error="Enter all required details and ensure the end time follows the start time.")
    try:
        connection.execute("""
        INSERT INTO examinations
            (course_code, examination_name, examination_date, start_time, end_time, venue, invigilator_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (course_code, examination_name, examination_date, start_time, end_time, venue, invigilator_id, status))
        connection.commit()
    except sqlite3.IntegrityError:
        connection.close()
        flash("The selected invigilator is no longer available. Please try again.", "error")
        return redirect(url_for("add_examination"))
    connection.close()
    flash("Examination scheduled successfully.", "success")

    return redirect(url_for("admin_examinations"))


@app.route("/admin/examinations/edit/<int:examination_id>", methods=["GET", "POST"])
def edit_examination(examination_id):
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()

    if request.method == "GET":
        examination = connection.execute(
            "SELECT * FROM examinations WHERE id = ?", (examination_id,)
        ).fetchone()
        invigilators = connection.execute("SELECT * FROM invigilators ORDER BY first_name").fetchall()
        connection.close()
        if examination is None:
            return redirect(url_for("admin_examinations"))
        return render_template("examination_form.html", examination=examination, invigilators=invigilators)

    course_code = request.form.get("course_code")
    examination_name = request.form.get("examination_name")
    examination_date = request.form.get("examination_date")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")
    venue = request.form.get("venue")
    invigilator_id = request.form.get("invigilator_id") or None
    status = request.form.get("status")

    if not all((course_code, examination_name, examination_date, start_time, end_time, status)) or end_time <= start_time or status not in {"scheduled", "ongoing", "completed", "cancelled"}:
        examination = connection.execute("SELECT * FROM examinations WHERE id = ?", (examination_id,)).fetchone()
        invigilators = connection.execute("SELECT * FROM invigilators ORDER BY first_name").fetchall()
        connection.close()
        if examination is None:
            flash("The examination record could not be found.", "error")
            return redirect(url_for("admin_examinations"))
        return render_template("examination_form.html", examination=examination, invigilators=invigilators, error="Enter all required details and ensure the end time follows the start time.")

    connection.execute("""
        UPDATE examinations
        SET course_code = ?, examination_name = ?, examination_date = ?, start_time = ?,
            end_time = ?, venue = ?, invigilator_id = ?, status = ?
        WHERE id = ?
    """, (course_code, examination_name, examination_date, start_time, end_time,
          venue, invigilator_id, status, examination_id))
    connection.commit()
    connection.close()
    flash("Examination details saved.", "success")

    return redirect(url_for("admin_examinations"))


@app.route("/admin/examinations/delete/<int:examination_id>", methods=["POST"])
def delete_examination(examination_id):
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    try:
        connection.execute("DELETE FROM examinations WHERE id = ?", (examination_id,))
        connection.commit()
    except sqlite3.IntegrityError:
        connection.close()
        flash("This examination has linked incident records and cannot be deleted.", "error")
        return redirect(url_for("admin_examinations"))
    connection.close()
    flash("Examination deleted.", "success")

    return redirect(url_for("admin_examinations"))


# ============================================================
# INVIGILATOR MANAGEMENT (full CRUD)
# ============================================================

@app.route("/admin/invigilators")
def admin_invigilators():
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    invigilators = connection.execute("SELECT * FROM invigilators ORDER BY first_name").fetchall()
    connection.close()

    return render_template("invigilators.html", invigilators=invigilators)


@app.route("/admin/invigilators/add", methods=["GET", "POST"])
def add_invigilator():
    if not admin_required():
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("invigilator_form.html", invigilator=None)

    employee_number = (request.form.get("employee_number") or "").strip()
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    phone = request.form.get("phone")
    status = request.form.get("status")

    connection = get_db_connection()
    if not employee_number or not first_name or not last_name or status not in {"active", "inactive"}:
        connection.close()
        return render_template("invigilator_form.html", invigilator=None, error="Employee number, name and a valid status are required.")
    try:
        connection.execute("""
            INSERT INTO invigilators (employee_number, first_name, last_name, phone, status)
            VALUES (?, ?, ?, ?, ?)
        """, (employee_number, first_name, last_name, phone, status))
        connection.commit()
    except sqlite3.IntegrityError:
        connection.close()
        return render_template("invigilator_form.html", invigilator=None, error="That employee number is already registered.")
    connection.close()
    flash("Invigilator added successfully.", "success")

    return redirect(url_for("admin_invigilators"))


@app.route("/admin/invigilators/edit/<int:invigilator_id>", methods=["GET", "POST"])
def edit_invigilator(invigilator_id):
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()

    if request.method == "GET":
        invigilator = connection.execute(
            "SELECT * FROM invigilators WHERE id = ?", (invigilator_id,)
        ).fetchone()
        connection.close()
        if invigilator is None:
            return redirect(url_for("admin_invigilators"))
        return render_template("invigilator_form.html", invigilator=invigilator)

    employee_number = (request.form.get("employee_number") or "").strip()
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    phone = request.form.get("phone")
    status = request.form.get("status")

    if not employee_number or not first_name or not last_name or status not in {"active", "inactive"}:
        invigilator = connection.execute("SELECT * FROM invigilators WHERE id = ?", (invigilator_id,)).fetchone()
        connection.close()
        return render_template("invigilator_form.html", invigilator=invigilator, error="Employee number, name and a valid status are required.")
    try:
        connection.execute("""
            UPDATE invigilators
            SET employee_number = ?, first_name = ?, last_name = ?, phone = ?, status = ?
            WHERE id = ?
        """, (employee_number, first_name, last_name, phone, status, invigilator_id))
        connection.commit()
    except sqlite3.IntegrityError:
        connection.close()
        lookup = get_db_connection()
        invigilator = lookup.execute("SELECT * FROM invigilators WHERE id = ?", (invigilator_id,)).fetchone()
        lookup.close()
        return render_template("invigilator_form.html", invigilator=invigilator, error="That employee number is already registered.")
    connection.close()
    flash("Invigilator details saved.", "success")

    return redirect(url_for("admin_invigilators"))


@app.route("/admin/invigilators/delete/<int:invigilator_id>", methods=["POST"])
def delete_invigilator(invigilator_id):
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    try:
        connection.execute("DELETE FROM invigilators WHERE id = ?", (invigilator_id,))
        connection.commit()
    except sqlite3.IntegrityError:
        connection.close()
        flash("This invigilator is assigned to an examination and cannot be deleted.", "error")
        return redirect(url_for("admin_invigilators"))
    connection.close()
    flash("Invigilator deleted.", "success")

    return redirect(url_for("admin_invigilators"))


# ============================================================
# INCIDENT MANAGEMENT (full CRUD)
# ============================================================

@app.route("/admin/incidents")
def admin_incidents():
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    incidents = connection.execute("""
        SELECT incidents.*, students.student_number, students.first_name, students.last_name,
               examinations.course_code
        FROM incidents
        LEFT JOIN students ON incidents.student_id = students.id
        LEFT JOIN examinations ON incidents.examination_id = examinations.id
        ORDER BY incidents.reported_at DESC
    """).fetchall()
    connection.close()

    return render_template("incidents.html", incidents=incidents)


@app.route("/admin/incidents/add", methods=["GET", "POST"])
def add_incident():
    # The legacy incident form exposes a broad student selector and is not
    # candidate/session scoped. Invigilators must use the newer session-bound
    # operations workflow, which validates their assignment and candidate list.
    if invigilator_required():
        flash("Report examination incidents from your assigned examination session.", "info")
        return redirect(url_for("operations.workspace"))
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()

    if request.method == "GET":
        students = connection.execute("SELECT * FROM students ORDER BY first_name").fetchall()
        if invigilator_required():
            assigned = connection.execute("SELECT id FROM invigilators WHERE user_id = ?", (session["user_id"],)).fetchone()
            examinations = connection.execute("SELECT * FROM examinations WHERE invigilator_id = ? ORDER BY examination_date DESC", (assigned["id"],)).fetchall() if assigned else []
        else:
            examinations = connection.execute("SELECT * FROM examinations ORDER BY examination_date DESC").fetchall()
        connection.close()
        return render_template("incident_form.html", students=students, examinations=examinations)

    student_id = request.form.get("student_id")
    examination_id = request.form.get("examination_id")
    incident_type = request.form.get("incident_type")
    description = request.form.get("description")
    severity = request.form.get("severity")

    if not student_id or not examination_id or not incident_type or severity not in {"low", "medium", "high"}:
        students = connection.execute("SELECT * FROM students ORDER BY first_name").fetchall()
        if invigilator_required():
            assigned = connection.execute("SELECT id FROM invigilators WHERE user_id = ?", (session["user_id"],)).fetchone()
            examinations = connection.execute("SELECT * FROM examinations WHERE invigilator_id = ? ORDER BY examination_date DESC", (assigned["id"],)).fetchall() if assigned else []
        else:
            examinations = connection.execute("SELECT * FROM examinations ORDER BY examination_date DESC").fetchall()
        connection.close()
        return render_template("incident_form.html", students=students, examinations=examinations, error="Select a student, examination, incident type and valid severity.")
    if invigilator_required():
        assigned = connection.execute("SELECT id FROM invigilators WHERE user_id = ?", (session["user_id"],)).fetchone()
        valid_exam = connection.execute("SELECT 1 FROM examinations WHERE id = ? AND invigilator_id = ?", (examination_id, assigned["id"] if assigned else -1)).fetchone()
        if not valid_exam:
            connection.close()
            flash("You can report incidents only for examinations assigned to you.", "error")
            return redirect(url_for("add_incident"))
    try:
        connection.execute("""
            INSERT INTO incidents (student_id, examination_id, incident_type, description, severity, status)
            VALUES (?, ?, ?, ?, ?, 'open')
        """, (student_id, examination_id, incident_type.strip(), description, severity))
        connection.commit()
    except sqlite3.IntegrityError:
        connection.close()
        flash("Select a valid registered student and examination, then try again.", "error")
        return redirect(url_for("add_incident"))
    connection.close()
    flash("Incident report recorded.", "success")

    if admin_required():
        return redirect(url_for("admin_incidents"))
    return redirect(url_for("invigilator_dashboard"))


@app.route("/admin/incidents/resolve/<int:incident_id>", methods=["POST"])
def resolve_incident(incident_id):
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    connection.execute("UPDATE incidents SET status = 'resolved' WHERE id = ?", (incident_id,))
    connection.commit()
    connection.close()
    flash("Incident marked as resolved.", "success")

    return redirect(url_for("admin_incidents"))


@app.route("/admin/incidents/delete/<int:incident_id>", methods=["POST"])
def delete_incident(incident_id):
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    connection.execute("DELETE FROM incidents WHERE id = ?", (incident_id,))
    connection.commit()
    connection.close()

    return redirect(url_for("admin_incidents"))


# ============================================================
# REPORTS
# ============================================================

@app.route("/admin/reports")
def admin_reports():
    if not admin_required():
        return redirect(url_for("login"))

    from modules.examination_definitions import ensure_schema as ensure_examination_definition_schema
    ensure_examination_definition_schema()
    connection = get_db_connection()

    by_severity = connection.execute("""
        SELECT severity, COUNT(*) AS total FROM incidents GROUP BY severity
    """).fetchall()

    by_status = connection.execute("""
        SELECT status, COUNT(*) AS total FROM incidents GROUP BY status
    """).fetchall()

    by_course = connection.execute("""
        SELECT examinations.course_code, COUNT(*) AS total
        FROM incidents
        JOIN examinations ON incidents.examination_id = examinations.id
        GROUP BY examinations.course_code
        ORDER BY total DESC
    """).fetchall()

    examination_summary = {row["status"]: row["total"] for row in connection.execute(
        """SELECT CASE status WHEN 'active' THEN 'ongoing' ELSE status END AS status,
                  COUNT(*) AS total
           FROM examination_sessions
           GROUP BY CASE status WHEN 'active' THEN 'ongoing' ELSE status END"""
    ).fetchall()}
    invigilator_summary = {row["status"]: row["total"] for row in connection.execute(
        "SELECT status, COUNT(*) AS total FROM invigilators GROUP BY status"
    ).fetchall()}
    _flagged_students, student_risk_summary = get_student_risk_records(connection)
    total_students = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]

    connection.close()

    return render_template(
        "reports.html",
        by_severity=by_severity,
        by_status=by_status,
        by_course=by_course,
        max_severity=max((row["total"] for row in by_severity), default=0),
        max_status=max((row["total"] for row in by_status), default=0),
        max_course=max((row["total"] for row in by_course), default=0),
        incident_total=sum(row["total"] for row in by_status),
        examination_summary=examination_summary,
        invigilator_summary=invigilator_summary,
        student_risk_summary=student_risk_summary,
        total_students=total_students,
        total_invigilators=sum(invigilator_summary.values())
    )


@app.errorhandler(404)
def page_not_found(_error):
    return render_template("error.html", code=404, message="The page you requested could not be found."), 404


@app.errorhandler(500)
def internal_error(_error):
    app.logger.exception("Unexpected application error")
    return render_template("error.html", code=500, message="The request could not be completed. Please try again."), 500


# ============================================================
# AI ANALYSIS
# A simple, explainable rule-based flagging engine:
#   - Flags a student as "high risk" once they have 2+ incidents.
#   - Flags a student as "critical" once they have any 'high' severity incident.
# This is intentionally rule-based (not a trained ML model) so every
# flag can be explained in the presentation: it's a starting point the
# report identifies as extendable to a trained model later.
# ============================================================

@app.route("/admin/ai-analysis")
def admin_ai_analysis():
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()

    flagged, risk_summary = get_student_risk_records(connection)
    connection.close()
    return render_template("ai_analysis.html", flagged=flagged, risk_summary=risk_summary)


# ============================================================
# SETTINGS
# ============================================================

@app.route("/admin/settings")
def admin_settings():
    if not admin_required():
        return redirect(url_for("login"))

    return render_template("settings.html", username=session.get("username"))


# ============================================================
# INVIGILATOR DASHBOARD
# ============================================================

@app.route("/invigilator")
def invigilator_dashboard():
    if not invigilator_required():
        return redirect(url_for("login"))
    # The session register is authoritative. Do not expose legacy master-row
    # schedule fields as if they were actual invigilator assignments.
    return redirect(url_for("operations.workspace"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
