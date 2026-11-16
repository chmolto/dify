"""Explicit error chains have stable order and terminate even when exceptions form cycles."""

import pytest

from libs.exception import iter_error_causes


@pytest.mark.parametrize("cycle", [None, 0, 1])
def test_error_causes_preserve_order_and_stop_before_revisiting(cycle: int | None) -> None:
    errors = [RuntimeError("outer"), ValueError("middle"), TypeError("inner")]
    errors[0].__cause__ = errors[1]
    errors[1].__cause__ = errors[2]
    if cycle is not None:
        errors[2].__cause__ = errors[cycle]

    assert list(iter_error_causes(errors[0])) == errors


def test_error_causes_exclude_implicit_context_and_handle_self_causes() -> None:
    error = ValueError("outer")
    error.__context__ = RuntimeError("implicit")
    error.__cause__ = error

    assert list(iter_error_causes(error)) == [error]
