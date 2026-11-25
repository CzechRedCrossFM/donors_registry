"""Application migration history for SQL Server."""

from alembic import context
from flask import current_app

config = context.config
database = current_app.extensions["migrate"].db

if context.is_offline_mode():
    context.configure(
        url=database.engine.url, target_metadata=database.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with database.engine.connect() as connection:
        context.configure(connection=connection, target_metadata=database.metadata)
        with context.begin_transaction():
            context.run_migrations()
