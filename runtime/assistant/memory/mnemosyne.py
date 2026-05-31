import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .provider import MemoryHealth, MemoryItem, MemoryProvider, MemoryQuery, MemoryWrite, MemoryWriteResult


class MnemosyneMemoryProvider(MemoryProvider):
    name = "mnemosyne"

    def __init__(
        self,
        path: Path,
        *,
        data_dir: Path,
        adapter_mode: str = "sdk",
        bank: str = "paos",
        session_id: str = "paos-assistant",
        author_id: str | None = None,
        author_type: str | None = None,
        channel_id: str | None = None,
        strict_healthcheck: bool = False,
        endpoint: str | None = None,
        timeout_seconds: float = 2.0,
    ):
        # Keep path/endpoint compatibility fields for diagnostics continuity.
        self.path = Path(path)
        self.endpoint = (endpoint or "").strip() or None
        self.timeout_seconds = max(0.1, float(timeout_seconds))

        self.adapter_mode = (adapter_mode or "sdk").strip().lower() or "sdk"
        self.data_dir = Path(data_dir)
        self.bank = (bank or "paos").strip() or "paos"
        self.session_id = (session_id or "paos-assistant").strip() or "paos-assistant"
        self.author_id = (author_id or "").strip() or None
        self.author_type = (author_type or "").strip() or None
        self.channel_id = (channel_id or "").strip() or None
        self.strict_healthcheck = bool(strict_healthcheck)

    def _base_details(self) -> dict[str, Any]:
        return {
            "adapter_mode": self.adapter_mode,
            "data_dir": str(self.data_dir),
            "bank": self.bank,
            "session_id": self.session_id,
            "strict_healthcheck": self.strict_healthcheck,
        }

    def _build_client(self):
        if self.adapter_mode != "sdk":
            raise RuntimeError(
                f"Unsupported mnemosyne adapter_mode: {self.adapter_mode} (only 'sdk' is supported)"
            )

        os.environ["MNEMOSYNE_DATA_DIR"] = str(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        from mnemosyne import Mnemosyne

        kwargs: dict[str, Any] = {
            "bank": self.bank,
            "session_id": self.session_id,
        }
        if self.author_id:
            kwargs["author_id"] = self.author_id
        if self.author_type:
            kwargs["author_type"] = self.author_type
        if self.channel_id:
            kwargs["channel_id"] = self.channel_id

        return Mnemosyne(**kwargs)

    def _version(self) -> str | None:
        try:
            import importlib.metadata as md

            return md.version("mnemosyne-memory")
        except Exception:
            return None

    def _normalize_recall_item(self, payload: Any) -> MemoryItem | None:
        data = payload if isinstance(payload, dict) else {}
        content = str(data.get("content") or "").strip()
        if not content:
            return None

        raw_metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        metadata = dict(raw_metadata)
        for key in ("score", "keyword_score", "dense_score", "fts_score", "importance"):
            if key in data and data.get(key) is not None:
                metadata[key] = data.get(key)

        source = str(data.get("source") or self.name)
        scope = raw_metadata.get("scope") if isinstance(raw_metadata.get("scope"), str) else data.get("scope")
        created_at = str(data.get("timestamp") or data.get("created_at") or "")
        item_id = str(data.get("id") or "")

        if not created_at:
            created_at = datetime.now().astimezone().isoformat()
        if not item_id:
            item_id = f"mnemosyne-{abs(hash(content))}"

        return MemoryItem(
            id=item_id,
            content=content,
            scope=scope if isinstance(scope, str) or scope is None else str(scope),
            created_at=created_at,
            source=source,
            metadata=metadata,
        )

    def healthcheck(self) -> MemoryHealth:
        details = self._base_details()

        version = self._version()
        details["version"] = version
        if version is None:
            return MemoryHealth(
                provider=self.name,
                healthy=False,
                warning=False,
                message="mnemosyne-memory package is not installed.",
                details=details,
            )

        try:
            client = self._build_client()
        except Exception as exc:
            details["error"] = str(exc)
            return MemoryHealth(
                provider=self.name,
                healthy=False,
                warning=False,
                message="Mnemosyne SDK initialization failed.",
                details=details,
            )

        if not self.strict_healthcheck:
            return MemoryHealth(
                provider=self.name,
                healthy=True,
                warning=False,
                message="Mnemosyne SDK client initialized.",
                details=details,
            )

        probe_token = datetime.now().astimezone().isoformat()
        probe_text = f"paos-healthcheck-probe {probe_token}"
        try:
            _ = client.remember(
                probe_text,
                source="paos-healthcheck",
                importance=0.01,
                metadata={"provider": self.name, "probe": True},
                scope="session",
            )
            recalled = client.recall("paos-healthcheck-probe", top_k=1)
            details["strict_probe_recall_count"] = len(recalled) if isinstance(recalled, list) else 0
        except Exception as exc:
            details["error"] = str(exc)
            return MemoryHealth(
                provider=self.name,
                healthy=False,
                warning=False,
                message="Mnemosyne strict healthcheck probe failed.",
                details=details,
            )

        return MemoryHealth(
            provider=self.name,
            healthy=True,
            warning=True,
            message="Mnemosyne strict healthcheck probe succeeded.",
            details=details,
        )

    def recall(self, query: MemoryQuery) -> list[MemoryItem]:
        try:
            client = self._build_client()
            rows = client.recall(str(query.text or ""), top_k=max(0, int(query.limit)))
        except Exception:
            return []

        if not isinstance(rows, list):
            return []

        if not rows and str(query.text or "").strip():
            try:
                rows = client.recall("", top_k=max(1, int(query.limit) * 3))
            except Exception:
                rows = []

        needle = str(query.text or "").strip().lower()
        items: list[MemoryItem] = []
        for row in rows:
            item = self._normalize_recall_item(row)
            if item is None:
                continue
            if query.scope:
                scope_value = str(query.scope)
                if scope_value in {"session", "global"}:
                    if item.scope != scope_value:
                        continue
                else:
                    item_scope = item.metadata.get("scope")
                    if item_scope is not None and item_scope != scope_value:
                        continue
            if needle and needle not in item.content.lower():
                continue
            items.append(item)

        return items[: max(0, int(query.limit))]

    def write(self, item: MemoryWrite) -> MemoryWriteResult:
        try:
            client = self._build_client()
            metadata = dict(item.metadata or {})
            metadata.setdefault("provider", self.name)
            if item.scope:
                metadata.setdefault("scope", item.scope)

            scope_value = item.scope if item.scope in {"session", "global"} else "session"
            memory_id = client.remember(
                item.content,
                source=str(metadata.get("source") or "paos"),
                importance=float(metadata.get("importance") or 0.5),
                metadata=metadata,
                scope=scope_value,
            )

            memory_item = MemoryItem(
                id=str(memory_id or ""),
                content=item.content,
                scope=item.scope,
                created_at=datetime.now().astimezone().isoformat(),
                source=self.name,
                metadata=metadata,
            )
            return MemoryWriteResult(
                ok=True,
                item=memory_item,
                path=str(self.data_dir / "mnemosyne.db"),
                warning=None,
            )
        except Exception as exc:
            return MemoryWriteResult(
                ok=False,
                item=None,
                path=str(self.data_dir / "mnemosyne.db"),
                warning=f"Mnemosyne SDK write failed: {exc}",
            )
