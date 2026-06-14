class UpstreamServiceError(Exception):
    """Raised when Ollama cannot return a usable response."""


class ClientRequestError(Exception):
    """Raised when a client request is invalid for this proxy."""

    def __init__(
        self, message: str, status_code: int = 400, error_type: str = "invalid_request_error"
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
