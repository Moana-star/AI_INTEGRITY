# Self-hosted EIMS deployment starter

This package runs EIMS with PostgreSQL, Redis, Gunicorn and persistent evidence storage. It is an operational self-hosted starting point, not a declaration that the university has approved a production deployment.

## Local/staging startup

Requirements: Docker Engine and Docker Compose v2.

1. Copy .env.example to .env.
2. Generate unique secrets. For the database password, use URL-safe hexadecimal output so it can be placed in DATABASE_URL without URL-encoding issues:

   \`\`\`powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   \`\`\`

3. Set POSTGRES_PASSWORD, FLASK_SECRET_KEY, EIMS_BOOTSTRAP_ADMIN_USERNAME and EIMS_BOOTSTRAP_ADMIN_PASSWORD in .env. Never commit .env.
4. Start the stack:

   \`\`\`bash
   docker compose up --build -d
   \`\`\`

5. Check service health:

   \`\`\`bash
   docker compose ps
   docker compose logs web
   \`\`\`

6. Open http://127.0.0.1:8000 from the host machine and sign in using the first administrator credentials you supplied. Provision the remaining staff accounts through the protected institutional account workflow.

The web port is bound to loopback only. The starter sets FLASK_HTTPS=0 for local/staging access and must not be exposed directly to the public internet.

## First-start behavior

scripts/bootstrap_postgres.py checks the target PostgreSQL schema:
- Empty database: creates an empty-first SQLite schema snapshot with one deployment-provisioned administrator, then uses the guarded migration utility to initialize PostgreSQL.
- Existing EIMS database: verifies that core tables exist and makes no changes.
- Partial/unknown schema: stops rather than overwriting data.

No fictional student, examination, attendance or incident records are inserted. Demo data requires a separate explicit --demo command and is not used by this container entrypoint.

## Public production deployment requirements

Before public access:
- Put the web service behind an institution-approved TLS reverse proxy or ingress.
- Set FLASK_HTTPS=1 so session cookies are Secure.
- Restrict PostgreSQL and Redis to the private application network.
- Use a managed secret store and rotate credentials.
- Configure encrypted database and evidence backups, retention, restore drills, monitoring and incident response.
- Set institution-approved RPO/RTO and verify recovery.
- Complete the PostgreSQL full-workflow, security, accessibility, load and institutional acceptance gates in the acceptance pack.

This Compose file does not implement TLS termination, encrypted backup storage or disaster recovery. Do not treat docker compose up as institutional production approval.

## Operations

Stop without deleting persistent data:

\`\`\`bash
docker compose down
\`\`\`

Do not use docker compose down -v on an environment containing records; -v deletes the persistent PostgreSQL, Redis and evidence volumes.

To inspect logs:

\`\`\`bash
docker compose logs --tail=200 web db redis
\`\`\`

Use a reviewed database migration and a verified backup for schema changes. Do not delete the database volume to solve migration failures.
