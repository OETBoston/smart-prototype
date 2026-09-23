"""Exercise commit and rollback across related export tables using SQLite."""

import sqlite3

import pandas as pd
import pytest
from api_updater import exporter


@pytest.mark.parametrize("fail", [False, True])
def test_export_is_one_transaction(monkeypatch, fail) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE changes (name TEXT PRIMARY KEY)")
    contexts = []

    class Database:
        def __init__(self, **kwargs: object) -> None:
            contexts.append(kwargs)

        def __enter__(self) -> "Database":
            connection.__enter__()
            return self

        def __exit__(self, *args: object) -> bool:
            return connection.__exit__(*args)

        def update_or_append(self, table, frame, keys) -> None:
            connection.execute("INSERT INTO changes VALUES (?)", (table,))

        def append_data(self, table, frame) -> None:
            connection.execute("INSERT INTO changes VALUES (?)", (table,))
            if fail:
                raise RuntimeError("relationship write failed")

        def delete(self, table, frame, keys) -> None:
            connection.execute("INSERT INTO changes VALUES ('delete')")

    monkeypatch.setattr(exporter, "SmartCurbDB", Database)
    data = {
        name: {"table": pd.DataFrame({"id": [1]}), "keys": ["id"]}
        for name in (
            "curb_zones",
            "curb_policies",
            "curb_zone_policies_delete",
            "curb_zone_policies",
        )
    }
    if fail:
        with pytest.raises(RuntimeError, match="relationship write failed"):
            exporter.export_to_db("cds", data, "chinatown_cds")
        assert connection.execute("SELECT count(*) FROM changes").fetchone()[0] == 0
    else:
        exporter.export_to_db("cds", data, "chinatown_cds")
        assert connection.execute("SELECT count(*) FROM changes").fetchone()[0] == 4
    assert contexts == [{"dbname": "cds", "schema": "chinatown_cds"}]
    connection.close()
