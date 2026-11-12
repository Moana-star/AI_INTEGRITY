# EIMS Architecture

## Purpose

This document describes the current high-level structure of the Examination Integrity Management System. It reflects the Flask and SQLite code in this repository; it is not a production deployment specification.

## Request and data flow

```mermaid
flowchart TD
    User[Administrator or Invigilator] --> Browser[Browser]
    Browser <--> Flask[Flask routes in app.py]
    Flask --> Access[Session and role checks]
    Flask --> SQL[Parameterized SQLite queries]
    SQL <--> DB[(database/exam_integrity.db)]
    Flask --> Analysis[get_student_risk_records]
    Analysis --> Rules[Incident count and severity rules]
    Rules --> Flask
    Flask --> Templates[Jinja templates]
    Templates --> Browser
    Browser --> Assets[CSS and JavaScript]
```

## Main responsibilities

| Component | Responsibility |
|---|---|
| `app.py` | Flask setup, legacy routes, session handling, role checks, and blueprint registration |
| `modules/institutional_registry.py` | Administrator-only student registry, profile persistence, CSV onboarding, and selected audit events |
| `database/database.py` | SQLite table creation and synthetic demonstration-data seeding |
| `database/exam_integrity.db` | Local runtime database generated during setup; excluded from Git |
| `templates/` | Server-rendered HTML/Jinja pages |
| `static/css/` | Application styling |
| `static/js/` | Browser-side JavaScript |

## Data model

The original database setup defines five core tables:

- `users`: usernames, password hashes, and roles.
- `students`: student identifiers and academic details.
- `invigilators`: invigilator details and optional links to user accounts.
- `examinations`: course, schedule, venue, status, and assigned invigilator.
- `incidents`: incident description, severity, status, and links to a student and examination.

The institutional-registry increment adds the following tables on first access to its routes:

- `student_profiles`: optional academic placement and institutional contact fields linked one-to-one to an existing student.
- `academic_units`: a unit catalogue foundation.
- `student_unit_enrolments`: student-to-unit enrolment foundation by academic year and semester.
- `examination_attendance`: session attendance and verification metadata foundation; no check-in workflow is implemented yet.
- `audit_events`: attribution records for selected registry create, update, and import operations.

These tables are additive. Existing `students`, `incidents`, and other legacy records are not replaced. The new registry interface is served by `modules/institutional_registry.py` at `/admin/registry/students`.

Foreign-key relationships are declared in the schema. The Flask application's database connection enables SQLite foreign-key enforcement for application connections.

## Incident analysis

The `get_student_risk_records` function aggregates incident counts by student and assigns a category:

1. One or more high-severity incidents → Critical.
2. Otherwise, two or more incidents → High.
3. Otherwise, one recorded incident → Watch.

This is deterministic rule-based categorization. It is not a machine-learning model and should only be interpreted as a prompt for human review.
