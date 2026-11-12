# Kisii University EIMS — role authorization model

## Institutional roles

This role model defines five distinct roles. It is a server-side authorization
contract; navigation visibility is not a security boundary.

| Role | Intended responsibility | Explicit restrictions |
|---|---|---|
| Administrator | System configuration, user administration and exceptional oversight | Privileged actions must still be audited and protected |
| Registrar | Student registry, academic history, programme/unit enrolment and academic status | Cannot schedule examinations, investigate incidents or decide appeals |
| Examination Officer | Examination setup, eligibility review, timetable, venues, seating, invigilator allocation, attendance reconciliation, reporting and incident/appeal review | Cannot silently alter registrar-owned academic records |
| Invigilator | Assigned-session candidate list, identity checks, attendance events and incident reporting | Cannot access unassigned sessions, alter eligibility or decide incidents |
| Student | Own profile, academic history, enrolments, schedule, attendance, incident response and appeal | Must never access another student's records or staff operations |

## Implementation status

- `modules/access_control.py` defines the five roles and granular permission keys.
- Unknown roles and permission keys are denied by default.
- Unit tests cover the permission matrix and negative cases.
- This is the authorization policy foundation. Existing route guards and the
  legacy SQLite `users.role` constraint still need migration and integration
  before the five roles are operational end-to-end.
- Do not provision live staff accounts until the role migration, authentication
  integration, account recovery, MFA policy and authorization tests are complete.

## Kisii University policy configuration still required

The system must not invent faculty/department structures, programme codes,
academic progression rules, examination eligibility thresholds, supplementary
exam rules, deferment/suspension handling, or appeal deadlines. Load these from
approved university policies and authorized data sources.

## Biometric decision

No provider has been approved. Camera capture and live one-to-one matching
remain disabled. A camera preview, if later implemented, must not persist frames
or transmit them to a third party until the institution has approved the provider,
processing purpose, legal basis, DPIA, retention, security and alternative
manual verification procedure.
