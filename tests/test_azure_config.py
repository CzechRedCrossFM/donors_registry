"""Production configuration and health checks must fail safely."""

import runpy
from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError


@pytest.mark.parametrize("debug", ["false", "0"])
def test_production_settings_use_configured_database_and_secret(monkeypatch, debug):
    monkeypatch.setenv("FLASK_DEBUG", debug)
    monkeypatch.setenv(
        "DATABASE_URL",
        "mssql+pyodbc://example.invalid/production?driver=ODBC+Driver+18+for+SQL+Server",
    )
    monkeypatch.setenv("SECRET_KEY", "production-test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    for name, value in {
        "SMTP_SERVER": "example.invalid",
        "SMTP_PORT": "587",
        "SMTP_LOGIN": "test",
        "SMTP_PASSWORD": "test",
        "EMAIL_SENDER": "test@example.invalid",
    }.items():
        monkeypatch.setenv(name, value)
    config = runpy.run_module("registry.settings")
    assert config["DEBUG"] is False
    assert config["SQLALCHEMY_ECHO"] is False
    assert config["SQLALCHEMY_ENGINE_OPTIONS"]["hide_parameters"] is True
    assert (
        config["SQLALCHEMY_DATABASE_URI"]
        == "mssql+pyodbc://example.invalid/production?driver=ODBC+Driver+18+for+SQL+Server"
    )
    assert config["SECRET_KEY"] == "production-test-secret"
    assert config["SESSION_COOKIE_SECURE"] is True


def test_readiness_checks_database_without_breaking_liveness(app, db):
    client = app.test_client()
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    with patch.object(db.engine, "connect", side_effect=SQLAlchemyError("offline")):
        assert client.get("/readyz").status_code == 503
        assert client.get("/healthz").status_code == 200


def test_application_rejects_sqlite():
    from types import SimpleNamespace

    from registry.app import create_app
    from registry.extensions import bcrypt

    previous_rounds = bcrypt.generate_password_hash("settings-check").split(b"$")[2]
    with pytest.raises(ValueError, match="Only MSSQL"):
        create_app(
            SimpleNamespace(
                SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SECRET_KEY="test"
            )
        )
    assert (
        bcrypt.generate_password_hash("settings-check").split(b"$")[2]
        == previous_rounds
    )
