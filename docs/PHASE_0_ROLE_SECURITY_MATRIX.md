# Phase 0 — Role and Security Verification Matrix

**Branch:** `feature/eims-institutional-completion`  
**Review date:** 13 November 2026  
**Purpose:** State what the current automated tests actually exercise. This is not a penetration-test certificate.

## Institutional role boundaries

| Role | Intended access | Explicitly excluded |
|---|---|---|
| Administrator | Institution-wide administration and approved staff provisioning | Still subject to auditability and production safeguards |
| Registrar | Student registry, academic history, enrolment, status and approved biometric enrolment administration | Exam scheduling, attendance recording/reconciliation, incident adjudication |
| Examination officer | Exam/session/venue/seating management, eligibility evaluation, attendance reconciliation, incident review, reports and appeal decisions | Student registry writes and personal student portal access |
| Invigilator | Assigned sessions and candidates, assigned-session attendance, incident reporting and assigned evidence submission | Registry, global scheduling, attendance export/reconciliation, incident adjudication |
| Student | Own profile, academic history, enrolments, schedule, attendance, incident response and appeal | Other students' records, staff workspaces and attendance/incident administration |

The server-side code must enforce these boundaries. Navigation visibility is not an access-control mechanism.

## Existing automated evidence

| Test file | Verified scope |
|---|---|
| `tests/test_access_control.py` | Five defined roles, wildcard admin permission, key allow/deny permissions and unknown-role fail-closed behavior; expanded critical permission matrix |
| `tests/test_blueprint_authorization_matrix.py` | Anonymous denial and a deliberately unauthorized role across registered routes/methods for protected blueprints |
| `tests/test_legacy_admin_authorization_matrix.py` | Legacy `/admin` routes reject registrar, examination officer, invigilator and student sessions |
| `tests/test_staff_authentication.py` | Registrar sign-in, role mismatch rejection, admin staff provisioning with audit reason, public staff registration disabled |
| `tests/test_academic_operations.py` | Registrar attendance denial, invigilator attendance-export denial, assigned-session/candidate scoping |
| `tests/test_identity_review.py` | Assigned invigilator can view only assigned candidates; unassigned invigilator and registrar are denied |
| `tests/test_biometric_attendance_routes.py` | Assigned invigilator verification, fail-closed liveness behavior and duplicate check-in rejection using an isolated fake provider |
| `tests/test_independent_appeals.py` | Student can appeal own case, cannot appeal another student's case, original reporter/reviewer cannot decide their own appeal |
| `tests/test_password_recovery_security.py` | CSRF rejection, safe health endpoint, no username-only password reset |

## Important coverage limits

The route matrix currently uses one selected denied role per blueprint plus anonymous requests. It does **not** exhaustively test every one of the five roles against every route, HTTP method, and object identifier. Positive access is tested in selected workflows, not every endpoint.

Additional work required before institutional acceptance:

1. Generate an endpoint inventory from Flask's live URL map, including methods and blueprint.
2. Assign allowed roles and object-scope rules to every endpoint; no endpoint should be omitted from the inventory.
3. Test each route with anonymous, each wrong role, and each intended role.
4. For student routes, use two students and prove student A cannot read or mutate student B's records.
5. For invigilator routes, use two invigilators and two sessions and prove cross-session access is denied for GET and every state-changing method.
6. Test administrator/registrar/examination-officer separation for all student, eligibility, incident, evidence, attendance and appeal endpoints.
7. Include CSRF, rate-limit, session lifecycle, upload validation and sensitive response caching checks.

## Security controls evidenced in code/tests

- CSRF protection is enabled globally; tests reject a state-changing request without a token.
- Login is rate-limited; production configuration requires shared Redis-compatible storage.
- Browser security headers include content-type sniffing protection, clickjacking protection, referrer policy and camera permissions policy.
- Production startup requires PostgreSQL and a sufficiently long secret key; HTTPS secure-cookie configuration is enabled for production.
- Evidence uses private storage, checksums and audited download paths.
- Biometric processing fails closed unless enabled and institutional approval is configured.

## Security controls not certified

No claim is made that the following are complete or independently verified: MFA, account lockout, full session revocation/expiry, exhaustive object-level authorization, malware scanning, encryption/key custody for backups and evidence, backup restore drills, monitoring/incident response, independent penetration testing, DPIA/lawful-basis review, accessibility, load and concurrency testing.

**Release decision:** Automated baseline tests passing is not a production security certification. The institution's ICT/security and data protection owners must review and approve the system before live student data or biometric processing.
