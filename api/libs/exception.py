from collections.abc import Iterator, Mapping
from typing import Any

from werkzeug.exceptions import HTTPException


def iter_error_causes(error: BaseException) -> Iterator[BaseException]:
    """Yield an exception and its explicit causes once, in order, stopping before any cycle.

    Implicit contexts are excluded; traversal neither mutates exceptions nor follows a cause twice.
    """
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__


class BaseHTTPException(HTTPException):
    error_code: str = "unknown"
    data: dict[str, Any] | None = None

    def __init__(self, description=None, response=None):
        super().__init__(description, response)

        self.data = {
            "code": self.error_code,
            "message": self.description,
            "status": self.code,
        }


class RelayedHTTPError(BaseHTTPException):
    """An error whose ``code`` and status are relayed from a downstream service at runtime.

    Emits the standard error body, but its codes cannot be listed per class. Declaring it
    with ``error_responses`` keeps the operation's error codes and statuses open.
    """

    def __init__(self, *, status: int, error_code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        self.code = status
        self.error_code = error_code
        super().__init__(description=message)
        if details:
            assert self.data is not None
            self.data["details"] = dict(details)
