import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEV_TOKENS = {
    "user_a": "dev-token-user-a",
    "user_b": "dev-token-user-b",
    "admin": "dev-token-admin",
    "demo_standard": "dev-token-demo-standard",
    "demo_streaming": "dev-token-demo-streaming",
    "demo_usage_a": "dev-token-demo-usage-a",
    "demo_usage_b": "dev-token-demo-usage-b",
    "demo_limits": "dev-token-demo-limits",
    "demo_report": "dev-token-demo-report",
    "demo_concurrency_a": "dev-token-demo-concurrency-a",
    "demo_concurrency_b": "dev-token-demo-concurrency-b",
    "demo_load_open": "dev-token-demo-load-open",
    "demo_load_limited": "dev-token-demo-load-limited",
}

SEEDED_USERS = (
    ("user_a", "User A", "user", "User A dev token"),
    ("user_b", "User B", "user", "User B dev token"),
    ("admin", "Admin", "admin", "Admin dev token"),
    ("demo_standard", "Demo Standard", "user", "Standard demo token"),
    ("demo_streaming", "Demo Streaming", "user", "Streaming demo token"),
    ("demo_usage_a", "Demo Usage A", "user", "Usage demo A token"),
    ("demo_usage_b", "Demo Usage B", "user", "Usage demo B token"),
    ("demo_limits", "Demo Limits", "user", "Limits demo token"),
    ("demo_report", "Demo Report", "user", "Usage report demo token"),
    ("demo_concurrency_a", "Demo Concurrency A", "user", "Concurrency demo A token"),
    ("demo_concurrency_b", "Demo Concurrency B", "user", "Concurrency demo B token"),
    ("demo_load_open", "Demo Load Open", "user", "Load demo no-limit token"),
    ("demo_load_limited", "Demo Load Limited", "user", "Load demo limited token"),
)

ALLOWED_MODELS = ("llama3.2", "llama3.2:1b", "moondream")


def seed_dev_data(database_path: Path) -> None:
    from app.db import initialize_database
    from app.repositories.models import ModelRepository
    from app.repositories.users import UserRepository

    initialize_database(database_path)

    user_repository = UserRepository(database_path)
    for user_id, display_name, role, token_name in SEEDED_USERS:
        token = DEV_TOKENS[user_id]
        user_repository.upsert_user(user_id, display_name, role=role)
        user_repository.upsert_api_token(token, user_id, token, token_name)

    for user_id, _display_name, role, _token_name in SEEDED_USERS:
        if role != "admin":
            user_repository.upsert_admin_user_association("admin", user_id)

    model_repository = ModelRepository(database_path)
    for model_id in ALLOWED_MODELS:
        model_repository.upsert_allowed_model(model_id)


if __name__ == "__main__":
    database_path = Path(os.getenv("DATABASE_PATH", "data/proxy.sqlite3"))

    seed_dev_data(database_path)
    print(f"Seeded development data in {database_path}")
    print("User A token: dev-token-user-a")
    print("User B token: dev-token-user-b")
    print("Admin token: dev-token-admin")
    print("Demo tokens:")
    for user_id, _display_name, _role, _token_name in SEEDED_USERS:
        if user_id.startswith("demo_"):
            print(f"  {user_id}: {DEV_TOKENS[user_id]}")
