import sqlite3
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class User:
    id: str
    display_name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def hash_api_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


class UserRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def get_user_by_api_token(self, token: str) -> User | None:
        token_hash = hash_api_token(token)
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT users.id, users.display_name, users.role
                FROM api_tokens
                JOIN users ON users.id = api_tokens.user_id
                WHERE api_tokens.token_hash = ?
                  AND api_tokens.is_active = 1
                  AND users.is_active = 1
                """,
                (token_hash,),
            ).fetchone()

        if row is None:
            return None

        return User(id=row[0], display_name=row[1], role=row[2])

    def upsert_user(
        self, user_id: str, display_name: str, role: str = "user"
    ) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO users (id, display_name, role, is_active)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    display_name = excluded.display_name,
                    role = excluded.role,
                    is_active = 1
                """,
                (user_id, display_name, role),
            )

    def upsert_api_token(self, token_id: str, user_id: str, token: str, name: str) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO api_tokens (id, user_id, token_hash, name, is_active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    user_id = excluded.user_id,
                    token_hash = excluded.token_hash,
                    name = excluded.name,
                    is_active = 1
                """,
                (token_id, user_id, hash_api_token(token), name),
            )
