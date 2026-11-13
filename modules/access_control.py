"""Central, deny-by-default role permissions for the institutional EIMS.

Roles are institutional job functions, not UI labels. Route handlers must check
permissions server-side; hiding navigation items is never an authorization rule.
"""
from __future__ import annotations

ROLES = frozenset({
    "admin",
    "registrar",
    "examination_officer",
    "invigilator",
    "student",
})

# Permission keys are deliberately granular so route groups can be migrated
# without granting broad access to an entire subsystem.
ROLE_PERMISSIONS = {
    "admin": frozenset({"*"}),
    "registrar": frozenset({
        "registry.read", "registry.write",
        "academic_history.read", "academic_history.write",
        "unit_enrolment.read", "unit_enrolment.write",
        "student_status.read", "student_status.write",
    }),
    "examination_officer": frozenset({
        "exams.read", "exams.write", "eligibility.read", "eligibility.evaluate",
        "sessions.read", "sessions.write", "venues.read", "venues.write",
        "seating.read", "seating.write", "invigilator_assignment.write",
        "attendance.read", "attendance.reconcile", "reports.read",
        "incidents.read", "incidents.review", "appeals.review",
    }),
    "invigilator": frozenset({
        "assigned_sessions.read", "assigned_candidates.read",
        "attendance.read_assigned", "attendance.record",
        "incidents.report_assigned", "incidents.evidence_upload_assigned",
    }),
    "student": frozenset({
        "own_profile.read", "own_academic_history.read",
        "own_enrolments.read", "own_schedule.read",
        "own_attendance.read", "own_incidents.read",
        "own_incidents.respond", "own_incidents.appeal",
    }),
}


def normalize_role(role: object) -> str | None:
    """Return a known role, otherwise None (unknown roles never gain access)."""
    if not isinstance(role, str):
        return None
    normalized = role.strip().lower()
    return normalized if normalized in ROLES else None


def has_permission(role: object, permission: str) -> bool:
    """Check one permission. Unknown roles and permissions are denied."""
    normalized = normalize_role(role)
    if normalized is None or not isinstance(permission, str) or not permission:
        return False
    permissions = ROLE_PERMISSIONS[normalized]
    return "*" in permissions or permission in permissions


def permissions_for(role: object) -> frozenset[str]:
    """Return the immutable permission set for a known role, else empty."""
    normalized = normalize_role(role)
    return ROLE_PERMISSIONS.get(normalized, frozenset())


STAFF_ROLES = frozenset(ROLES - {"student"})


def ensure_role_schema(connection):
    """Add role metadata without rebuilding or deleting legacy user records.

    The old users.role CHECK constraint only accepts admin/invigilator. Keep
    that column as a compatibility field while institutional_role becomes the
    authoritative five-role assignment. This additive migration is repeatable.
    """
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "users" not in tables:
        raise RuntimeError("The users table must be initialized before role migration.")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "institutional_role" not in columns:
        connection.execute("""
            ALTER TABLE users ADD COLUMN institutional_role TEXT
            CHECK (institutional_role IS NULL OR institutional_role IN
            ('admin','registrar','examination_officer','invigilator'))
        """)
    connection.execute("""
        UPDATE users SET institutional_role=role
        WHERE institutional_role IS NULL AND role IN ('admin','invigilator')
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS institutional_staff_profiles (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            employee_number TEXT UNIQUE,
            department TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS institutional_role_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            target_user_id INTEGER NOT NULL,
            previous_role TEXT,
            new_role TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(actor_user_id) REFERENCES users(id),
            FOREIGN KEY(target_user_id) REFERENCES users(id)
        )
    """)
    connection.commit()


def effective_user_role(user):
    """Resolve the new role column with safe legacy fallback."""
    if user is None:
        return None
    keys = user.keys() if hasattr(user, "keys") else ()
    role = user["institutional_role"] if "institutional_role" in keys else None
    role = role or (user["role"] if "role" in keys else None)
    return normalize_role(role)


def legacy_role_for(role):
    """Map institutional staff roles to the constrained legacy role column."""
    normalized = normalize_role(role)
    if normalized not in STAFF_ROLES:
        raise ValueError("A valid institutional staff role is required.")
    return "admin" if normalized == "admin" else "invigilator"
