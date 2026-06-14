class ProxyError(Exception):
    """Base exception for proxy-specific failures rendered by the API layer."""

    status_code = 500
    error_type = "proxy_error"
    code = "proxy_error"
    default_message = "Proxy request failed"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class UpstreamError(ProxyError):
    error_type = "upstream_error"
    code = "upstream_error"
    default_message = "Upstream request failed"


class UpstreamUnavailableError(UpstreamError):
    status_code = 502
    code = "ollama_unavailable"
    default_message = "Ollama is unavailable"


class UpstreamTimeoutError(UpstreamError):
    status_code = 504
    code = "ollama_timeout"
    default_message = "Ollama request timed out"
