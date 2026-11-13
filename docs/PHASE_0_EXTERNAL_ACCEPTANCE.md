# Phase 0 external acceptance package

This document contains the two acceptance procedures that cannot be truthfully completed by repository inspection alone.

## A. Clean Windows workstation installation

Run in a new PowerShell window. This uses a separate clone and does not alter an existing working directory.

```powershell
git clone --branch feature/eims-institutional-completion https://github.com/Moana-star/AI_INTEGRITY.git AI_INTEGRITY-phase0-clean
Set-Location AI_INTEGRITY-phase0-clean

py --version
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Compile and run the automated suite before initializing a local database.
python -m compileall -q app.py modules tests
python -m unittest discover -v
```

### Initialize the empty local database and first administrator

The application does not create its foundational tables or a default administrator during a login request. Initialize the database explicitly before starting Flask. This prevents an uninitialized database from being mistaken for an authentication failure and avoids shipping a shared default password.

In the same PowerShell session, choose an administrator username and enter a unique password of at least 16 characters. The password prompt below is masked and the temporary environment variables are cleared immediately after initialization:

```powershell
$adminUsername = Read-Host "Choose the initial administrator username"
$securePassword = Read-Host "Enter a unique administrator password (minimum 16 characters)" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $env:EIMS_BOOTSTRAP_ADMIN_USERNAME = $adminUsername.Trim().ToLower()
    $env:EIMS_BOOTSTRAP_ADMIN_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    python database/database.py
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    Remove-Item Env:EIMS_BOOTSTRAP_ADMIN_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:EIMS_BOOTSTRAP_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    Remove-Variable securePassword, passwordPointer, adminUsername -ErrorAction SilentlyContinue
}
```

Confirm that the initializer reports that the database is ready and that the initial administrator was provisioned. Do not run `--demo` for this clean institutional-installation check. The default database is empty of student, examination and incident records.

### Start and verify the application

In the first PowerShell window:

```powershell
python app.py
```

In a second PowerShell window, from the same repository directory:

```powershell
Invoke-WebRequest http://127.0.0.1:5000/healthz -UseBasicParsing
```

Expected readiness response: HTTP 200 with `{"status":"ok"}`. Then open `http://127.0.0.1:5000/login` and sign in with the administrator credentials entered during initialization. Stop the app with Ctrl+C.

Record the Windows version, Python version, pip installation result, complete test summary, database initialization output, startup log, health response and successful administrator login. Redact secrets and never use live student records. If a command fails, preserve the complete error text; do not mark installation passed.

## B. Independent security assessment

The assessor must be separate from the developer and must receive a test deployment with synthetic data, written scope, test accounts for all five roles and explicit authorization to test. Do not provide production student data or real biometric captures.

Minimum scope:
1. Authentication: password policy, login throttling, account enumeration, staff provisioning, student account provisioning, recovery, logout and session lifecycle.
2. Authorization: every URL rule and HTTP method as anonymous and as each of admin, registrar, examination officer, invigilator and student; verify object ownership and assigned-session boundaries with two students and two invigilators.
3. CSRF and browser controls: every state-changing endpoint, cookies, HTTPS, security headers, CORS and content security policy.
4. Data protection: SQL injection, stored/reflected XSS, IDOR, sensitive response caching, exports, logs, private evidence downloads, upload size/type validation and malware handling.
5. Evidence integrity: checksum validation, append-only histories, evidence access audit, case-review conflicts and appeal independence.
6. Infrastructure: PostgreSQL privileges/TLS, Redis rate limiting, secret storage, backup encryption, restore, container non-root operation, dependency and image vulnerability scanning.
7. Biometric boundary: confirm disabled-by-default/fail-closed behavior; do not enable a provider or collect biometric data during assessment without institution approval and a DPIA.

Deliverables required:
- assessor identity/organization and assessment date;
- tested commit SHA and deployment/configuration description;
- scope, methodology and limitations;
- finding severity, reproduction steps and affected routes/data;
- remediation recommendations and retest evidence;
- explicit residual-risk statement and signed acceptance by institutional ICT/security and data protection owners.

A passing CI run, internal source review, or this checklist is not an independent penetration test. Phase 0 security sign-off remains open until the independent report and institutional acceptance are attached.
