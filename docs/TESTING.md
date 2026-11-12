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

The initial registry tests cover additive schema creation, preservation of existing student records, field normalization, academic-status validation, and linked profile persistence. A GitHub Actions workflow runs this command for pushes to the feature branch and pull requests targeting main. The tests do not constitute full application, security, import-file, or end-to-end coverage.

## Manual test cases

| ID | Area | Action | Expected result | Result |
|---|---|---|---|---|
| T01 | Startup | Start the app after database initialization | Flask starts without an application traceback | Not run |
| T02 | Login | Submit empty login fields | A validation message is displayed | Not run |
| T03 | Login | Submit an incorrect username or password | Login is rejected with a generic error | Not run |
| T04 | Admin access | Sign in with the locally configured admin account | Administrator dashboard opens | Not run |
| T05 | Invigilator access | Sign in with the locally configured invigilator account | Invigilator dashboard opens | Not run |
| T06 | Role access | Open an administrator route while signed out or signed in as an invigilator | Access is redirected or denied | Not run |
| T07 | Registration | Register a new invigilator with valid details | Account is created and can sign in | Not run |
| T08 | Registration | Attempt self-registration with the administrator role | Registration is rejected | Not run |
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
