from pydantic import BaseModel


class AdminStatus(BaseModel):
    status: str
