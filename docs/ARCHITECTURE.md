# EIMS Architecture

## Current development architecture

The current feature branch uses a modular Flask application with server-rendered Jinja templates and a shared SQLite database.

```mermaid
flowchart TD
    USERS[Administrator, Invigilator, Student] --> WEB[Browser]
    WEB --> APP[Flask Application]
    APP --> AUTH[Existing staff sessions and student portal accounts]
    APP --> REG[Institutional Student Registry]
    APP --> OPS[Academic Operations]
    APP --> ATT[Attendance Workflows]
    APP --> CASE[Incident Case Review]
    APP --> EVID[Private Evidence Storage]
    APP --> PORTAL[Student Self-Service]
    REG --> DB[(SQLite Database)]
    OPS --> DB
    ATT --> DB
    CASE --> DB
    PORTAL --> DB
    CASE --> EVID
    DB --> AUDIT[Audit and Review Events]
```

## Module responsibilities

| Module | Responsibility |
|---|---|
| `app.py` | Flask application, existing legacy routes, staff authentication and blueprint registration |
| `modules/institutional_registry.py` | Admission-number-based student profiles, CSV import and profile audit events |
| `modules/operations.py` | Academic units, enrolments, venues, examination sessions, candidate lists, seat labels, invigilator assignments and attendance |
| `modules/integrity.py` | Incident case workflow, review history, evidence upload/download and evidence audit events |
| `modules/student_portal.py` | Student account provisioning, authentication, academic/exam views, password change and incident responses |
| `database/database.py` | Existing SQLite schema creation and optional synthetic demonstration seeding |
| `templates/` | Server-rendered user interfaces |
| `static/` | CSS and browser-side JavaScript |

## Data flow

1. An authorized administrator creates or imports a student record. Admission number is unique.
2. The administrator creates academic units and registers active students for a unit by academic year and semester.
3. The administrator creates an examination session linked to an existing examination and optionally to an academic unit.
4. Candidate records are derived from active enrolments for the matching academic year and semester.
5. The venue capacity is checked against the derived candidate count. Seat labels are assigned sequentially.
6. An administrator assigns invigilators to the session.
7. Assigned invigilators record student-card or manual identity checks and check-in/check-out events.
8. Student portal users see only their own profile, enrolments, candidate sessions, attendance and incident notices.
9. An authorized reviewer manages incident workflow statuses, records review notes and requests a student response.
10. Students can submit one response to an incident when a response has been requested. Evidence is stored outside the public static directory and checksummed.

## Database strategy

The current feature branch is still SQLite-based. New tables are created additively and use foreign keys and uniqueness constraints where practical. Existing student, examination and incident tables are preserved.

SQLite is suitable for local development and controlled functional testing. It is not the approved final database for a multi-user university deployment. A PostgreSQL migration requires a deliberate data migration, transaction/concurrency review, backup and rollback plan, and end-to-end regression testing.

## Identity verification boundary

Attendance supports manual document checks and recording that a student card was checked. The system does not currently scan cards, read QR/barcodes, capture faces, compare biometric templates or perform liveness detection. A biometric provider adapter and institutional approval are prerequisites for any face verification pilot.

## Security boundary

The current code has password hashing for provisioned student accounts and existing staff accounts, role checks on new workflows, private evidence storage and selected audit records. It does not yet implement full institutional RBAC, CSRF protection, MFA, login rate limiting, encrypted evidence storage, malware scanning, automated retention or production monitoring. See [Production Readiness](PRODUCTION_READINESS.md).
