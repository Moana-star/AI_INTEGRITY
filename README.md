# Examination Integrity Management System (EIMS)

A Flask and SQLite web application for managing examination operations and recording, reviewing, and reporting examination incidents. The system provides separate administrator and invigilator experiences, structured records, and an explainable rule-based student risk analysis.

> **Project status:** Academic / demonstration project. The seeded demonstration records are synthetic. Risk labels are rule-based indicators for review; they are not proof of misconduct and should not be used as an automated disciplinary decision.

## Overview

The Examination Integrity Management System is designed to support the administrative work around examinations. Administrators can manage student, examination, and invigilator records, review incident reports, and view summaries. Invigilators can access their assigned examinations and record observations.

The application uses a transparent rules engine to summarize incident patterns. It does not use a trained machine-learning model.

## Key features

- **Role-based access:** separate administrator and invigilator sign-in experiences.
- **Account registration:** invigilators can self-register through the registration page.
- **Student management:** create, view, update, and delete student records, subject to linked-record constraints.
- **Examination management:** manage examination details, schedules, venues, statuses, and invigilator assignments.
- **Invigilator management:** maintain invigilator records and status.
- **Incident management:** record incidents with descriptions, severity levels, and open/resolved statuses.
- **Explainable risk analysis:** summarize incident patterns using explicit rules:
  - **Watch:** one lower-severity incident.
  - **High:** two or more recorded incidents, with no high-severity incident.
  - **Critical:** at least one high-severity incident.
- **Reports and dashboards:** view examination, incident, and risk summaries.
- **SQLite persistence:** store application records locally in a SQLite database.

## Technology stack

- Python
- Flask
- SQLite
- HTML
- CSS
- JavaScript
- Werkzeug password hashing (used through Flask's Werkzeug dependency)

## Project structure

```text
AI_INTEGRITY/
├── app.py
├── database/
│   └── database.py
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── auth.js
├── templates/
│   ├── admin_dashboard.html
│   ├── ai_analysis.html
│   ├── base.html
│   ├── examination_form.html
│   ├── examinations.html
│   ├── incident_form.html
│   ├── incidents.html
│   ├── invigilator_dashboard.html
│   ├── invigilator_form.html
│   ├── invigilators.html
│   ├── login.html
│   ├── register.html
│   ├── reports.html
│   ├── student_form.html
│   ├── students.html
│   └── ...
└── .gitignore
```

## Requirements

- Python 3.9 or newer
- pip

## Run locally

### 1. Clone the repository

```bash
git clone https://github.com/Moana-star/AI_INTEGRITY.git
cd AI_INTEGRITY
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

```powershell
python -m venv v
.\v\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can run the app using the virtual environment's Python executable directly (shown below), or use Command Prompt activation:

```cmd
v\Scripts\activate.bat
```

### 3. Install Flask

```bash
python -m pip install Flask
```

### 4. Configure a local administrator account

The database setup script can create demonstration login accounts from environment variables. Set passwords before building the database; do not put real passwords in source code or commit them to Git.

**Windows PowerShell**

```powershell
$env:DEMO_ADMIN_PASSWORD = "Choose-A-Strong-Local-Password"
$env:DEMO_INVIGILATOR_PASSWORD = "Choose-Another-Strong-Password"
$env:FLASK_SECRET_KEY = "Replace-With-A-Long-Random-Secret"
```

These values apply to the current PowerShell session. Choose your own passwords and secret; do not reuse the example strings.

### 5. Create the SQLite database

From the project root, run:

```bash
python database/database.py
```

This creates `database/exam_integrity.db` and seeds synthetic demonstration records. The database file is intentionally excluded from version control by `.gitignore`.

If you run the setup script again, it uses `INSERT OR IGNORE` for many seeded records; it is not a substitute for a database migration or backup strategy.

### 6. Start the Flask application

```bash
python app.py
```

Open the local address printed by Flask in your browser (normally http://127.0.0.1:5000).

For local development, you may enable Flask debug mode in PowerShell before starting the app:

```powershell
$env:FLASK_DEBUG = "1"
python app.py
```

Do not enable debug mode in a public production deployment.

## Demonstration accounts

If you set `DEMO_ADMIN_PASSWORD` and `DEMO_INVIGILATOR_PASSWORD` before running `python database/database.py`, the setup script provisions:

| Role | Username | Password |
|---|---|---|
| Administrator | `admin` | The value you set in `DEMO_ADMIN_PASSWORD` |
| Invigilator | `jkamau` | The value you set in `DEMO_INVIGILATOR_PASSWORD` |

If the database was already created before setting these variables, set them and run the database setup script again. Use only local demonstration credentials.

Invigilators can also register through the application's registration page. Self-registration is restricted to the invigilator role.

## How the risk analysis works

The analysis is deliberately transparent and deterministic. It counts recorded incidents for each student and assigns a review category using the following rules:

| Condition | Displayed category |
|---|---|
| At least one high-severity incident | Critical |
| Two or more incidents, with no high-severity incident | High |
| One lower-severity incident | Watch |

These labels are intended to help administrators prioritize record review. They do not establish intent, guilt, or a finding of academic misconduct. All incidents should be assessed in context and through the institution's established procedures.

## Important implementation notes

- Passwords are stored as Werkzeug password hashes rather than plaintext.
- The application uses parameterized SQLite queries for database operations.
- The Flask secret key should be supplied through the `FLASK_SECRET_KEY` environment variable and kept private.
- The forgot-password flow is a **local demonstration flow**. It does not send email or verify a user's identity; it is not suitable for production account recovery.
- The project uses a local SQLite database. For a real institutional deployment, assess database backups, access controls, audit requirements, privacy obligations, HTTPS, CSRF protection, deployment configuration, and operational security before use.
- Do not commit real student information, passwords, API keys, or a populated local database.

## Future improvements

Potential extensions include automated tests, stronger account-recovery verification, CSRF protection, audit logging, configurable institutional policies, database migrations, and deployment with a production-grade WSGI server and managed database.

## Author

**Moana-star**

GitHub: [https://github.com/Moana-star](https://github.com/Moana-star)

---

This repository is an academic software project demonstrating web application development, relational data management, role-based workflows, and explainable rule-based analysis.
