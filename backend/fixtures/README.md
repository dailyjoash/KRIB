# KRIB fixtures

This directory previously contained `sqlite_migration.json`, a dump of an
early-development SQLite database that included real-looking emails, phone
numbers, and `pbkdf2_sha256` password hashes for users created during local
testing. That file was cleared on the security-hardening pass because
committing PII or password hashes (even synthetic-looking ones) creates
privacy and credential-reuse risk if the repo is ever exposed.

The placeholder `sqlite_migration.json` here is an empty JSON array so any
script that calls `loadfixtures` keeps working without re-introducing PII.

If you need demo accounts in local development, use the management command
that ships with the app instead:

```bash
python manage.py seed_krib   # only runs with DJANGO_DEBUG=1
```

That command builds synthetic landlord/manager/tenant accounts and seeds a
fresh database without committing any data to source control.

History note: if older commits still contain the original fixture, rewrite
history with `git filter-repo --path backend/fixtures/sqlite_migration.json
--invert-paths` (coordinate with the team — this changes commit SHAs).
