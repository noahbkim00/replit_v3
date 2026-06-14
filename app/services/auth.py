from app.repositories.users import User, UserRepository


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    def authenticate(self, token: str) -> User | None:
        return self._user_repository.get_user_by_api_token(token)
