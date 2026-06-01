from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from assistant.config import load_assistant_config

from .factory import load_memory_provider
from .provider import MemoryItem, MemoryQuery, MemoryWrite
from .taxonomy import normalize_memory_type, normalize_source_type, normalize_status

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DIR = ROOT / "runtime" / "assistant" / "memory" / "runtime"
CANDIDATES_PATH = RUNTIME_DIR / "candidates.jsonl"


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    type: str
    content: str
    source_type: str
    source_ref: str
    evidence_summary: str
    confidence: float
    status: str
    topic_key: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "type": self.type,
            "content": self.content,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "evidence_summary": self.evidence_summary,
            "confidence": self.confidence,
            "status": self.status,
            "topic_key": self.topic_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class MemoryHealthReport:
    ok: bool
    summary: str
    provider: str
    active_count: int
    candidate_count: int
    rejected_count: int
    warnings: list[str]


_STOPWORDS = {
    "yang", "dan", "untuk", "dengan", "adalah", "the", "a", "di", "ke", "dari", "ini", "itu", "saya", "aku",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _topic_key(memory_type: str, content: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", content.lower())
    tokens = [tok for tok in normalized.split() if tok and tok not in {"yang", "dan", "untuk", "dengan", "adalah", "the", "a"}]
    return f"{memory_type}:" + " ".join(tokens[:8]).strip()


def _compact(text: str, max_chars: int = 240) -> str:
    clean = re.sub(r"\s+", " ", str(text or "").strip())
    return clean[:max_chars]


def _terms(text: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
    return [tok for tok in normalized.split() if tok and tok not in _STOPWORDS]


def _recency_score(iso_value: str) -> float:
    try:
        dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
    except Exception:
        return 0.0
    age_hours = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
    if age_hours <= 24:
        return 0.25
    if age_hours <= 24 * 7:
        return 0.15
    if age_hours <= 24 * 30:
        return 0.08
    return 0.03


def _type_priority(memory_type: str) -> float:
    ranking = {
        "decision": 0.35,
        "task_state": 0.28,
        "project_fact": 0.24,
        "working_style": 0.20,
        "preference": 0.18,
        "note": 0.10,
    }
    return ranking.get(normalize_memory_type(memory_type), 0.05)


def _query_relevance_score(query: str, payload: dict[str, Any]) -> tuple[float, str]:
    query_terms = set(_terms(query))
    content = str(payload.get("content") or "")
    content_terms = set(_terms(content))
    overlap = query_terms.intersection(content_terms) if query_terms else set()

    overlap_score = 0.0
    if query_terms:
        overlap_score = min(0.60, (len(overlap) / max(1, len(query_terms))) * 0.60)

    base = _type_priority(str(payload.get("type") or "note"))
    confidence = float(payload.get("confidence") or 0.0) * 0.10
    recency = _recency_score(str(payload.get("updated_at") or payload.get("created_at") or ""))
    total = round(base + confidence + recency + overlap_score, 4)

    if not query_terms:
        reason = "recent active memory"
    elif overlap:
        reason = "matched query terms: " + ", ".join(sorted(list(overlap))[:3])
    else:
        reason = "semantically related memory type"
    return total, reason


def _normalize_confidence(value: float | int | str | None) -> float:
    try:
        parsed = float(value if value is not None else 0.7)
    except Exception:
        parsed = 0.7
    return max(0.0, min(1.0, parsed))


def _candidate_from_payload(payload: dict[str, Any]) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=str(payload.get("candidate_id") or ""),
        type=normalize_memory_type(payload.get("type")),
        content=_compact(str(payload.get("content") or ""), 8000),
        source_type=normalize_source_type(payload.get("source_type")),
        source_ref=_compact(str(payload.get("source_ref") or ""), 280),
        evidence_summary=_compact(str(payload.get("evidence_summary") or ""), 400),
        confidence=_normalize_confidence(payload.get("confidence")),
        status=normalize_status(payload.get("status")),
        topic_key=_compact(str(payload.get("topic_key") or ""), 220),
        created_at=str(payload.get("created_at") or _now_iso()),
        updated_at=str(payload.get("updated_at") or _now_iso()),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )


def _read_candidates() -> list[CandidateRecord]:
    if not CANDIDATES_PATH.exists():
        return []
    rows: list[CandidateRecord] = []
    for line in CANDIDATES_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        item = _candidate_from_payload(payload)
        if item.candidate_id:
            rows.append(item)
    return rows


def _write_candidates(rows: list[CandidateRecord]) -> None:
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATES_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_dict(), ensure_ascii=True) + "\n")


