"""Offline Azure boundaries; run with requirements/azure.txt installed."""

import gzip
import runpy
import struct
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import create_engine

pytest.importorskip("azure.storage.blob")
pytest.importorskip("pyodbc")

from registry.assets import sync_assets  # noqa: E402
from registry.database import configure_sql_auth  # noqa: E402


def test_gzip_backup_upload_and_assets(app, db, tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_CLIENT_ID", "test-identity")
    monkeypatch.setenv("BACKUP_CONTAINER_URL", "https://example.invalid/backups")
    monkeypatch.setenv("ASSET_CONTAINER_URL", "https://example.invalid/assets")
    client = MagicMock()
    uploaded = []
    client.upload_blob.side_effect = lambda name, data, overwrite: uploaded.append(
        data.read()
    )
    with patch("azure.identity.ManagedIdentityCredential"), patch(
        "azure.storage.blob.ContainerClient.from_container_url"
    ) as factory:
        factory.return_value.__enter__.return_value = client
        result = app.test_cli_runner().invoke(args=["backup-database"])
        assert result.exit_code == 0, result.output
    assert gzip.decompress(uploaded[0]).startswith(b'{"format": "donors-registry-1"')
    (tmp_path / "stamps").mkdir()
    (tmp_path / "signatures").mkdir()
    client.list_blobs.return_value = [MagicMock(), MagicMock()]
    for blob, name in zip(
        client.list_blobs.return_value, ["stamps/a.png", "signatures/b.png"]
    ):
        blob.name = name
    client.download_blob.return_value.readall.return_value = b"test-png"
    with patch("registry.assets.Path", return_value=tmp_path), patch(
        "registry.assets.ManagedIdentityCredential"
    ), patch("registry.assets.ContainerClient.from_container_url") as factory:
        factory.return_value.__enter__.return_value = client
        sync_assets()
        assert (tmp_path / "stamps/a.png").read_bytes() == b"test-png"
        client.list_blobs.return_value[0].name = "stamps/../../escape.png"
        with pytest.raises(ValueError, match="Assets must"):
            sync_assets()
        client.list_blobs.return_value = []
        with pytest.raises(ValueError, match="At least one"):
            sync_assets()


def test_managed_identity_refreshes_token_for_new_connections(monkeypatch):
    monkeypatch.delenv("SQL_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("AZURE_CLIENT_ID", "test-identity")
    engine = create_engine(
        "mssql+pyodbc://example.invalid/donors?driver=ODBC+Driver+18+for+SQL+Server"
    )
    with patch("azure.identity.ManagedIdentityCredential") as factory:
        factory.return_value.get_token.side_effect = [
            MagicMock(token="first"),
            MagicMock(token="second"),
        ]
        configure_sql_auth(engine)
        for expected in ["first", "second"]:
            args, kwargs = ["dsn;Trusted_Connection=Yes"], {}
            for listener in engine.dialect.dispatch.do_connect:
                listener(engine.dialect, None, args, kwargs)
            encoded = expected.encode("utf-16-le")
            assert (
                kwargs["attrs_before"][1256]
                == struct.pack("<I", len(encoded)) + encoded
            )
            assert "Trusted_Connection" not in args[0]
    engine.dispose()


def test_local_sql_auth_keeps_password_login(monkeypatch):
    monkeypatch.delenv("SQL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    engine = create_engine(
        "mssql+pyodbc://user:password@example.invalid/donors?driver=ODBC+Driver+18+for+SQL+Server"
    )
    configure_sql_auth(engine)
    assert not engine.dialect.dispatch.do_connect
    engine.dispose()


@pytest.mark.parametrize("matching_identity", [True, False])
def test_bootstrap_refuses_permissions_for_a_different_identity(
    monkeypatch, matching_identity
):
    principal = UUID("12345678-1234-1234-1234-123456789abc")
    monkeypatch.setattr("sys.argv", ["bootstrap_sql", str(principal)])
    with patch("registry.app.create_app"), patch("registry.extensions.db") as database:
        connection = (
            database.engine.connect.return_value.execution_options.return_value.__enter__.return_value
        )
        connection.exec_driver_sql.return_value.scalar.return_value = (
            principal.bytes_le if matching_identity else b"other-identity"
        )
        if matching_identity:
            runpy.run_module("registry.bootstrap_sql", run_name="__main__")
            assert connection.exec_driver_sql.call_args.args[0].startswith(
                "GRANT SELECT, INSERT, UPDATE, DELETE"
            )
        else:
            with pytest.raises(ValueError, match="different identity"):
                runpy.run_module("registry.bootstrap_sql", run_name="__main__")
            assert not any(
                call.args[0].startswith("GRANT")
                for call in connection.exec_driver_sql.call_args_list
            )


def test_failed_backup_is_never_uploaded(app, monkeypatch):
    with patch(
        "registry.transfer.export_database", side_effect=RuntimeError("snapshot failed")
    ), patch("azure.storage.blob.ContainerClient.from_container_url") as factory:
        result = app.test_cli_runner().invoke(args=["backup-database"])
        assert result.exit_code != 0
        factory.assert_not_called()


def test_asset_entrypoint_downloads_both_artwork_folders(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_CLIENT_ID", "test-identity")
    monkeypatch.setenv("ASSET_CONTAINER_URL", "https://example.invalid/assets")
    for folder in ["stamps", "signatures"]:
        (tmp_path / folder).mkdir()
    client = MagicMock()
    client.list_blobs.return_value = [MagicMock(), MagicMock()]
    for blob, name in zip(
        client.list_blobs.return_value, ["stamps/a.png", "signatures/b.png"]
    ):
        blob.name = name
    client.download_blob.return_value.readall.return_value = b"test-png"
    with patch("pathlib.Path", return_value=tmp_path), patch(
        "azure.identity.ManagedIdentityCredential"
    ), patch("azure.storage.blob.ContainerClient.from_container_url") as factory:
        factory.return_value.__enter__.return_value = client
        runpy.run_path("registry/assets.py", run_name="__main__")
    assert (tmp_path / "stamps/a.png").read_bytes() == b"test-png"
    assert (tmp_path / "signatures/b.png").read_bytes() == b"test-png"
