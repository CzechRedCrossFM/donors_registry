"""The retired database format is accepted only by the separate cutover tool."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from click import ClickException
from sqlalchemy import select

from registry.transfer import digest
from tests.test_database_transfer import assert_empty, clear_database
from tools.import_legacy_sqlite import import_snapshot


def legacy_snapshot(db, path):
    expected = {}
    with db.engine.connect() as source, sqlite3.connect(path) as target:
        target.executescript(
            (Path(__file__).parent / "data/legacy_schema.sql").read_text()
        )
        target.execute("INSERT INTO alembic_version VALUES ('72e643ad5b8c')")
        for table in db.metadata.sorted_tables:
            rows = source.execute(select(table)).all()
            expected[table.name] = digest(rows)
            values = [
                [
                    value.isoformat(" ") if isinstance(value, datetime) else value
                    for value in row
                ]
                for row in rows
            ]
            names = ", ".join(f'"{column.name}"' for column in table.columns)
            placeholders = ", ".join("?" for column in table.columns)
            target.executemany(
                f'INSERT INTO "{table.name}" ({names}) VALUES ({placeholders})', values
            )
        target.execute("ANALYZE")
    return expected


def test_legacy_import_preserves_all_values_and_source(db, user, tmp_path):
    snapshot = tmp_path / "legacy.sqlite"
    expected = legacy_snapshot(db, snapshot)
    before = snapshot.read_bytes()
    with pytest.raises(ClickException, match="not empty"):
        import_snapshot(snapshot)
    clear_database(db)
    import_snapshot(snapshot)
    with db.engine.connect() as connection:
        for table in db.metadata.sorted_tables:
            assert digest(connection.execute(select(table))) == expected[table.name]
    assert snapshot.read_bytes() == before


@pytest.mark.parametrize("change", ["revision", "table", "column", "integrity"])
def test_legacy_import_rejects_unrecognized_input(db, tmp_path, change):
    snapshot = tmp_path / "legacy.sqlite"
    legacy_snapshot(db, snapshot)
    with sqlite3.connect(snapshot) as connection:
        if change == "revision":
            connection.execute("UPDATE alembic_version SET version_num='unsupported'")
        elif change == "table":
            connection.execute("CREATE TABLE unknown_data (value TEXT)")
        elif change == "column":
            connection.execute("ALTER TABLE notes ADD COLUMN unknown_data TEXT")
    if change == "integrity":
        snapshot.write_bytes(b"not a database")
    clear_database(db)
    with pytest.raises((ClickException, sqlite3.DatabaseError)):
        import_snapshot(snapshot)
    assert_empty(db)


def test_legacy_value_mismatch_rolls_back_import(db, tmp_path, monkeypatch):
    snapshot = tmp_path / "legacy.sqlite"
    legacy_snapshot(db, snapshot)
    clear_database(db)
    answers = iter([{"count": 1, "sha256": "before"}, {"count": 1, "sha256": "after"}])
    monkeypatch.setattr("tools.import_legacy_sqlite.digest", lambda rows: next(answers))
    with pytest.raises(ClickException, match="Verification failed"):
        import_snapshot(snapshot)
    assert_empty(db)
