from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from assistant.action_loop import create_action_from_draft

ROOT = Path(__file__).resolve().parents[2]

SOURCE_JOBS = {
    "rss-collector",
    "threads-account",
    "threads-keyword",
    "github-collector",
    "candidate-pool",
    "signal-builder",
    "digest",
    "insights",
}


@dataclass(frozen=True)
class SourceStatus:
    payload: dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_dir() -> Path:
    env_file = ROOT / ".env"
    if env_file.exists():
        try:
            for raw_line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "PAOS_RUNTIME_PATH":
                    candidate = Path(value.strip().strip('"').strip("'"))
                    if candidate.exists():
                        return candidate
        except Exception:
            pass
    return ROOT / "runtime"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _resolve_latest_file(root_dir: Path, filename: str) -> Path | None:
    if not root_dir.exists() or not root_dir.is_dir():
        return None
    candidates = sorted(
        [path for path in root_dir.glob(f"*/{filename}") if path.is_file()],
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _resolve_latest_statuses(runtime_dir: Path) -> list[dict[str, Any]]:
    runs_dir = runtime_dir / ".runtime" / "runs"
    out: list[dict[str, Any]] = []
    if not runs_dir.exists() or not runs_dir.is_dir():
        return out
    for status_path in sorted(runs_dir.glob("*/latest.json")):
        payload = _read_json(status_path)
        if not payload:
            continue
        job = str(payload.get("job") or status_path.parent.name)
        if job not in SOURCE_JOBS:
            continue
        out.append({"job": job, "path": status_path, "payload": payload})
    return out


def get_source_status(category: str = "ai") -> SourceStatus:
    runtime_dir = _runtime_dir()
    warnings: list[str] = []
    statuses = _resolve_latest_statuses(runtime_dir)

    digest = _resolve_latest_file(runtime_dir / "intelligence" / "digests", f"{category}.md")
    insight = _resolve_latest_file(runtime_dir / "intelligence" / "insights", f"{category}.md")
    candidate = _resolve_latest_file(runtime_dir / "intelligence" / "candidates", f"{category}.jsonl")

    items = []
    state_counter = Counter()
    for row in statuses:
        payload = row["payload"]
        status = str(payload.get("status") or "unknown")
        state_counter[status] += 1
        finished_at = str(payload.get("finished_at") or "")
        health = "healthy"
        if status in {"failed"}:
            health = "error"
        elif status in {"success_with_warnings", "skipped", "minimal"}:
            health = "warning"
        items.append(
            {
                "job": row["job"],
                "status": status,
                "health": health,
                "finished_at": finished_at,
                "last_success_at": payload.get("finished_at") if status.startswith("success") else None,
                "items_collected": payload.get("items_collected") or payload.get("candidates_written") or 0,
                "warnings": payload.get("warnings") or [],
                "errors": payload.get("errors") or ([] if not payload.get("error_message") else [payload.get("error_message")]),
                "path": str(row["path"]),
            }
        )

    if not statuses:
        warnings.append("no source jobs found in .runtime/runs")

    candidate_count = len(_read_jsonl(candidate)) if candidate else 0
    maintenance = "Pertahankan source aktif saat ini."
    if state_counter.get("failed", 0) > 0:
        maintenance = "Perbaiki source yang failed dulu, lalu rerun collector terkait."
    elif candidate_count == 0:
        maintenance = "Candidate kosong; cek source config dan jalankan ulang collector + candidate pool."

    summary = (
        f"Source intelligence: healthy={sum(1 for i in items if i['health'] == 'healthy')}, "
        f"warning={sum(1 for i in items if i['health'] == 'warning')}, "
        f"error={sum(1 for i in items if i['health'] == 'error')}, "
        f"candidates={candidate_count}."
    )

    return SourceStatus(
        {
            "ok": True,
            "generated_at": now_iso(),
            "source": "paos.source-intelligence",
            "status": "ready" if items else "minimal",
            "summary": summary,
            "category": category,
            "items": items,
            "artifacts": {
                "candidate": {"exists": bool(candidate), "path": str(candidate) if candidate else None, "date": candidate.parent.name if candidate else None},
                "digest": {"exists": bool(digest), "path": str(digest) if digest else None, "date": digest.parent.name if digest else None},
                "insight": {"exists": bool(insight), "path": str(insight) if insight else None, "date": insight.parent.name if insight else None},
            },
            "candidate_count": candidate_count,
            "recommended_next_maintenance_action": maintenance,
            "warnings": warnings,
            "errors": [],
        }
    )


def get_source_candidates(category: str = "ai", source: str | None = None, limit: int = 10) -> dict[str, Any]:
    runtime_dir = _runtime_dir()
    candidate_file = _resolve_latest_file(runtime_dir / "intelligence" / "candidates", f"{category}.jsonl")
    rows = _read_jsonl(candidate_file) if candidate_file else []
    normalized_source = str(source or "").strip().lower()
    if normalized_source:
        rows = [r for r in rows if str(r.get("platform") or "").strip().lower() == normalized_source or str((r.get("candidate_metadata") or {}).get("policy") or "").strip().lower() == normalized_source]
    rows = rows[: max(1, int(limit))]
    return {
        "ok": True,
        "generated_at": now_iso(),
        "source": "paos.source-intelligence",
        "summary": f"Loaded {len(rows)} candidates.",
        "category": category,
        "items": rows,
        "warnings": [],
        "errors": [],
    }


def _insight_jsonl_path(runtime_dir: Path, category: str) -> Path | None:
    insight_root = runtime_dir / "intelligence" / "insights"
    latest_md = _resolve_latest_file(insight_root, f"{category}.md")
    if not latest_md:
        return None
    candidate = latest_md.with_suffix(".jsonl")
    return candidate if candidate.exists() else None


def get_source_insights(category: str = "ai", limit: int = 5) -> dict[str, Any]:
    runtime_dir = _runtime_dir()
    path = _insight_jsonl_path(runtime_dir, category)
    rows = _read_jsonl(path) if path else []
    rows = rows[: max(1, int(limit))]
    return {
        "ok": True,
        "generated_at": now_iso(),
        "source": "paos.source-intelligence",
        "summary": f"Loaded {len(rows)} insights.",
        "category": category,
        "items": rows,
        "warnings": [],
        "errors": [],
    }


def get_source_digest(category: str = "ai", limit: int = 8) -> dict[str, Any]:
    runtime_dir = _runtime_dir()
    digest_file = _resolve_latest_file(runtime_dir / "intelligence" / "digests", f"{category}.md")
    if not digest_file:
        return {
            "ok": True,
            "generated_at": now_iso(),
            "source": "paos.source-intelligence",
            "summary": "Digest belum tersedia.",
            "category": category,
            "items": [],
            "warnings": ["digest artifact missing"],
            "errors": [],
        }
    lines = [ln.strip() for ln in digest_file.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    items = [ln.lstrip("- ") for ln in lines if ln.startswith("- ")][: max(1, int(limit))]
    return {
        "ok": True,
        "generated_at": now_iso(),
        "source": "paos.source-intelligence",
        "summary": f"Loaded {len(items)} digest points.",
        "category": category,
        "items": items,
        "artifact_path": str(digest_file),
        "warnings": [],
        "errors": [],
    }


def get_source_recommendation(category: str = "ai") -> dict[str, Any]:
    status = get_source_status(category=category).payload
    candidates = get_source_candidates(category=category, limit=200).get("items") or []
    by_platform = Counter(str(x.get("platform") or "unknown") for x in candidates)
    top = by_platform.most_common(3)

    recommendations = []
    if not top:
        recommendations.append("Tambah/aktifkan source RSS atau Threads keyword agar candidate tidak kosong.")
    else:
        recommendations.append(
            "Source paling berguna minggu ini (berdasarkan candidate terbaru): "
            + ", ".join([f"{name} ({count})" for name, count in top])
        )
    for item in status.get("items") or []:
        if item.get("health") == "error":
            recommendations.append(f"Perbaiki job {item.get('job')} karena status error.")
        elif item.get("health") == "warning":
            recommendations.append(f"Tinjau warning di {item.get('job')} agar sinyal lebih bersih.")

    return {
        "ok": True,
        "generated_at": now_iso(),
        "source": "paos.source-intelligence",
        "summary": "Rekomendasi tuning source siap.",
        "category": category,
        "items": recommendations[:6],
        "signals": {"candidate_count_by_platform": dict(by_platform)},
        "warnings": [],
        "errors": [],
    }


def create_action_from_latest_insight(category: str = "ai", reference: str | None = None) -> dict[str, Any]:
    insight_payload = get_source_insights(category=category, limit=1)
    items = insight_payload.get("items") or []
    if not items:
        return {
            "ok": False,
            "generated_at": now_iso(),
            "source": "paos.source-intelligence",
            "summary": "Insight terbaru tidak ditemukan.",
            "warnings": [],
            "errors": ["insight_not_found"],
        }

    insight = items[0]
    title = str(insight.get("title") or "Insight terbaru")
    reason = str(insight.get("reason") or "")
    draft = {
        "title": f"Action dari insight: {title}",
        "summary": reason[:280] or "Action draft dari insight terbaru.",
        "steps": [
            "Validasi relevansi insight dengan prioritas hari ini.",
            "Jalankan satu eksperimen kecil berbasis insight ini.",
            "Catat hasil dan update keputusan berikutnya.",
        ],
        "category": category,
        "kind": "daily",
        "action_class": "draft_only",
        "evidence": {
            "reference": reference or "latest_insight",
            "insight": insight,
            "provenance": {
                "source": "intelligence/insights",
                "category": category,
            },
        },
    }
    result = create_action_from_draft(draft, actor="source-intelligence")
    payload = result.to_dict()
    payload["ok"] = bool(result.ok)
    payload["generated_at"] = now_iso()
    payload["source"] = "paos.source-intelligence"
    payload["summary"] = "Proposed action dibuat dari insight terbaru. No external action was applied."
    return payload
