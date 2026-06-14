from pydantic import BaseModel


class LimitConfig(BaseModel):
    limit_type: str
    value: int
