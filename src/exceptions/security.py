class BaseSecurityError(Exception):
    """Base class for all security errors."""

    def __init__(self, message: str = None) -> None:
        if message is None:
            message = "A security error has occurred."
        super().__init__(message)


class ExpiredTokenError(BaseSecurityError):
    """Raised when a token has expired."""

    def __init__(self, message: str = "The token has expired.") -> None:
        super().__init__(message)


class InvalidTokenError(BaseSecurityError):
    """Raised when a token is invalid."""

    def __init__(self, message: str = "Invalid token.") -> None:
        super().__init__(message)
