class AppException(Exception):
    """Raised for HTTP-level errors with a specific status code and error code."""

    def __init__(self, status_code: int, error: str, detail: str | None = None) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.error = error
        self.detail = detail


class IngestionError(Exception):
    """Raised when an ingestion step fails unrecoverably."""

    def __init__(self, message: str, step: str = "") -> None:
        super().__init__(message)
        self.step = step


class RetrievalError(Exception):
    """Raised when a retrieval step fails unrecoverably."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
