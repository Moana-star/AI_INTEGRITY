# EIMS Authorization Matrix and Review Record

Branch: feature/eims-institutional-completion

## Role matrix

| Capability | Administrator | Registrar | Examination Officer | Invigilator | Student |
|---|---:|---:|---:|---:|---:|
| Institutional staff administration | Yes | No | No | No | No |
| Student registry read/write | Yes | Yes | No | No | Own record only |
| Academic history | Yes | Yes | No | No | Own record only |
| Unit and enrolment administration | Yes | Yes | No | No | Own enrolments |
| Eligibility evidence and evaluation | Yes | Yes | Yes | No | Read own outcome only |
| Eligibility policy approval | Independent admin only | No | No | No | No |
| Examination session and venue management | Yes | No | Yes | No | No |
| View examination sessions | All | No | All | Assigned only | Own schedule |
| View candidate details | All | Registry access | Operational need | Assigned sessions only | Own record |
| Record attendance | Yes | No | Yes | Assigned sessions only | No |
| Attendance exception override | Yes | No | No | No | No |
| Attendance export/reconciliation | Yes | No | Yes | No | No |
| Report examination incident | Yes | No | Yes | Assigned sessions only | No |
| Review incident case | Yes | No | Yes | No | No |
| Upload evidence | Yes | No | Yes | Assigned incidents only | No |
| Download case evidence | Yes | No | Yes | No | No |
| Submit appeal/Senate review | No | No | No | No | Own case only |
| Record Senate verdict / review queue | Yes | Registrar workflow | Review queue | No | No |

## Implemented server-side controls

- Student registry blueprint denies all roles except administrator and registrar.
- Operations blueprint requires authenticated institutional staff; each write route has narrower role checks.
- Invigilator attendance and identity pages verify assignment to the specific session.
- Invigilator incident list/detail/evidence routes scope to examinations or sessions assigned to that invigilator.
- Attendance CSV export and attendance reconciliation are restricted to administrator/examination officer.
- Registrar cannot view or record examination attendance.
- Eligibility routes require authenticated administrator, registrar or examination officer; policy approval is administrator-only and requires a different administrator from the creator.
- Incident review decisions are administrator/examination-officer only and prevent the original reporter from reviewing their own case.
- Evidence download is administrator/examination-officer only and audited.
- Student portal queries are constrained by the authenticated student ID; student incident response and appeals require ownership checks.
- Senate review submission is constrained to the signed-in student's own verdict and the 21-day period.
- Biometric enrolment is administrator/registrar only; live biometric attendance is administrator/examination officer or the session's assigned invigilator.
- Invigilator workspace context is now restricted to assigned sessions, those sessions' candidates, linked units/venues and examinations. It no longer receives the institution-wide student and examination lists.

## Automated coverage

- tests/test_access_control.py: role and permission semantics.
- tests/test_academic_operations.py: registrar attendance denial, invigilator export denial, and assigned-session/candidate context isolation.
- tests/test_integrity_and_student_portal.py: incident and student self-service controls.
- tests/test_independent_appeals.py: student ownership and independent appeal review.
- tests/test_senate_review.py: own-verdict submission and review-period boundary.
- tests/test_biometric_attendance_routes.py: invigilator assignment, eligible candidate, provider result, liveness and duplicate check-in controls.

## Known remaining security work (do not claim complete)

1. Add a parameterized route-permission test for every registered route and every role, including negative method tests; current tests cover critical boundaries but not the complete URL map.
2. Complete object-level authorization review for all legacy app.py routes and every evidence/incident attachment access path.
3. Add staff MFA and institutional SSO, account disable/revocation and session revocation.
4. Add security testing for CSRF on every state-changing form, brute-force throttling, session fixation, password reset and credential delivery.
5. Add PostgreSQL row-level protections/constraints only after the production schema migration; application authorization remains mandatory.
6. Independent penetration test and university ICT sign-off.

## Review principle

A UI menu is not an access control. Every protected request must be denied at the server, and every object must be checked against the requesting user's role, assignment or student ownership. Any unrecognized role or missing ownership/assignment must fail closed.
