import json
import socket
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from .provider import MemoryHealth, MemoryItem, MemoryProvider, MemoryQuery, MemoryWrite, MemoryWriteResult


class MnemosyneMemoryProvider(MemoryProvider):
    name = "mnemosyne"

    def __init__(self, path: Path, endpoint: str | None, timeout_seconds: float = 2.0):
        self.path = Path(path)
        self.endpoint = (endpoint or "").strip() or None
        self.timeout_seconds = max(0.1, float(timeout_seconds))

    def _read_items(self) -> list[MemoryItem]:
        if not self.path.exists():
            return []

        items: list[MemoryItem] = []
        for line in self.path.read_text(encoding="utf-8", errors="ignore").splitlines():
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
                    source=str(payload.get("source") or self.name),
                    metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                )
            )

        return items

    def _endpoint_health(self) -> tuple[bool, str, dict]:
        if not self.endpoint:
            return (
                False,
                "Mnemosyne endpoint is not configured.",
                {"endpoint": None},
            )

        parsed = urlparse(self.endpoint)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host:
            return (
                False,
                "Mnemosyne endpoint is invalid (missing host).",
                {"endpoint": self.endpoint},
            )

        try:
            with socket.create_connection((host, port), timeout=self.timeout_seconds):
                pass
        except OSError as exc:
            return (
                False,
                "Mnemosyne endpoint is configured but unreachable.",
                {"endpoint": self.endpoint, "error": str(exc)},
            )

        return (
            True,
            "Mnemosyne endpoint is reachable; MVP adapter uses temporary JSONL bridge storage.",
            {"endpoint": self.endpoint, "bridge_path": str(self.path)},
        )

    def healthcheck(self) -> MemoryHealth:
        endpoint_ok, message, details = self._endpoint_health()
        if not endpoint_ok:
            return MemoryHealth(
                provider=self.name,
                healthy=False,
                warning=True,
                message=message,
                details=details,
            )

        parent = self.path.parent
        if self.path.exists() and not self.path.is_file():
            return MemoryHealth(
                provider=self.name,
                healthy=False,
                warning=False,
                message=f"Mnemosyne bridge path exists but is not a file: {self.path}",
                details={"path": str(self.path)},
            )
        if not parent.exists():
            return MemoryHealth(
                provider=self.name,
                healthy=False,
                warning=False,
                message=f"Mnemosyne bridge directory does not exist: {parent}",
                details={"path": str(self.path)},
            )

        try:
            _ = self._read_items()
        except OSError as exc:
            return MemoryHealth(
                provider=self.name,
                healthy=False,
                warning=False,
                message=f"Mnemosyne bridge file is not readable: {self.path}",
                details={"path": str(self.path), "error": str(exc)},
            )

        return MemoryHealth(
            provider=self.name,
            healthy=True,
            warning=True,
            message=message,
            details=details,
        )

    def recall(self, query: MemoryQuery) -> list[MemoryItem]:
        try:
            items = self._read_items()
        except OSError:
            return []

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
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            created_at = datetime.now().astimezone().isoformat()
            memory_item = MemoryItem(
                id=uuid4().hex,
                content=item.content,
                scope=item.scope,
                created_at=created_at,
                source=self.name,
                metadata=item.metadata,
            )
            payload = memory_item.to_dict()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        except OSError as exc:
            return MemoryWriteResult(
                ok=False,
                item=None,
                path=str(self.path),
                warning=f"Mnemosyne write failed: {exc}",
            )

        return MemoryWriteResult(
            ok=True,
            item=memory_item,
            path=str(self.path),
            warning="Mnemosyne MVP adapter wrote via temporary JSONL bridge storage.",
        )
