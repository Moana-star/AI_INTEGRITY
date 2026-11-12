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
