# -*- coding: utf-8 -*-
"""Defines fixtures available to all tests."""

import logging
import os
from itertools import cycle
from random import sample, shuffle
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch
from uuid import uuid4

from flask_migrate import upgrade
from pytest import fixture
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from webtest import TestApp

from registry.app import create_app
from registry.donor.models import DonorsOverview, IgnoredDonors, Note
from registry.extensions import db as _db
from registry.list.seed import seed_reference_data
from registry.user.models import User

from .utils import (
    get_test_data_df,
    test_data_ignored,
    test_data_medals,
    test_data_notes,
    test_data_overrides,
    test_data_records,
)

TEST_RECORDS = 1000  # Number of test imports to use in test database


@fixture(scope="session")
def app():
    """Create and destroy only this run's random database on a disposable server."""
    from tests import settings

    url = make_url(os.environ["DONORS_TEST_SERVER_URL"])
    if url.drivername != "mssql+pyodbc" or url.database != "master":
        raise ValueError(
            "DONORS_TEST_SERVER_URL must target a disposable MSSQL master database"
        )
    name = "donors_test_" + uuid4().hex
    server = create_engine(url, isolation_level="AUTOCOMMIT")
    with server.connect() as connection:
        connection.exec_driver_sql(
            f"CREATE DATABASE [{name}] COLLATE Czech_100_CI_AS_SC_UTF8"
        )
        connection.exec_driver_sql(
            f"ALTER DATABASE [{name}] SET ALLOW_SNAPSHOT_ISOLATION ON"
        )
    settings.SQLALCHEMY_DATABASE_URI = url.set(database=name)
    application = create_app(settings)
    application.logger.setLevel(logging.CRITICAL)
    context = application.test_request_context()
    context.push()
    try:
        upgrade()
        seed_reference_data()
        test_data_records(_db, limit=TEST_RECORDS)
        test_data_medals(_db)
        test_data_overrides(_db)
        test_data_ignored(_db, limit=3)
        test_data_notes(_db)
        DonorsOverview.refresh_overview()
        with _db.engine.connect() as connection:
            application.config["TEST_BASELINE"] = {
                table.name: [
                    dict(row) for row in connection.execute(select(table)).mappings()
                ]
                for table in _db.metadata.sorted_tables
            }
        yield application
    finally:
        _db.session.remove()
        _db.engine.dispose()
        context.pop()
        with server.connect() as connection:
            connection.exec_driver_sql(
                f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE"
            )
            connection.exec_driver_sql(f"DROP DATABASE [{name}]")
        server.dispose()


@fixture
def testapp(app):
    return TestApp(app)


@fixture(autouse=True)
def db(app):
    """Reset synthetic data while allowing real commits and backup connections."""
    _db.session.remove()
    with _db.engine.begin() as connection:
        for table in reversed(_db.metadata.sorted_tables):
            connection.execute(table.delete())
        for table in _db.metadata.sorted_tables:
            rows = app.config["TEST_BASELINE"][table.name]
            chunk = max(1, 2000 // len(table.columns))
            for start in range(0, len(rows), chunk):
                connection.execute(table.insert(), rows[start : start + chunk])
    yield _db
    _db.session.remove()


@fixture(scope="function")
def user(db):
    """Create user for the tests."""
    user = User("test@example.com", "test123")
    user.test_password = "test123"
    user.active = True
    db.session.add(user)
    # The user might already exists in the db and we cannot
    # combine session-scoped and function-scoped fixtures
    # so we have to be ready for that situation.
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return user


@fixture(scope="session")
def test_data_df():
    """The same data we have in test database but in form of Pandas DataFrame"""
    return get_test_data_df(TEST_RECORDS)


def sample_of_rc(amount=100):
    """Yields random sample of RC from test data"""
    test_data = get_test_data_df(TEST_RECORDS)
    dcs = test_data.MISTO_ODBERU.unique()
    shuffle(dcs)
    dcs = cycle(dcs)

    for _ in range(amount):
        dc = next(dcs)
        yield sample(list(test_data[test_data.MISTO_ODBERU == dc].RC.unique()), 1)[0]


def new_rc_if_ignored(rodne_cislo):
    while True:
        if _db.session.get(IgnoredDonors, rodne_cislo):
            rodne_cislo = next(sample_of_rc(1))
            continue
        return rodne_cislo


@fixture(scope="session", autouse=True)
def empty_stamp_png():
    with NamedTemporaryFile(
        dir="registry/static/stamps", suffix=".png"
    ), NamedTemporaryFile(dir="registry/static/signatures", suffix=".png"):
        yield


@fixture
def mock_smtp():
    with patch("smtplib.SMTP", autospec=True) as mock_smtp_class:
        mock_instance = mock_smtp_class.return_value
        mock_instance.send_message = MagicMock()
        yield mock_instance


def delete_note_if_exists(rodne_cislo):
    if (note := _db.session.get(Note, rodne_cislo)) is not None:
        _db.session.delete(note)
        _db.session.commit()
