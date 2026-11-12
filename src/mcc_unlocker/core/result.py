"""Typed Ok/Err result used by the whole application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Mapping, TypeVar, Union

from .errors import ERRORS, ErrorCode, ErrorSpec

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    @property
    def is_ok(self) -> bool:
        return True

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value


@dataclass(frozen=True, slots=True)
class Err:
    code: ErrorCode
    message: str = ""
    retryable: bool | None = None
    rollback_required: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        spec = ERRORS.get(self.code)
        if spec is not None:
            if self.retryable is None:
                object.__setattr__(self, "retryable", spec.retryable)
            if not self.message:
                object.__setattr__(self, "message", spec.user_message)
        elif self.retryable is None:
            object.__setattr__(self, "retryable", False)

    @property
    def is_ok(self) -> bool:
        return False

    def unwrap(self) -> Any:
        raise ValueError(f"cannot unwrap Err({self.code.value}): {self.message}")

    def unwrap_or(self, default: U) -> U:
        return default

    @property
    def spec(self) -> ErrorSpec | None:
        return ERRORS.get(self.code)

    def to_dict(self) -> dict[str, Any]:
        spec = self.spec
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": bool(self.retryable),
            "rollback_required": self.rollback_required,
            "details": dict(self.details),
            "likely_cause": spec.likely_cause if spec else "",
            "device_state": spec.device_state if spec else "unknown",
            "allowed_actions": list(spec.allowed_actions) if spec else [],
            "restore_preconditions": list(spec.restore_preconditions) if spec else [],
        }


Result = Union[Ok[T], Err]
