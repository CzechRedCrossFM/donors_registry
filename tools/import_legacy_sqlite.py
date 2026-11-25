"""One-time cutover tool. SQLite is read-only input, never an application backend.

Run from the application checkout: python -m tools.import_legacy_sqlite SNAPSHOT
The application DATABASE_URL must point at an empty, migrated MSSQL database.
This tool and the source snapshot are deliberately excluded from production images.
"""

import sqlite3
from pathlib import Path

import click
from sqlalchemy import select

from registry.app import create_app
from registry.extensions import db
from registry.transfer import decode_row, digest, require_empty


def import_snapshot(path):
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as source:
        source.execute("BEGIN")
        if source.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise click.ClickException("Source integrity check failed.")
        revision = source.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision != ("72e643ad5b8c",):
            raise click.ClickException("Upgrade the legacy source before cutover.")
        names = {
            row[0]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'"
            )
        } - {"alembic_version"}
        if names != set(db.metadata.tables):
            raise click.ClickException(
                "Legacy source schema does not match the application."
            )
        with db.engine.begin() as destination:
            require_empty(destination)
            for table in db.metadata.sorted_tables:
                columns = {
                    row[1]
                    for row in source.execute(f'PRAGMA table_info("{table.name}")')
                }
                if columns != set(table.columns.keys()):
                    raise click.ClickException(f"Unexpected columns in {table.name}.")
                sql = (
                    "SELECT "
                    + ", ".join(f'"{column.name}"' for column in table.columns)
                    + f' FROM "{table.name}"'
                )
                batch_size = max(1, 2000 // len(table.columns))
                cursor = source.execute(sql)
                while rows := cursor.fetchmany(batch_size):
                    destination.execute(
                        table.insert(), [decode_row(table, list(row)) for row in rows]
                    )
                original = digest(
                    list(decode_row(table, list(row)).values())
                    for row in source.execute(sql)
                )
                copied = digest(destination.execute(select(table)))
                if original != copied:
                    raise click.ClickException(f"Verification failed for {table.name}.")
                click.echo(f"{table.name}: {original['count']} rows verified")


@click.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def main(path):
    with create_app().app_context():
        import_snapshot(path)


if __name__ == "__main__":
    main()
