from pydantic import BaseModel


class UsageSummary(BaseModel):
    user_id: str
    total_tokens: int = 0