def _active_memories(limit: int = 200) -> list[MemoryItem]:
    selection = load_memory_provider()
    return selection.provider.recall(MemoryQuery(text="", scope=None, limit=max(1, int(limit))))


def _memory_payload(item: MemoryItem) -> dict[str, Any]:
    md = item.metadata if isinstance(item.metadata, dict) else {}
    return {
        "id": item.id,
        "type": normalize_memory_type(md.get("type")),
        "content": item.content,
        "status": normalize_status(md.get("status") or "active"),
        "source_type": normalize_source_type(md.get("source_type")),
        "source_ref": str(md.get("source_ref") or ""),
        "evidence_summary": str(md.get("evidence_summary") or ""),
        "confidence": _normalize_confidence(md.get("confidence")),
        "topic_key": str(md.get("topic_key") or _topic_key(normalize_memory_type(md.get("type")), item.content)),
        "created_at": item.created_at,
        "updated_at": str(md.get("updated_at") or item.created_at),
        "scope": item.scope,
    }


def _has_required_provenance(source_type: str, source_ref: str, evidence_summary: str) -> bool:
    return bool(source_type.strip() and source_ref.strip() and evidence_summary.strip())


def create_candidate(
    content: str,
    *,
    memory_type: str | None,
    source_type: str | None,
    source_ref: str | None,
    evidence_summary: str | None,
    confidence: float | int | str | None = None,
    status: str = "candidate",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = _compact(content, 8000)
    if not body:
        return {"ok": False, "errors": ["content is required"], "warnings": []}

    mtype = normalize_memory_type(memory_type)
    stype = normalize_source_type(source_type)
    sref = _compact(str(source_ref or ""), 280)
    evidence = _compact(str(evidence_summary or ""), 400)
    conf = _normalize_confidence(confidence)
    now = _now_iso()
    row = CandidateRecord(
        candidate_id=uuid4().hex,
        type=mtype,
        content=body,
        source_type=stype,
        source_ref=sref,
        evidence_summary=evidence,
        confidence=conf,
        status=normalize_status(status),
        topic_key=_topic_key(mtype, body),
        created_at=now,
        updated_at=now,
        metadata=metadata or {},
    )
    rows = _read_candidates()
    rows.append(row)
    _write_candidates(rows)
    warnings: list[str] = []
    if not _has_required_provenance(stype, sref, evidence):
        warnings.append("candidate has weak provenance; cannot be promoted to active until source_ref and evidence_summary are set")
    return {"ok": True, "candidate": row.to_dict(), "warnings": warnings, "errors": []}


def list_candidates(status: str | None = None, limit: int = 10) -> dict[str, Any]:
    rows = _read_candidates()
    if status:
        s = normalize_status(status)
        rows = [row for row in rows if row.status == s]
    rows.sort(key=lambda row: row.updated_at, reverse=True)
    return {
        "ok": True,
        "items": [row.to_dict() for row in rows[: max(1, int(limit))]],
        "warnings": [],
        "errors": [],
    }


def transition_candidate(candidate_id: str, transition: str) -> dict[str, Any]:
    cid = str(candidate_id or "").strip()
    action = str(transition or "").strip().lower()
    rows = _read_candidates()
    idx = next((i for i, row in enumerate(rows) if row.candidate_id == cid), -1)
    if idx < 0:
        return {"ok": False, "warnings": [], "errors": ["candidate_not_found"]}
    target = rows[idx]

    if action in {"reject", "rejected"}:
        updated = CandidateRecord(**{**target.to_dict(), "status": "rejected", "updated_at": _now_iso()})
        rows[idx] = updated
        _write_candidates(rows)
        return {"ok": True, "candidate": updated.to_dict(), "warnings": [], "errors": []}

    if action not in {"approve", "approved", "write", "activate"}:
        return {"ok": False, "warnings": [], "errors": [f"invalid transition: {transition}"]}

    if not _has_required_provenance(target.source_type, target.source_ref, target.evidence_summary):
        return {"ok": False, "warnings": [], "errors": ["candidate_missing_provenance"]}

    promoted = promote_candidate(target)
    if not promoted.get("ok"):
        return promoted

    updated = CandidateRecord(**{**target.to_dict(), "status": "active", "updated_at": _now_iso()})
    rows[idx] = updated
    _write_candidates(rows)
    promoted["candidate"] = updated.to_dict()
    return promoted


def _similar_enough(a: str, b: str) -> bool:
    ax = _topic_key("note", a).split(":", 1)[-1]
    bx = _topic_key("note", b).split(":", 1)[-1]
    if not ax or not bx:
        return False
    if ax == bx:
        return True
    return ax in bx or bx in ax


def _find_merge_target(content: str, mtype: str, items: list[MemoryItem]) -> MemoryItem | None:
    for item in items:
        md = item.metadata if isinstance(item.metadata, dict) else {}
        itype = normalize_memory_type(md.get("type"))
        if itype != mtype:
            continue
        if item.content.strip().lower() == content.strip().lower():
            return item
        if _similar_enough(item.content, content):
            return item
    return None


def promote_candidate(candidate: CandidateRecord) -> dict[str, Any]:
    mtype = normalize_memory_type(candidate.type)
    selection = load_memory_provider()
    existing = _active_memories(limit=200)
    merge_target = _find_merge_target(candidate.content, mtype, existing)

    metadata = {
        "type": mtype,
        "source_type": normalize_source_type(candidate.source_type),
        "source_ref": candidate.source_ref,
        "evidence_summary": candidate.evidence_summary,
        "confidence": candidate.confidence,
        "status": "active",
        "updated_at": _now_iso(),
        "topic_key": candidate.topic_key,
    }
    if merge_target:
        metadata["merged_from"] = merge_target.id

    # Keep one compact active memory per topic: append merged update as the latest active fact.
    result = selection.provider.write(MemoryWrite(content=candidate.content, scope="ai", metadata=metadata))
    if not result.ok:
        return {
            "ok": False,
            "warnings": [str(result.warning or "")],
            "errors": ["memory write failed"],
        }

    if merge_target:
        superseded_metadata = dict(merge_target.metadata or {})
        superseded_metadata["status"] = "superseded"
        superseded_metadata["superseded_by"] = result.item.id if result.item else ""
        superseded_metadata["updated_at"] = _now_iso()
        selection.provider.write(
            MemoryWrite(
                content=merge_target.content,
                scope=merge_target.scope,
                metadata=superseded_metadata,
            )
        )

    return {
        "ok": True,
        "result": result.to_dict(),
        "merged": bool(merge_target),
        "warnings": [str(result.warning)] if result.warning else [],
        "errors": [],
    }


def direct_approved_write(
    content: str,
    *,
    memory_type: str | None,
    source_type: str,
    source_ref: str,
    evidence_summary: str,
    confidence: float | int | str | None = 0.9,
) -> dict[str, Any]:
    created = create_candidate(
        content,
        memory_type=memory_type,
        source_type=source_type,
        source_ref=source_ref,
        evidence_summary=evidence_summary,
        confidence=confidence,
        status="candidate",
        metadata={"approved_explicitly": True},
    )
    if not created.get("ok"):
        return created
    candidate = created.get("candidate") or {}
    return transition_candidate(str(candidate.get("candidate_id") or ""), "approve")


def memory_profile_get(scope: str | None = None, category: str | None = None, limit: int = 8) -> dict[str, Any]:
    config = load_assistant_config()
    scoped = scope if scope is not None else (category if category is not None else config.default_category)
    selection = load_memory_provider()
    items = selection.provider.recall(MemoryQuery(text="", scope=scoped, limit=max(1, int(limit) * 3)))
    active = []
    seen_topics: set[str] = set()
    for item in items:
        payload = _memory_payload(item)
        if payload["status"] == "active":
            key = str(payload.get("topic_key") or payload.get("content") or "").strip().lower()
            if key in seen_topics:
                continue
            seen_topics.add(key)
            active.append(payload)
    active = active[: max(1, int(limit))]
    return {
        "ok": True,
        "scope": scoped,
        "summary": f"{len(active)} active memories.",
        "items": active,
        "warnings": [],
        "errors": [],
    }


def memory_relevant_get(query: str = "", category: str | None = None, scope: str | None = None, limit: int = 6) -> dict[str, Any]:
    config = load_assistant_config()
    scoped = scope if scope is not None else (category if category is not None else config.default_category)
    selection = load_memory_provider()
    items = selection.provider.recall(MemoryQuery(text=query, scope=scoped, limit=max(1, int(limit) * 4)))
    rows = []
    seen_topics: set[str] = set()
    for item in items:
        payload = _memory_payload(item)
        if payload["status"] != "active":
            continue
        key = str(payload.get("topic_key") or payload.get("content") or "").strip().lower()
        if key in seen_topics:
            continue
        seen_topics.add(key)
        score, reason = _query_relevance_score(query=query, payload=payload)
        payload["relevance_score"] = score
        payload["reason"] = reason
        payload["source"] = {
            "source_type": payload.get("source_type") or "unknown",
            "source_ref": _compact(str(payload.get("source_ref") or ""), 120),
        }
        payload["content"] = _compact(str(payload.get("content") or ""), 220)
        rows.append(payload)

    rows.sort(key=lambda x: float(x.get("relevance_score") or 0.0), reverse=True)
    sliced = rows[: max(1, int(limit))]
    stable = [x for x in sliced if str(x.get("type") or "") in {"preference", "working_style", "project_fact", "decision"}]
    temporary = [x for x in sliced if str(x.get("type") or "") in {"task_state", "note"}]
    return {
        "ok": True,
        "scope": scoped,
        "query": query,
        "items": sliced,
        "stable_items": stable,
        "temporary_items": temporary,
        "summary": f"{len(sliced)} relevant memories (stable={len(stable)}, temporary={len(temporary)}).",
        "warnings": [],
        "errors": [],
    }


def working_context_get(category: str | None = None) -> dict[str, Any]:
    config = load_assistant_config()
    scoped = category if category is not None else config.default_category

    from assistant.action_loop import list_actions  # type: ignore
    from assistant.agent_orchestration import list_handoffs  # type: ignore

    accepted = list_actions(state="accepted", limit=1, remember_list=False)
    proposed_or_deferred = [
        x for x in list_actions(limit=20, remember_list=False)
        if x.state in {"proposed", "deferred"}
    ][:3]

    decision_memory = memory_relevant_get(query="keputusan terbaru prioritas", category=scoped, limit=3)
    decision_items = [
        x for x in (decision_memory.get("items") or []) if str(x.get("type") or "") == "decision"
    ][:2]

    handoffs = list_handoffs(limit=3).get("items") or []
    latest_handoff = handoffs[0] if handoffs else None

    context = {
        "session_scope": scoped,
        "current_focus": {
            "action_id": accepted[0].action_id if accepted else None,
            "title": accepted[0].title if accepted else None,
            "state": accepted[0].state if accepted else None,
        },
        "pending_focus": [
            {
                "action_id": x.action_id,
                "title": x.title,
                "state": x.state,
                "updated_at": x.updated_at,
            }
            for x in proposed_or_deferred
        ],
        "recent_decisions": [
            {
                "content": _compact(str(x.get("content") or ""), 180),
                "updated_at": x.get("updated_at"),
                "reason": x.get("reason"),
            }
            for x in decision_items
        ],
        "active_handoff": {
            "handoff_id": (latest_handoff or {}).get("handoff_id"),
            "target_agent": (latest_handoff or {}).get("target_agent"),
            "status": (latest_handoff or {}).get("status"),
            "source_action_id": (latest_handoff or {}).get("source_action_id"),
            "updated_at": (latest_handoff or {}).get("updated_at"),
        },
        "generated_at": _now_iso(),
        "expires_in_hours": 24,
        "summary": "Temporary working context for current focus, pending actions, recent decisions, and active handoff.",
        "notice": "No external action was applied.",
    }
    return {"ok": True, "scope": scoped, "context": context, "warnings": [], "errors": []}


def memory_health_get() -> dict[str, Any]:
    selection = load_memory_provider()
    active_items = _active_memories(limit=300)
    payloads = [_memory_payload(item) for item in active_items]
    active_count = len([x for x in payloads if x["status"] == "active"])
    candidates = _read_candidates()
    candidate_count = len([x for x in candidates if x.status == "candidate"])
    rejected_count = len([x for x in candidates if x.status == "rejected"])
    warnings: list[str] = []
    if not selection.active_health.healthy:
        warnings.append("memory provider unhealthy")
    if candidate_count > 20:
        warnings.append("candidate backlog is high")
    summary = f"provider={selection.active_provider}, active={active_count}, candidate={candidate_count}, rejected={rejected_count}"
    return {
        "ok": True,
        "summary": summary,
        "provider": selection.to_dict(),
        "active_count": active_count,
        "candidate_count": candidate_count,
        "rejected_count": rejected_count,
        "warnings": warnings,
        "errors": [],
    }
