from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any

from .factory import load_memory_provider
from .provider import MemoryQuery, MemoryWrite

ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = ROOT / "runtime" / "assistant" / "memory" / "runtime" / "personal_context_sync_state.json"


@dataclass(frozen=True)
class ContextFile:
    key: str
    rel_path: str
    memory_type: str


BASELINE_FILES: tuple[ContextFile, ...] = (
    ContextFile("context_map", "CONTEXT_MAP.md", "project_fact"),
    ContextFile("identity", "core/identity.md", "project_fact"),
    ContextFile("working_style", "core/working-style.md", "working_style"),
    ContextFile("current_state", "core/current-state.md", "task_state"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_personal_context_root() -> tuple[Path | None, list[str]]:
    warnings: list[str] = []
    candidates = [
        os.environ.get("PAOS_PERSONAL_CONTEXT_ROOT"),
        os.environ.get("PAOS_CONTEXT_PATH"),
        os.environ.get("PAOS_CONTEXT_REPO"),
    ]
    env_path = ROOT / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in {"PAOS_PERSONAL_CONTEXT_ROOT", "PAOS_CONTEXT_PATH", "PAOS_CONTEXT_REPO"}:
                candidates.append(value.strip())
    for item in candidates:
        if not item:
            continue
        path = Path(item).expanduser()
        if path.exists() and path.is_dir():
            return path, warnings
        warnings.append(f"configured personal-context root not found: {path}")
    warnings.append("personal-context root is not configured")
    return None, warnings


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _compact(text: str, max_chars: int = 360) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())[:max_chars]


def _clean_markdown_text(text: str) -> str:
    cleaned = str(text or "").replace("\ufeff", "")
    cleaned = re.sub(r"`", "", cleaned)
    cleaned = re.sub(r"\*{1,2}", "", cleaned)
    cleaned = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -|;,")


def _markdown_field(lines: list[str], label: str) -> str:
    pattern = re.compile(rf"^\*\*{re.escape(label)}:\*\*\s*(.+)$", re.I)
    for line in lines:
        match = pattern.match(line)
        if match:
            return _clean_markdown_text(match.group(1))
    return ""


def _extract_bullets(lines: list[str]) -> list[str]:
    bullets: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            cleaned = _clean_markdown_text(stripped[2:])
            if cleaned:
                bullets.append(cleaned)
    return bullets

def _split_markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "_root"
    sections[current] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current = _clean_markdown_text(line[3:]).lower()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections

def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in markers)

def _extract_dated_entries(text: str) -> list[tuple[date | None, str]]:
    entries: list[tuple[date | None, str]] = []
    for line in str(text or "").splitlines():
        cleaned = _clean_markdown_text(line)
        if not cleaned:
            continue
        match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", cleaned)
        parsed_date: date | None = None
        if match:
            try:
                parsed_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            except Exception:
                parsed_date = None
        entries.append((parsed_date, cleaned))
    return entries

def _is_background_history_line(text: str, *, today: date | None = None) -> bool:
    cleaned = _clean_markdown_text(text)
    lowered = cleaned.lower()
    if not lowered:
        return False
    history_markers = (
        "setup selesai",
        "fully operational",
        "auto-sync",
        "semua komponen verified working",
        "source of truth disatukan",
        "operating context confirmed",
        "daily memory sync committed",
    )
    if any(marker in lowered for marker in history_markers):
        return True
    if today is None:
        today = datetime.now(timezone.utc).date()
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", lowered)
    if match:
        try:
            parsed = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except Exception:
            return False
        if parsed < today:
            return True
    return False

def _working_style_natural_summary(lines: list[str]) -> str:
    bullets = _extract_bullets(lines)
    mapped: list[str] = []
    mapping: list[tuple[tuple[str, ...], str]] = [
        (("synthesize first", "observer + synthesizer"), "rangkum dulu sebelum masuk aksi"),
        (("ask if ambiguous", "ask before starting"), "kalau ambigu, tanya seperlunya dulu"),
        (("do not enter action/strategy mode", "do not push toward output"), "jangan masuk mode aksi atau strategi sebelum diminta"),
        (("evidence-based", "repository-native", "runtime evidence first"), "keputusan berbasis bukti dan konteks repo"),
        (("slow and correct", "precision", "correct beats fast"), "presisi lebih penting daripada cepat tapi generik"),
        (("direct", "no motivational framing", "concise"), "gaya komunikasinya langsung, ringkas, dan tanpa motivasional berlebihan"),
    ]
    for bullet in bullets:
        lowered = bullet.lower()
        for markers, rendered in mapping:
            if any(marker in lowered for marker in markers) and rendered not in mapped:
                mapped.append(rendered)
                break
    if not mapped:
        return "Gaya kerja tersedia dari personal-context dan cenderung langsung, hati-hati, dan berbasis bukti."
    return _compact("; ".join(mapped), 320)

