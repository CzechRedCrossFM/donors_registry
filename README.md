# donors_registry

Registry of blood donors for Czech Red Cross in Frýdek-Místek.

## Development

Python 3.13 and Microsoft SQL Server are required. Development, tests and production
use the same database engine and one Alembic history in `migrations/`.

1. Install Docker Compose and Microsoft ODBC Driver 18 for SQL Server.
1. Create and activate a Python 3.13 virtual environment.
1. Install dependencies: `pip install -r requirements/dev.txt`.
1. Copy `.env.example` to `.env`. These are local development credentials only.
1. Start the database: `docker compose up -d --wait db`.
1. Create the development database: `docker compose run --rm init-db`.
1. Apply its schema: `flask db upgrade`.
1. Initialize the medal and donation-center lists: `flask init-reference-data`.
1. Create your account: `flask create-user <email> <password>`.
1. Optionally populate a fresh database: `flask install-test-data`.
1. Run the application: `flask run`.

Database files live in the named Docker volume `mssql-data`. Stopping the container
keeps them. **Do not run `docker compose down -v` unless you intend to delete local data.**
The database port is published on localhost only. Self-signed certificate acceptance
in `.env.example` is for the local container; Azure uses certificate validation and
managed identity instead of these development passwords.

## Tests

Start the local database as above, then load the test URL from `.env` and run:

```bash
set -a
. ./.env
set +a
tox -e py313
```

`DONORS_TEST_SERVER_URL` must target the `master` database of a disposable local SQL
Server. Tests create their own randomly named database, reset synthetic data between
tests, and drop that database afterward. They do not use the `donors` development DB.
The login needs permission to create/drop databases. Interrupted runs may leave a
`donors_test_*` database to remove manually after confirming it is not in use.

The complete suite runs against MSSQL in GitHub Actions too. Azure and Blob calls
are mocked; database queries, migrations and backup/restore use real SQL Server.

Run lint checks with `tox -e lint`. To enable checks before commits, install the
extra dependencies and run `pre-commit install`.

## Backups

`flask backup-database` writes a consistent, verified `.jsonl.gz` data archive to
private Blob storage. `flask restore-database /path/to/backup.jsonl.gz` restores into
an empty database with the same migration revision. It validates schema, row counts
and checksums, preserves IDs and password hashes, and rolls back failed restores.
The backup must be paired with this application's migration history and artwork.

## Importing the previous database

SQLite is not an application, development, test-database or backup backend. The
separate `tools/import_legacy_sqlite.py` tool accepts a frozen, read-only snapshot
from the previous release solely for the one-time cutover. It requires source
revision `72e643ad5b8c` and an empty, migrated MSSQL target:

```bash
FLASK_DEBUG=false python -m tools.import_legacy_sqlite /secure/path/to/cutover.sqlite
```

The tool validates every table and refuses to discard unknown tables or columns.
It is excluded from production images. Existing legacy data must be migrated before
starting this version; this application cannot open the old database directly.
