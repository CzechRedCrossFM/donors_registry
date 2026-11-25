"""Database differences that cannot be expressed using portable SQLAlchemy SQL."""

from sqlalchemy import collate
from sqlalchemy.dialects.mssql import DATETIME2

# DATETIME2 preserves microseconds when importing existing donation history.
timestamp_type = DATETIME2(precision=6)


def czech_order(column):
    return collate(column, "Czech_100_CI_AS")


def configure_sql_auth(engine):
    """Get fresh Azure tokens for new connections; local SQL uses password authentication."""
    import os
    import struct

    from sqlalchemy import event

    admin_token = os.environ.get("SQL_ACCESS_TOKEN")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    if not admin_token and not client_id:
        return
    credential = None
    if not admin_token:
        from azure.identity import ManagedIdentityCredential

        credential = ManagedIdentityCredential(client_id=client_id)

    @event.listens_for(engine, "do_connect")
    def provide_token(dialect, connection_record, args, kwargs):
        token = (
            admin_token
            or credential.get_token("https://database.windows.net/.default").token
        )
        encoded = token.encode("utf-16-le")
        args[0] = args[0].replace(";Trusted_Connection=Yes", "")
        kwargs["attrs_before"] = {1256: struct.pack("<I", len(encoded)) + encoded}