def _build_current_state_sections(lines: list[str]) -> dict[str, list[str]]:
    joined = "\n".join(lines)
    sections = _split_markdown_sections(joined)
    return {
        "projects_running": _extract_bullets(sections.get("projects running", [])),
        "active_decisions": _extract_bullets(sections.get("active decisions", [])),
        "priorities_this_week": _extract_bullets(sections.get("priorities this week", [])),
        "recent_signals": [item for _dt, item in _extract_dated_entries("\n".join(sections.get("recent signals / events", [])))],
    }

def _current_build_summary_from_sections(sections: dict[str, list[str]]) -> str:
    project_lines = sections.get("projects_running", [])
    paos_lines = [item for item in project_lines if "paos" in item.lower()]
    recent_runtime = [
        item for item in sections.get("recent_signals", [])
        if "paos" in item.lower() and _contains_any(item, ("telegram", "hermes", "mnemosyne", "runtime"))
    ]
    corpus = " ".join(paos_lines + recent_runtime).lower()
    if not corpus:
        return "PAOS Runtime masih menjadi build utama, tapi detail runtime terbaru belum cukup lengkap di source ini."

    parts = ["Kamu lagi bangun PAOS Runtime sebagai asisten operasional pribadi"]
    if "telegram" in corpus:
        parts.append("jalur utamanya lewat Telegram")
    if "hermes" in corpus:
        parts.append("Hermes jadi layer reasoning utamanya")
    if "mnemosyne" in corpus or "memory" in corpus or "context" in corpus:
        parts.append("ada layer context dan memory untuk grounding")
    if "approval" in corpus or "action" in corpus or "handoff" in corpus:
        parts.append("alur aksi dan approval tetap dibatasi terpisah")
    return _compact(", ".join(parts), 260)

def _background_summary_from_sections(sections: dict[str, list[str]]) -> str:
    background_lines = [
        item for item in sections.get("recent_signals", [])
        if _is_background_history_line(item) and _contains_any(item, ("paos", "telegram", "hermes", "mnemosyne", "context", "memory", "vault", "sync"))
    ]
    if not background_lines:
        return ""
    rendered = []
    for item in background_lines[:3]:
        compact = re.sub(r"\b\d{4}-\d{2}-\d{2}:?\s*", "", item).strip()
        rendered.append(compact)
    return _compact("Latar belakang penting: " + "; ".join(rendered), 320)

def _current_focus_summary_from_sections(sections: dict[str, list[str]]) -> str:
    priorities = [item for item in sections.get("priorities_this_week", []) if item]
    projects = [item for item in sections.get("projects_running", []) if item and not _is_background_history_line(item)]
    paos_projects = [item for item in projects if "paos" in item.lower()]
    paos_signals = [
        item for item in sections.get("recent_signals", [])
        if "paos" in item.lower() and not _is_background_history_line(item)
    ]
    if paos_projects:
        return _compact(f"Konteks project aktif yang paling relevan sekarang masih {paos_projects[0]}", 220)
    if paos_signals:
        return _compact(f"Sinyal kerja yang paling segar untuk fokus sekarang: {paos_signals[0]}", 220)
    if priorities:
        return _compact(f"Prioritas personal terdekat yang masih kebaca: {priorities[0]}", 220)
    if projects:
        return _compact(f"Project aktif yang masih kebaca: {projects[0]}", 220)
    return "Belum ada fokus terbaru yang cukup kuat dari current-state; jangan angkat catatan setup lama sebagai fokus aktif."


def _focus_confidence(current_focus_summary: str, focus_candidates: list[str], stale_warnings: list[str]) -> str:
    summary = str(current_focus_summary or "").lower()
    if not summary:
        return "low"
    if any(marker in summary for marker in ("paos v2", "phase 1", "restructure")):
        return "low"
    if "paos" in summary and focus_candidates:
        return "medium" if stale_warnings else "high"
    if any("stale" in warning.lower() or "latar belakang" in warning.lower() for warning in stale_warnings):
        return "low"
    if focus_candidates:
        return "medium"
    return "low"

def _query_profile(query: str) -> str:
    normalized = str(query or "").strip().lower()
    if any(token in normalized for token in ("siapa saya", "sipa saya", "profil saya")):
        return "identity"
    if any(token in normalized for token in ("working style", "gaya kerja", "cara kerja saya")):
        return "working_style"
    if any(token in normalized for token in ("bangun apa", "lagi bangun", "project saya", "proyek saya", "build apa")):
        return "current_build"
    if any(token in normalized for token in ("pagi", "next terbaik", "fokus", "ngapain", "hari ini")):
        return "daily_focus"
    return "general"


