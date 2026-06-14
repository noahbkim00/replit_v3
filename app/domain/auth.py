from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class User:
    user_id: str
