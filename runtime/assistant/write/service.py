import json
from datetime import datetime
from pathlib import Path
import os


ALLOWED_TARGETS = {
    "core/current-state.md",
    "domains/daily/notes.md",
    "domains/work/current-project.md",
    "domains/career/action-plan/next-actions.md",
    "domains/branding/content-topics/main-topics.md",
}


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _draft_root() -> Path:
    return _runtime_root() / ".runtime" / "assistant" / "write-drafts"


def _latest_draft_path() -> Path:
    return _draft_root() / "latest.json"


def _today_draft_path() -> Path:
    today = datetime.now().astimezone().date().isoformat()
    return _draft_root() / today / "context-update-draft.json"


def _parse_dot_env(env_path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not env_path.exists() or not env_path.is_file():
        return data
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def resolve_personal_context_root() -> tuple[Path | None, list[str]]:
    warnings: list[str] = []
    env_candidates = [
        os.environ.get("PAOS_PERSONAL_CONTEXT_ROOT"),
        os.environ.get("PAOS_CONTEXT_PATH"),
    ]
    dot_env = _parse_dot_env(_runtime_root() / ".env")
    env_candidates.extend(
        [dot_env.get("PAOS_PERSONAL_CONTEXT_ROOT"), dot_env.get("PAOS_CONTEXT_PATH")]
    )
    for candidate in env_candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser()
        if path.exists() and path.is_dir():
            return path, warnings
        warnings.append(f"configured personal-context root not found: {path}")
    warnings.append("personal-context root is not configured")
    return None, warnings


def _is_safe_relative_target(target: str) -> bool:
    target_path = Path(target)
    if target_path.is_absolute():
        return False
    parts = target_path.parts
    if any(part in {"..", ""} for part in parts):
        return False
    lowered = [part.lower() for part in parts]
    if "archive" in lowered or "archives" in lowered:
        return False
    return True


def _make_entry(path: str, reason: str, content: str) -> dict:
    return {
        "target_path": path,
        "operation": "append",
        "reason": reason.strip(),
        "content": content.strip(),
    }


def generate_draft(suggestions: list[dict], sections: dict) -> dict:
    draft_entries: list[dict] = []
    warnings: list[str] = []
    seen_targets: set[str] = set()
    source_sections = sections if isinstance(sections, dict) else {}
    for item in suggestions:
        target = str((item or {}).get("path") or "").strip()
        reason = str((item or {}).get("reason") or "").strip()
        if not target:
            continue
        if target not in ALLOWED_TARGETS:
            warnings.append(f"blocked unknown target: {target}")
            continue
        if not _is_safe_relative_target(target):
            warnings.append(f"blocked unsafe target path: {target}")
            continue
        if target in seen_targets:
            continue

        content = ""
        if target == "core/current-state.md":
            decisions = source_sections.get("decisions") or []
            if decisions:
                content = "\n".join([f"- {str(x).strip()}" for x in decisions[:3] if str(x).strip()])
        elif target == "domains/daily/notes.md":
            progress = source_sections.get("recent_progress") or []
            if progress:
                content = "\n".join([f"- {str(x).strip()}" for x in progress[:3] if str(x).strip()])
        elif target == "domains/work/current-project.md":
            next_actions = source_sections.get("next_actions") or []
            if next_actions:
                content = "\n".join([f"- {str(x).strip()}" for x in next_actions[:3] if str(x).strip()])
        elif target == "domains/career/action-plan/next-actions.md":
            blockers = source_sections.get("blockers") or []
            if blockers:
                content = "\n".join([f"- Follow up: {str(x).strip()}" for x in blockers[:3] if str(x).strip()])
        elif target == "domains/branding/content-topics/main-topics.md":
            focus = str(source_sections.get("focus_today") or "").strip()
            if focus:
                content = f"- Theme candidate: {focus}"

        if not content:
            warnings.append(f"no draft content inferred for target: {target}")
            continue

        draft_entries.append(_make_entry(target, reason, content))
        seen_targets.add(target)

    context_root, root_warnings = resolve_personal_context_root()
    warnings.extend(root_warnings)

    payload = {
        "created_at": datetime.now().astimezone().isoformat(),
        "source": "promotion-suggestions",
        "status": "draft",
        "context_root": str(context_root) if context_root else None,
        "entries": draft_entries,
        "warnings": warnings,
    }

    draft_file = _today_draft_path()
    draft_file.parent.mkdir(parents=True, exist_ok=True)
    draft_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _latest_draft_path().parent.mkdir(parents=True, exist_ok=True)
    _latest_draft_path().write_text(
        json.dumps(
            {
                "created_at": payload["created_at"],
                "latest_draft_path": str(draft_file),
                "status": payload["status"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"draft_path": str(draft_file), "payload": payload}


def _read_latest_draft() -> tuple[dict | None, Path | None, list[str]]:
    warnings: list[str] = []
    latest = _latest_draft_path()
    if not latest.exists():
        return None, None, ["latest draft not found"]
    try:
        meta = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, None, [f"failed to parse latest draft pointer: {exc}"]
    path_str = str(meta.get("latest_draft_path") or "").strip()
    if not path_str:
        return None, None, ["latest draft pointer is empty"]
    draft_path = Path(path_str)
    if not draft_path.exists():
        return None, draft_path, [f"latest draft file is missing: {draft_path}"]
    try:
        payload = json.loads(draft_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, draft_path, [f"failed to parse latest draft: {exc}"]
    return payload, draft_path, warnings


def build_preview() -> dict:
    payload, draft_path, warnings = _read_latest_draft()
    if not payload:
        return {"ok": False, "warnings": warnings, "draft_path": str(draft_path) if draft_path else None}
    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    preview_items = []
    for entry in entries:
        target = str((entry or {}).get("target_path") or "").strip()
        content = str((entry or {}).get("content") or "").strip()
        preview_items.append(
            {
                "target_path": target,
                "reason": str((entry or {}).get("reason") or "").strip(),
                "addition_preview": content[:240],
                "added_lines": len([line for line in content.splitlines() if line.strip()]),
            }
        )
    return {
        "ok": True,
        "draft_path": str(draft_path),
        "target_files": [item.get("target_path") for item in preview_items],
        "items": preview_items,
        "warnings": list(payload.get("warnings") or []),
    }


def apply_latest_draft(confirm_token: str) -> dict:
    if str(confirm_token or "").strip().upper() != "CONFIRM":
        return {"ok": False, "applied": False, "warnings": ["missing CONFIRM token; no changes applied"]}

    payload, draft_path, warnings = _read_latest_draft()
    if not payload:
        return {"ok": False, "applied": False, "warnings": warnings}

    context_root, root_warnings = resolve_personal_context_root()
    warnings.extend(root_warnings)
    if not context_root:
        return {"ok": False, "applied": False, "warnings": warnings}

    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    if not entries:
        return {"ok": False, "applied": False, "warnings": ["draft has no entries to apply", *warnings]}

    audit_dir = _draft_root() / "applied"
    audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    audit_path = audit_dir / f"{stamp}-audit.json"
    backup_dir = audit_dir / f"{stamp}-backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    applied_targets = []
    blocked_targets = []
    for entry in entries:
        target = str((entry or {}).get("target_path") or "").strip()
        content = str((entry or {}).get("content") or "").strip()
        if target not in ALLOWED_TARGETS:
            blocked_targets.append({"target_path": target, "reason": "unknown target"})
            continue
        if not _is_safe_relative_target(target):
            blocked_targets.append({"target_path": target, "reason": "unsafe target"})
            continue
        target_path = (context_root / target).resolve()
        root_resolved = context_root.resolve()
        if root_resolved not in target_path.parents and target_path != root_resolved:
            blocked_targets.append({"target_path": target, "reason": "path escapes context root"})
            continue
        if not target_path.exists():
            if not target_path.parent.exists():
                blocked_targets.append({"target_path": target, "reason": "target parent path is missing"})
                continue
            target_path.touch()
        original = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        backup_path = backup_dir / target.replace("/", "__")
        backup_path.write_text(original, encoding="utf-8")
        to_append = content.strip()
        if not to_append:
            blocked_targets.append({"target_path": target, "reason": "empty content"})
            continue
        append_block = f"\n\n## PAOS Controlled Update ({datetime.now().astimezone().date().isoformat()})\n{to_append}\n"
        target_path.write_text(original.rstrip() + append_block, encoding="utf-8")
        applied_targets.append(target)

    audit_payload = {
        "applied_at": datetime.now().astimezone().isoformat(),
        "draft_path": str(draft_path) if draft_path else None,
        "context_root": str(context_root),
        "applied_targets": applied_targets,
        "blocked_targets": blocked_targets,
        "warnings": warnings,
    }
    audit_path.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "applied": bool(applied_targets),
        "applied_targets": applied_targets,
        "blocked_targets": blocked_targets,
        "warnings": warnings,
        "audit_path": str(audit_path),
    }
