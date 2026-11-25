"""MSSQL archive integrity, data preservation and atomic restore checks."""

import gzip
import json
from unittest.mock import patch

import pytest
from click import ClickException
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError

from registry.donor.models import DonorsOverview
from registry.transfer import digest, export_database, restore_archive


def clear_database(db):
    db.session.remove()
    with db.engine.begin() as connection:
        for table in reversed(db.metadata.sorted_tables):
            connection.execute(table.delete())


def assert_empty(db):
    with db.engine.connect() as connection:
        assert all(
            connection.scalar(select(func.count()).select_from(table)) == 0
            for table in db.metadata.sorted_tables
        )


def test_archive_roundtrip_and_nonempty_refusal(db, user, tmp_path):
    archive = tmp_path / "backup.jsonl.gz"
    with db.engine.connect() as connection:
        expected = {
            table.name: digest(connection.execute(select(table)))
            for table in db.metadata.sorted_tables
        }
    export_database(archive)
    with pytest.raises(ClickException, match="not empty"):
        restore_archive(archive)
    clear_database(db)
    restore_archive(archive)
    with db.engine.connect() as connection:
        for table in db.metadata.sorted_tables:
            assert digest(connection.execute(select(table))) == expected[table.name]


@pytest.mark.parametrize(
    "damage",
    [
        "revision",
        "schema",
        "columns",
        "row",
        "checksum",
        "truncated",
        "trailing",
        "gzip",
    ],
)
def test_corrupt_archive_rolls_back_all_tables(db, tmp_path, damage):
    archive = tmp_path / "backup.jsonl.gz"
    export_database(archive)
    with gzip.open(archive, "rt", encoding="utf-8") as source:
        lines = source.readlines()
    if damage == "revision":
        lines[0] = (
            json.dumps({"format": "donors-registry-1", "revision": "wrong"}) + "\n"
        )
    elif damage == "schema":
        lines[1] = json.dumps({"table": "unknown", "columns": []}) + "\n"
    elif damage == "columns":
        header = json.loads(lines[1])
        header["columns"] = []
        lines[1] = json.dumps(header) + "\n"
    elif damage == "row":
        lines[2] = "[]\n"
    elif damage == "checksum":
        lines[-1] = '{"count": -1, "sha256": "wrong"}\n'
    elif damage == "truncated":
        lines = lines[:-1]
    elif damage == "trailing":
        lines.append("{}\n")
    with gzip.open(archive, "wt", encoding="utf-8") as target:
        target.writelines(lines)
    if damage == "gzip":
        archive.write_bytes(b"not a gzip file")
    clear_database(db)
    with pytest.raises(ClickException):
        restore_archive(archive)
    assert_empty(db)


def test_restore_failure_rolls_back_all_tables(db, tmp_path):
    archive = tmp_path / "backup.jsonl.gz"
    export_database(archive)
    clear_database(db)
    with db.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER reject_records ON records AFTER INSERT AS THROW 51000, 'simulated restore failure', 1;"
        )
    try:
        with pytest.raises(SQLAlchemyError, match="simulated restore failure"):
            restore_archive(archive)
        assert_empty(db)
    finally:
        with db.engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER reject_records")


def test_restored_value_mismatch_rolls_back_all_tables(db, tmp_path):
    archive = tmp_path / "backup.jsonl.gz"
    export_database(archive)
    clear_database(db)
    with patch(
        "registry.transfer.digest", return_value={"count": -1, "sha256": "wrong"}
    ):
        with pytest.raises(ClickException, match="Restored values differ"):
            restore_archive(archive)
    assert_empty(db)


def test_failed_overview_refresh_preserves_previous_rows(db):
    table = DonorsOverview.__table__
    before = digest(db.session.execute(select(table)))

    def reject_insert(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO donors_overview"):
            raise RuntimeError("simulated overview failure")

    event.listen(db.engine, "before_cursor_execute", reject_insert)
    try:
        with pytest.raises(RuntimeError, match="simulated overview failure"):
            DonorsOverview.refresh_overview()
        db.session.rollback()
        assert digest(db.session.execute(select(table))) == before
    finally:
        event.remove(db.engine, "before_cursor_execute", reject_insert)


def test_restore_cli(app, db, tmp_path):
    archive = tmp_path / "backup.jsonl.gz"
    export_database(archive)
    clear_database(db)
    result = app.test_cli_runner().invoke(args=["restore-database", str(archive)])
    assert result.exit_code == 0, result.output
    assert "rows verified" in result.output


@pytest.mark.parametrize("change", ["table", "column"])
def test_backup_refuses_unrecognized_database_schema(db, tmp_path, change):
    with db.engine.begin() as connection:
        if change == "table":
            connection.exec_driver_sql("CREATE TABLE unknown_data (value INTEGER)")
        else:
            connection.exec_driver_sql("ALTER TABLE notes ADD unknown_data INTEGER")
    try:
        with pytest.raises(ClickException, match="schema|columns"):
            export_database(tmp_path / "backup.jsonl.gz")
    finally:
        with db.engine.begin() as connection:
            if change == "table":
                connection.exec_driver_sql("DROP TABLE unknown_data")
            else:
                connection.exec_driver_sql("ALTER TABLE notes DROP COLUMN unknown_data")
