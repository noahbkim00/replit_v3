import sqlite3
from pathlib import Path


class ModelRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def list_allowed_model_ids(self) -> set[str]:
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute("SELECT model_id FROM model_allowlist").fetchall()

        return {row[0] for row in rows}

    def upsert_allowed_model(self, model_id: str) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO model_allowlist (model_id)
                VALUES (?)
                ON CONFLICT(model_id) DO NOTHING
                """,
                (model_id,),
            )
