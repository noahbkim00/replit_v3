import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEV_TOKENS = {
    "user_a": "dev-token-user-a",
    "user_b": "dev-token-user-b",
}

ALLOWED_MODELS = ("llama3.2", "llama3.2:1b", "moondream")


def seed_dev_data(database_path: Path) -> None:
    from app.db import initialize_database
    from app.repositories.models import ModelRepository
    from app.repositories.users import UserRepository

    initialize_database(database_path)

    user_repository = UserRepository(database_path)
    user_repository.upsert_user("user_a", "User A")
    user_repository.upsert_user("user_b", "User B")
    user_repository.upsert_api_token(
        "dev-token-user-a", "user_a", DEV_TOKENS["user_a"], "User A dev token"
    )
    user_repository.upsert_api_token(
        "dev-token-user-b", "user_b", DEV_TOKENS["user_b"], "User B dev token"
    )

    model_repository = ModelRepository(database_path)
    for model_id in ALLOWED_MODELS:
        model_repository.upsert_allowed_model(model_id)


if __name__ == "__main__":
    database_path = Path(os.getenv("DATABASE_PATH", "data/proxy.sqlite3"))

    seed_dev_data(database_path)
    print(f"Seeded development data in {database_path}")
    print("User A token: dev-token-user-a")
    print("User B token: dev-token-user-b")
