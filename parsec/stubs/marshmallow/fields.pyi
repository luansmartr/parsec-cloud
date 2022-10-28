# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPL-3.0 2016-present Scille SAS
from __future__ import annotations
from typing import Any, Generic, TypeVar, Callable

missing_: object = object()

T = TypeVar("T")

class Field(Generic[T]):
    default: object

    def __init__(
        self,
        default: object = missing_,
        attribute: str | None = None,
        load_from: str | None = None,
        dump_to: str | None = None,
        error: str | None = None,
        validate: Callable[[Any], bool] | None = None,
        required: bool = False,
        allow_none: bool | None = None,
        load_only: bool = False,
        dump_only: bool = False,
        missing: object = missing_,
        error_messages: dict[str, object] | None = None,
        **metadata: Any,
    ): ...
    def serialize(
        self, attr: str, obj: object, accessor: Callable[..., object] | None = None
    ) -> Any: ...
    def deserialize(self, value: object, attr: str | None = None, data: Any = None) -> T: ...
    def _serialize(self, value: T | None, attr: str, obj: object) -> Any: ...
    def _deserialize(self, value: object, attr: str, obj: dict[str, object]) -> T: ...
    def __deepcopy__(self, memo: Any): ...
    def fail(self, key: str, **kwargs: Any) -> None: ...

class Int(Field): ...
class Float(Field): ...
class String(Field): ...
class List(Field): ...
class Dict(Field): ...
class Nested(Field): ...
class Integer(Field): ...
class Boolean(Field): ...
class Email(Field): ...
