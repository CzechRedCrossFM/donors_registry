"""Initial SQL Server schema, for the donor registry."""

from pathlib import Path

from alembic import op

revision = "mssql_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = Path(__file__).with_name("0001_schema.sql").read_text()
    for statement in sql.split("\nGO\n"):
        op.execute(statement)


def downgrade():
    for name in [
        "records",
        "contact_import_logs",
        "batches",
        "awarded_medals",
        "award_eligibility_snapshots",
        "users",
        "notes",
        "medals",
        "ignored_donors",
        "donors_overview",
        "donors_override",
        "donation_centers",
    ]:
        op.drop_table(name)
