import logging
import sqlite3

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect_database, initialize_database
from app.main import create_app


def test_healthz_returns_ok_and_logs_startup_without_secrets(tmp_path, caplog):
    settings = Settings(database_path=tmp_path / "proxy.sqlite3")
    app = create_app(settings)

    caplog.set_level(logging.INFO)
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    startup_records = [
        record for record in caplog.records if record.message == "proxy.startup"
    ]
    assert len(startup_records) == 1
    startup_record = startup_records[0]
    assert startup_record.app_name == "fastapi-ollama-proxy"
    assert startup_record.database_path == str(settings.database_path)
    assert startup_record.ollama_base_url == "http://localhost:11434/v1"
    assert startup_record.max_request_body_bytes == 8 * 1024 * 1024
    assert "dev-token" not in caplog.text
    assert "Authorization" not in caplog.text


def test_initialize_database_creates_sqlite_file_and_metadata_table(tmp_path):
    database_path = tmp_path / "nested" / "proxy.sqlite3"

    initialize_database(database_path)

    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        table_name = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()

    assert table_name == ("schema_migrations",)


def test_connect_database_creates_parent_and_sets_busy_timeout(tmp_path):
    database_path = tmp_path / "missing" / "proxy.sqlite3"

    with connect_database(database_path) as connection:
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()
        connection.execute("CREATE TABLE example (id INTEGER PRIMARY KEY)")

    assert database_path.exists()
    assert busy_timeout == (30000,)
