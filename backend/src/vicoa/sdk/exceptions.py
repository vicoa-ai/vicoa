"""Exception classes for the Vicoa SDK."""


class VicoaError(Exception):
    """Base exception for all Vicoa SDK errors."""

    pass


class AuthenticationError(VicoaError):
    """Raised when authentication fails."""

    pass


class TimeoutError(VicoaError):
    """Raised when an operation times out."""

    pass


class APIError(VicoaError):
    """Raised when the API returns an error response."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API Error {status_code}: {detail}")
