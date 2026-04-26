"""Result[T, E] for expected business outcomes (Q17 C).

Pattern: services return Result; route handlers map Err variants to
RFC 7807 problem+json (Q17 i)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, NoReturn, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_err(self) -> NoReturn:
        raise RuntimeError("Called unwrap_err on Ok")


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> NoReturn:
        raise RuntimeError(f"Called unwrap on Err: {self.error!r}")

    def unwrap_err(self) -> E:
        return self.error


# Convenience alias: Result[T, E] = Ok[T] | Err[E]
Result = Union[Ok[T], Err[E]]