def _summarize_paos_runtime(items: list[str]) -> str:
    corpus = " ".join(items).lower()
    parts = ["PAOS Runtime masih jadi fokus utama kamu"]
    if "telegram" in corpus:
        parts.append("jalur utamanya lewat Telegram")
    if "mnemosyne" in corpus or "context" in corpus:
        parts.append("konteks kerjanya sudah rapih dan tersambung")
    if "operational" in corpus or "fully operational" in corpus:
        parts.append("fondasinya juga sudah jalan")
    elif "setup selesai" in corpus:
        parts.append("setup utamanya juga sudah selesai")
    return _compact(", ".join(parts), 220)


def _updated_at_value(metadata: dict[str, Any]) -> str:
    return str(metadata.get("updated_at") or "")


def _extract_summary(key: str, content: str) -> str:
    lines = [ln.strip() for ln in str(content or "").splitlines() if ln.strip()]
    if key == "identity":
        name = _markdown_field(lines, "Name")
        role = _markdown_field(lines, "Role")
        company = _markdown_field(lines, "Company")
        summary = ", ".join([x for x in [name, role, company] if x])
        return _compact(summary or "Identity profile tersedia dari source of truth personal-context.")
    if key == "working_style":
        return _working_style_natural_summary(lines)
    if key == "current_state":
        sections = _build_current_state_sections(lines)
        build_summary = _current_build_summary_from_sections(sections)
        if build_summary:
            return build_summary
        bullets = _extract_bullets(lines)
        if bullets:
            return _compact("; ".join([item for item in bullets if not _is_background_history_line(item)][:5]))
        return _compact("Current state tersedia dari personal-context.")
    if key == "context_map":
        return "CONTEXT_MAP tersedia sebagai manifest konteks personal dan rujukan file relevan."
    return _compact(lines[0] if lines else "")


def sync_personal_context_to_memory(max_chars: int = 3200) -> dict[str, Any]:
    root, warnings = resolve_personal_context_root()
    if not root:
        return {"ok": False, "warnings": warnings, "errors": ["personal_context_unavailable"], "items": []}

    selection = load_memory_provider()
    state = _read_state()
    files_state = state.get("files") if isinstance(state.get("files"), dict) else {}
    updated: list[dict[str, Any]] = []
    scanned: list[dict[str, Any]] = []

    for spec in BASELINE_FILES:
        path = root / spec.rel_path
        if not path.exists() or not path.is_file():
            warnings.append(f"missing personal-context file: {spec.rel_path}")
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        digest = _sha256(raw)
        summary = _extract_summary(spec.key, raw)
        summary_digest = _sha256(summary)
        scanned.append({"key": spec.key, "path": spec.rel_path, "sha256": digest})

        prev = files_state.get(spec.key) if isinstance(files_state.get(spec.key), dict) else {}
        if str(prev.get("sha256") or "") == digest and str(prev.get("summary_sha256") or "") == summary_digest:
            continue

        payload = f"[{spec.key}] {summary}"
        metadata = {
            "type": spec.memory_type,
            "status": "active",
            "source_type": "personal_context_repo",
            "source_ref": f"{root}/{spec.rel_path}",
            "evidence_summary": summary,
            "confidence": 0.96,
            "topic_key": f"{spec.key}:baseline",
            "updated_at": _now_iso(),
            "sync_source": "personal-context",
        }
        wr = selection.provider.write(MemoryWrite(content=payload, scope="ai", metadata=metadata))
        if wr.ok:
            updated.append({"key": spec.key, "path": spec.rel_path, "memory_id": (wr.item.id if wr.item else "")})
            files_state[spec.key] = {
                "sha256": digest,
                "summary_sha256": summary_digest,
                "updated_at": _now_iso(),
                "source_ref": metadata["source_ref"],
            }

    state["files"] = files_state
    state["last_synced_at"] = _now_iso()
    _write_state(state)

    return {
        "ok": True,
        "provider": selection.active_provider,
        "root": str(root),
        "updated_items": updated,
        "scanned_files": scanned,
        "warnings": warnings,
        "errors": [],
    }


