"""Reference lists for a fresh installation; imported lists are left unchanged."""

import json
from pathlib import Path

from sqlalchemy import select

from registry.extensions import db


def seed_reference_data():
    data = json.loads(Path(__file__).with_name("reference.json").read_text())
    with db.engine.begin() as connection:
        for name, rows in data.items():
            table = db.metadata.tables[name]
            if not connection.execute(select(table)).first():
                connection.execute(table.insert(), rows)
