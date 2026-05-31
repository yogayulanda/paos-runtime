from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MemoryHealth:
    provider: str
    healthy: bool
    warning: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryQuery:
    text: str = ""
    scope: str | None = None
    limit: int = 10


@dataclass(frozen=True)
class MemoryItem:
    id: str
    content: str
    scope: str | None
    created_at: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MemoryWrite:
    content: str
    scope: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryWriteResult:
    ok: bool
    item: MemoryItem | None
    path: str | None
    warning: str | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        if self.item is not None:
            payload["item"] = self.item.to_dict()
        return payload


class MemoryProvider(ABC):
    name: str

    @abstractmethod
    def healthcheck(self) -> MemoryHealth:
        raise NotImplementedError

    @abstractmethod
    def recall(self, query: MemoryQuery) -> list[MemoryItem]:
        raise NotImplementedError

    @abstractmethod
    def write(self, item: MemoryWrite) -> MemoryWriteResult:
        raise NotImplementedError