def build_personal_context_pack(query: str, relevant_limit: int = 4) -> dict[str, Any]:
    sync = sync_personal_context_to_memory()
    selection = load_memory_provider()
    profile = _query_profile(query)
    baseline: dict[str, dict[str, str]] = {}
    root, root_warnings = resolve_personal_context_root()
    if root_warnings:
        sync_warnings = sync.get("warnings") if isinstance(sync.get("warnings"), list) else []
        sync["warnings"] = [*sync_warnings, *root_warnings]
    if root:
        for spec in BASELINE_FILES:
            path = root / spec.rel_path
            if not path.exists() or not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
            baseline[spec.key] = {
                "summary": _extract_summary(spec.key, raw),
                "source_ref": str(path)[:180],
                "updated_at": _now_iso(),
                "raw": raw,
            }

    from .service import working_context_get

    relevant = selection.provider.recall(MemoryQuery(text=str(query or "")[:180], scope="ai", limit=max(1, relevant_limit)))
    relevant_rows = []
    for row in relevant:
        md = row.metadata if isinstance(row.metadata, dict) else {}
        compact_content = _compact(row.content, 180)
        if _is_background_history_line(compact_content):
            continue
        relevant_rows.append(
            {
                "content": compact_content,
                "type": str(md.get("type") or "note"),
                "source_ref": str(md.get("source_ref") or "")[:140],
            }
        )

    working_context = working_context_get(category="ai")
    wc = working_context.get("context") if isinstance(working_context.get("context"), dict) else {}
    focus = (wc.get("current_focus") or {}) if isinstance(wc, dict) else {}
    working_summary = f"focus={str(focus.get('title') or 'belum ada')[:100]}, pending={len(wc.get('pending_focus') or []) if isinstance(wc, dict) else 0}"
    focus_title = _compact(str(focus.get("title") or ""), 160)
    generic_focus_titles = {"", "belum ada", "daily action draft", "draft aksi harian"}
    stale_warnings: list[str] = []
    current_state_raw = str((baseline.get("current_state") or {}).get("raw") or "")
    current_sections = _build_current_state_sections([ln.strip() for ln in current_state_raw.splitlines() if ln.strip()])
    current_build_summary = _current_build_summary_from_sections(current_sections)
    background_summary = _background_summary_from_sections(current_sections)
    current_focus_summary = _current_focus_summary_from_sections(current_sections)
    if profile in {"daily_focus", "current_build"} and current_build_summary:
        lowered_focus_summary = current_focus_summary.lower()
        prefer_build_summary = any(marker in lowered_focus_summary for marker in ("paos v2", "phase 1", "restructure"))
        current_focus_summary = _compact(
            current_build_summary if prefer_build_summary or "paos" not in lowered_focus_summary else current_focus_summary,
            220,
        )
    focus_is_stale = bool(focus_title) and (
        focus_title.lower() in generic_focus_titles or _is_background_history_line(focus_title)
    )
    runtime_focus_summary = focus_title if focus_title and not focus_is_stale else current_focus_summary
    if focus_is_stale:
        stale_warnings.append("working-context focus terlalu generik atau stale; jadikan background saja, bukan jawaban utama.")
    if background_summary:
        stale_warnings.append("catatan setup/operasional lama terdeteksi; pakai hanya sebagai latar belakang, bukan fokus aktif.")

    focus_candidates: list[str] = []
    for candidate in (
        focus_title,
        current_focus_summary,
        runtime_focus_summary,
        *((row.get("content") or "") for row in relevant_rows),
    ):
        compact_candidate = _compact(candidate, 180)
        if compact_candidate.lower() in generic_focus_titles:
            continue
        if compact_candidate and compact_candidate not in focus_candidates and not _is_background_history_line(compact_candidate):
            focus_candidates.append(compact_candidate)

    current_focus_confidence = _focus_confidence(current_focus_summary, focus_candidates, stale_warnings)

    return {
        "ok": bool(sync.get("ok")),
        "sync": {
            "updated_count": len(sync.get("updated_items") or []),
            "warnings": sync.get("warnings") or [],
        },
        "user_profile_summary": (baseline.get("identity") or {}).get("summary") or "",
        "identity_summary": (baseline.get("identity") or {}).get("summary") or "",
        "working_style_summary": (baseline.get("working_style") or {}).get("summary") or "",
        "current_state_summary": (baseline.get("current_state") or {}).get("summary") or "",
        "current_build_summary": current_build_summary,
        "current_focus_summary": current_focus_summary,
        "background_summary": background_summary,
        "identity_source_ref": (baseline.get("identity") or {}).get("source_ref") or "",
        "working_style_source_ref": (baseline.get("working_style") or {}).get("source_ref") or "",
        "current_state_source_ref": (baseline.get("current_state") or {}).get("source_ref") or "",
        "working_context_summary": working_summary,
        "runtime_focus_summary": runtime_focus_summary,
        "current_focus_confidence": current_focus_confidence,
        "current_focus_candidates": focus_candidates[:5],
        "stale_warnings": stale_warnings,
        "stale_or_background_warnings": stale_warnings,
        "source_refs": [
            x for x in [
                (baseline.get("identity") or {}).get("source_ref"),
                (baseline.get("working_style") or {}).get("source_ref"),
                (baseline.get("current_state") or {}).get("source_ref"),
            ] if x
        ],
        "relevant_memory_results": relevant_rows[:relevant_limit],
    }
