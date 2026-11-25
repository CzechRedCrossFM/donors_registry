"""Run once as the Entra SQL administrator, before migrations and cutover."""

import sys
from uuid import UUID

from registry.app import create_app
from registry.extensions import db

if __name__ == "__main__":
    principal_id = UUID(sys.argv[1])
    with create_app().app_context():
        with db.engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            conn.exec_driver_sql(
                "ALTER DATABASE CURRENT SET ALLOW_SNAPSHOT_ISOLATION ON"
            )
            conn.exec_driver_sql(
                "IF DATABASE_PRINCIPAL_ID('donors-runtime') IS NULL "
                f"CREATE USER [donors-runtime] WITH SID = 0x{principal_id.bytes_le.hex()}, TYPE = E"
            )
            existing = conn.exec_driver_sql(
                "SELECT sid FROM sys.database_principals WHERE name = 'donors-runtime'"
            ).scalar()
            if existing != principal_id.bytes_le:
                raise ValueError("Existing SQL user belongs to a different identity")
            conn.exec_driver_sql(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO [donors-runtime]"
            )
    print("Snapshot isolation and runtime permissions configured.")
