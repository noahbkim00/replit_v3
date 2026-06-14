from pydantic import BaseModel


class ErrorDetail(BaseModel):
    message: str
    type: str = "proxy_error"
    code: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
