"""Verified MSSQL data archives for daily backups and transactional restores."""

import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import click
from flask.cli import with_appcontext
from sqlalchemy import (
    Boolean,
    DateTime,
    LargeBinary,
    func,
    inspect,
    select,
    text,
)

from registry.extensions import db

FORMAT = "donors-registry-1"


def encode_row(row):
    return [
        (
            value.hex()
            if isinstance(value, bytes)
            else value.isoformat() if isinstance(value, datetime) else value
        )
        for value in row
    ]


def decode_row(table, values):
    if not isinstance(values, list) or len(values) != len(table.columns):
        raise click.ClickException(f"Unexpected row in {table.name}.")
    row = {}
    for column, value in zip(table.columns, values):
        if value is not None:
            if isinstance(column.type, LargeBinary) and isinstance(value, str):
                value = bytes.fromhex(value)
            elif isinstance(column.type, DateTime) and isinstance(value, str):
                value = datetime.fromisoformat(value)
            elif isinstance(column.type, Boolean):
                value = bool(value)
        row[column.name] = value
    return row


def row_hash(row):
    return hashlib.sha256(
        json.dumps(encode_row(row), ensure_ascii=False).encode()
    ).digest()


def summary(hashes):
    return {
        "count": len(hashes),
        "sha256": hashlib.sha256(b"".join(sorted(hashes))).hexdigest(),
    }


def digest(rows):
    # shortcut: row hashes fit small databases; use external sorting if job RAM is exceeded.
    return summary([row_hash(row) for row in rows])


def check_schema(connection):
    inspector = inspect(connection)
    if set(inspector.get_table_names()) - {"alembic_version"} != set(
        db.metadata.tables
    ):
        raise click.ClickException("Database schema does not match the application.")
    for table in db.metadata.sorted_tables:
        if {column["name"] for column in inspector.get_columns(table.name)} != set(
            table.columns.keys()
        ):
            raise click.ClickException(f"Unexpected columns in {table.name}.")


def require_empty(connection):
    for table in db.metadata.sorted_tables:
        if connection.scalar(select(func.count()).select_from(table)):
            raise click.ClickException(f"Destination table {table.name} is not empty.")


def export_database(path):
    """Read every table in one SQL Server snapshot transaction."""
    with db.engine.connect() as connection:
        connection.execution_options(isolation_level="SNAPSHOT")
        try:
            with connection.begin(), gzip.open(path, "wt", encoding="utf-8") as output:

                def write(value):
                    output.write(json.dumps(value, ensure_ascii=False) + "\n")

                check_schema(connection)
                revision = connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
                write({"format": FORMAT, "revision": revision})
                for table in db.metadata.sorted_tables:
                    write({"table": table.name, "columns": list(table.columns.keys())})
                    hashes = []
                    for row in connection.execute(select(table)):
                        write(encode_row(row))
                        hashes.append(row_hash(row))
                    write(summary(hashes))
        finally:
            # ODBC can leave an implicit snapshot transaction after resetting isolation.
            connection.execution_options(
                isolation_level=db.engine.dialect.default_isolation_level
            )
            connection.connection.dbapi_connection.commit()
    # Re-read the compressed file before uploading, checking every count and checksum.
    for _ in read_archive(path, revision):
        pass


def read_archive(path, revision):
    """Yield validated rows; a truncated, altered or incompatible archive fails."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as source:
            if json.loads(source.readline()) != {
                "format": FORMAT,
                "revision": revision,
            }:
                raise click.ClickException(
                    "Backup format or migration revision does not match."
                )
            for table in db.metadata.sorted_tables:
                header = json.loads(source.readline())
                if header != {
                    "table": table.name,
                    "columns": list(table.columns.keys()),
                }:
                    raise click.ClickException(f"Unexpected schema for {table.name}.")
                yield "table", table, None
                hashes = []
                while True:
                    value = json.loads(source.readline())
                    if isinstance(value, dict):
                        if value != summary(hashes):
                            raise click.ClickException(
                                f"Verification failed for {table.name}."
                            )
                        yield "end", table, value
                        break
                    row = decode_row(table, value)
                    hashes.append(row_hash(list(row.values())))
                    yield "row", table, row
            if source.read(1):
                raise click.ClickException("Unexpected trailing backup data.")
    except (OSError, EOFError, ValueError, TypeError) as error:
        raise click.ClickException("Invalid or truncated backup archive.") from error


def restore_archive(path):
    """Restore only into an empty migrated schema; any failure rolls back all rows."""
    with db.engine.begin() as connection:
        check_schema(connection)
        require_empty(connection)
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        batch = []
        for kind, table, value in read_archive(path, revision):
            if kind == "row":
                batch.append(value)
            if batch and (
                kind == "end" or len(batch) >= max(1, 2000 // len(table.columns))
            ):
                connection.execute(table.insert(), batch)
                batch.clear()
            if kind == "end":
                if digest(connection.execute(select(table))) != value:
                    raise click.ClickException(
                        f"Restored values differ for {table.name}."
                    )
                click.echo(f"{table.name}: {value['count']} rows verified")


@click.command("restore-database")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@with_appcontext
def restore_database(path):
    """Restore a verified .jsonl.gz backup into an empty MSSQL database."""
    restore_archive(path)


@click.command("backup-database")
@with_appcontext
def backup_database():
    """Upload a verified compressed data archive to private Blob storage."""
    from azure.identity import ManagedIdentityCredential
    from azure.storage.blob import ContainerClient

    with TemporaryDirectory() as directory:
        path = Path(directory) / "database.jsonl.gz"
        export_database(path)
        name = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S-%f.jsonl.gz")
        with ManagedIdentityCredential(
            client_id=os.environ["AZURE_CLIENT_ID"]
        ) as credential:
            with ContainerClient.from_container_url(
                os.environ["BACKUP_CONTAINER_URL"], credential
            ) as container:
                with path.open("rb") as data:
                    container.upload_blob(name, data, overwrite=False)
        click.echo(f"Backup uploaded: {name}")
