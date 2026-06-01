from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import ApprovalRecord


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _store_dir() -> Path:
    override = str(os.getenv("PAOS_APPROVAL_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _repo_root() / "assistant" / "approval"


def _approvals_path() -> Path:
    return _store_dir() / "approvals.jsonl"


def _audit_path() -> Path:
    return _store_dir() / "audit-events.jsonl"


def _ensure_store() -> None:
    root = _store_dir()
    root.mkdir(parents=True, exist_ok=True)
    for path in (_approvals_path(), _audit_path()):
        if not path.exists():
            path.write_text("", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def append_approval(record: ApprovalRecord) -> None:
    _ensure_store()
    _append_jsonl(_approvals_path(), record.to_dict())


def append_audit_event(event: dict[str, Any]) -> None:
    _ensure_store()
    _append_jsonl(_audit_path(), event)


def get_approval(approval_id: str) -> ApprovalRecord | None:
    aid = str(approval_id or "").strip()
    if not aid:
        return None
    latest: ApprovalRecord | None = None
    for row in _read_jsonl(_approvals_path()):
        if str(row.get("approval_id") or "") == aid:
            latest = ApprovalRecord.from_dict(row)
    return latest


def list_approvals(status: str | None = None, limit: int = 20) -> list[ApprovalRecord]:
    latest_by_id: dict[str, ApprovalRecord] = {}
    for row in _read_jsonl(_approvals_path()):
        rec = ApprovalRecord.from_dict(row)
        if rec.approval_id:
            latest_by_id[rec.approval_id] = rec
    rows = list(latest_by_id.values())
    rows.sort(key=lambda x: x.created_at, reverse=True)
    if status:
        rows = [x for x in rows if x.status == status]
    return rows[: max(1, int(limit))]


def list_audit_events(approval_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    rows = _read_jsonl(_audit_path())
    if approval_id:
        aid = str(approval_id).strip()
        rows = [row for row in rows if str(row.get("approval_id") or "") == aid]
    rows.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return rows[: max(1, int(limit))]
