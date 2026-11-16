"""Decorator that turns an investigator graph node into a span (bridge for the node timings)."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from veedor.infrastructure.telemetry.runtime import span

F = TypeVar("F", bound=Callable[..., Any])


def traced_node(name: str) -> Callable[[F], F]:
    """Wrap a node function in a span named ``node <name>``; behaviour is unchanged when off.

    Usage: ``graph.add_node("assess_signals", traced_node("assess_signals")(fn))``, or apply it
    inside the existing ``_timed`` wrapper around ``fn(state)``.
    """

    def decorate(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(f"node {name}", node=name):
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorate
