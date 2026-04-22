"""Request-scoped context helpers."""

from contextvars import ContextVar, Token

_request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Returns the current request id if the code runs inside an HTTP request."""
    return _request_id_context.get()


def set_request_id(request_id: str) -> Token:
    """Stores the request id in a context variable for the current task."""
    return _request_id_context.set(request_id)


def reset_request_id(token: Token) -> None:
    """Restores the previous request id context."""
    _request_id_context.reset(token)
