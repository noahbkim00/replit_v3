import sqlite3

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import initialize_database
from app.main import create_app


def test_healthz_returns_ok(tmp_path):
    settings = Settings(database_path=tmp_path / "proxy.sqlite3")
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_initialize_database_creates_sqlite_file_and_metadata_table(tmp_path):
    database_path = tmp_path / "nested" / "proxy.sqlite3"

    initialize_database(database_path)

    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        table_name = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()

    assert table_name == ("schema_migrations",)
