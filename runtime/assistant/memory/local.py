import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .provider import MemoryHealth, MemoryItem, MemoryProvider, MemoryQuery, MemoryWrite, MemoryWriteResult


class LocalMemoryProvider(MemoryProvider):
    name = "local"

    def __init__(self, path: Path):
        self.path = Path(path)

    def _read_items(self) -> list[MemoryItem]:
        if not self.path.exists():
            return []

        items: list[MemoryItem] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(payload, dict):
                continue

            items.append(
                MemoryItem(
                    id=str(payload.get("id") or ""),
                    content=str(payload.get("content") or ""),
                    scope=payload.get("scope"),
                    created_at=str(payload.get("created_at") or ""),
                    source=str(payload.get("source") or "local"),
                    metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                )
            )

        return items

    def healthcheck(self) -> MemoryHealth:
        if self.path.exists():
            if not self.path.is_file():
                return MemoryHealth(
                    provider=self.name,
                    healthy=False,
                    warning=False,
                    message=f"Local memory path exists but is not a file: {self.path}",
                    details={"path": str(self.path)},
                )
            try:
                self._read_items()
            except OSError as exc:
                return MemoryHealth(
                    provider=self.name,
                    healthy=False,
                    warning=False,
                    message=f"Local memory file is not readable: {self.path}",
                    details={"path": str(self.path), "error": str(exc)},
                )
            return MemoryHealth(
                provider=self.name,
                healthy=True,
                warning=False,
                message=f"Local memory file is readable: {self.path}",
                details={"path": str(self.path)},
            )

        parent = self.path.parent
        if not parent.exists():
            return MemoryHealth(
                provider=self.name,
                healthy=False,
                warning=False,
                message=f"Local memory directory does not exist: {parent}",
                details={"path": str(self.path)},
            )

        return MemoryHealth(
            provider=self.name,
            healthy=True,
            warning=False,
            message=f"Local memory file is ready: {self.path}",
            details={"path": str(self.path)},
        )

    def recall(self, query: MemoryQuery) -> list[MemoryItem]:
        items = self._read_items()
        items = [item for item in items if not query.scope or item.scope == query.scope]
        if query.limit <= 0:
            return []

        items.reverse()
        if not query.text.strip():
            return items[: query.limit]

        needle = query.text.strip().lower()
        matched = [item for item in items if needle in item.content.lower()]
        return matched[: query.limit]

    def write(self, item: MemoryWrite) -> MemoryWriteResult:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now().astimezone().isoformat()
        memory_item = MemoryItem(
            id=uuid4().hex,
            content=item.content,
            scope=item.scope,
            created_at=created_at,
            source="local",
            metadata=item.metadata,
        )
        payload = memory_item.to_dict()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        return MemoryWriteResult(ok=True, item=memory_item, path=str(self.path), warning=None)
