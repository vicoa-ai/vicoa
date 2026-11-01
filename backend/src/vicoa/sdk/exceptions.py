"""Exception classes for the Vicoa SDK."""


class VicoaError(Exception):
    """Base exception for all Vicoa SDK errors."""

    pass


class AuthenticationError(VicoaError):
    """Raised when authentication fails."""

    pass


class MachineLimitReached(VicoaError):
    """Raised when the account's plan has no room for another machine.

    Distinct from `AuthenticationError`: the credential is perfectly good, so
    the daemon must not stamp it dead — it simply has nowhere to register. Like
    `AuthenticationError`, it is NOT a `requests.RequestException`, so it escapes
    the broad retry handlers instead of being swallowed and retried forever
    against a wall that will not move without a purchase.
    """

    def __init__(self, detail: str, upgrade_url: str = "") -> None:
        self.detail = detail
        #: Where the server says to upgrade; "" when it named none.
        self.upgrade_url = upgrade_url
        super().__init__(detail)


class TimeoutError(VicoaError):
    """Raised when an operation times out."""

    pass


class APIError(VicoaError):
    """Raised when the API returns an error response."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API Error {status_code}: {detail}")
