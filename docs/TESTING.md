# EIMS Manual Testing Checklist

## Purpose and status

Use this checklist to verify the application in a local development environment. This is a test plan, not a report of completed tests. Mark each result only after performing the check.

## Before testing

- [ ] Clone the repository and create a Python virtual environment.
- [ ] Install dependencies from `requirements.txt`.
- [ ] Set a local `FLASK_SECRET_KEY` and unique demonstration passwords.
- [ ] Initialize the database with `python database/database.py`.
- [ ] Start the application with `python app.py`.
- [ ] Confirm the application opens at the local URL printed by Flask.

## Automated registry tests

Run the current automated unit tests from the repository root:

```powershell
python -m unittest discover -v
```

The automated suite covers additive registry and operations schemas, preservation of existing student records, student field normalization, academic-status validation, linked profile persistence, candidate/attendance uniqueness constraints, and incident/student-response schema constraints. GitHub Actions also compiles the application modules before running the tests. This remains a small unit-test foundation, not full application, security, upload, concurrency, or end-to-end coverage.

## Manual test cases

| ID | Area | Action | Expected result | Result |
|---|---|---|---|---|
| T01 | Startup | Start the app after database initialization | Flask starts without an application traceback | Not run |
| T02 | Login | Submit empty login fields | A validation message is displayed | Not run |
| T03 | Login | Submit an incorrect username or password | Login is rejected with a generic error | Not run |
| T04 | Admin access | Sign in with the locally configured admin account | Administrator dashboard opens | Not run |
| T05 | Invigilator access | Sign in with the locally configured invigilator account | Invigilator dashboard opens | Not run |
| T06 | Role access | Open an administrator route while signed out or signed in as an invigilator | Access is redirected or denied | Not run |
| T07 | Staff provisioning | As administrator, provision a staff account with an approved reason | Account and role-audit record are created; credentials are delivered securely | Not run |
| T08 | Registration | Attempt public self-registration with any staff role | Registration is rejected; no account is created | Not run |
| T09 | Students | Create and review a student record as an administrator | The saved record appears in the relevant view | Not run |
| T10 | Examinations | Create or update an examination and assign an invigilator | Saved details appear in the examination view | Not run |
| T11 | Incidents | Record an incident for a valid student and examination | The incident appears in the incident list | Not run |
| T12 | Incident review | Mark an open incident as resolved | Its status changes to resolved | Not run |
| T13 | Analysis | Review synthetic Watch, High, and Critical examples | Categories follow the documented rules | Not run |
| T14 | Logout | Log out and revisit a protected route | The protected page requires the appropriate role | Not run |
| T15 | Registry access | Open `/admin/registry/students` while signed out or as an invigilator | Access is redirected to sign-in | Not run |
| T16 | Registry | Create a student with a unique admission number | Student and linked profile appear in the registry | Not run |
| T17 | Registry | Attempt a duplicate admission number or institutional email | Duplicate is rejected without partial student creation | Not run |
| T18 | Registry | Edit an existing student | Existing student and profile are updated without losing incident links | Not run |
| T19 | CSV import | Import a valid UTF-8 CSV | Valid rows are inserted and import totals are shown | Not run |
| T20 | CSV import | Include a duplicate or invalid row | That row is skipped without leaving a partial student record | Not run |
| T21 | Privacy boundary | Inspect registry forms and database schema | No face image, face embedding, or biometric template is captured or stored | Not run |
| T22 | Audit | Create, edit, and import registry records | Corresponding registry audit events are recorded | Not run |
| T23 | Academic operations | Create a unit and enrol an active student | Enrolment is saved for the selected academic year and semester | Not run |
| T24 | Examination sessions | Create a session linked to a unit | Eligible active enrolments populate the candidate list | Not run |
| T25 | Venue scheduling | Attempt to overlap two sessions in one venue | Conflicting venue booking is rejected | Not run |
| T26 | Invigilator assignment | Assign an invigilator to overlapping sessions | Overlapping assignment is rejected | Not run |
| T27 | Attendance | Check a candidate in and out | Timestamps and audit events are recorded; duplicate events are rejected | Not run |
| T28 | Authorization | Open an unassigned session as an invigilator | Access is denied | Not run |
| T29 | Student portal | Provision an account and sign in with temporary password | Student must change password before portal access | Not run |
| T30 | Student privacy | Open the student portal | Only that student's own profile, enrolments, sessions and incidents are shown | Not run |
| T31 | Student response | Request a response and submit it from the student portal | One immutable response is recorded and visible to authorized reviewer | Not run |
| T32 | Evidence | Upload an invalid type or oversized file | Upload is rejected | Not run |
| T33 | Evidence | Upload valid PDF/JPEG/PNG and download as administrator | File checksum is stored and download access is audited | Not run |
| T34 | Biometric boundary | Inspect attendance UI and provider configuration | No facial matching is claimed or enabled | Not run |

## Recording results

Replace **Not run** with **Pass**, **Fail**, or **Blocked** only after performing each test. Add relevant notes below.

### Test run notes

- Date:
- Python version:
- Operating system:
- Tester:
- Issues observed:

Do not use real student records or personal information when testing this demonstration project.

## Scope

These manual checks do not replace automated unit tests, security testing, accessibility testing, concurrency testing, or a production-readiness review. In particular, verify CSRF protection, account recovery, session configuration, authorization boundaries, and data handling before considering public or institutional deployment.
