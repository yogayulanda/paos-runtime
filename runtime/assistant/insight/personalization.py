import re
from pathlib import Path


def _compact(value):
    return " ".join(str(value or "").split())


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _read_json(path: Path):
    import json

    raw = _read_text(path)
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _today() -> str:
    from datetime import datetime

    return datetime.now().astimezone().date().isoformat()


def _resolve_latest_file(base_dir: Path, filename: str) -> Path | None:
    today_candidate = base_dir / _today() / filename
    if today_candidate.exists():
        return today_candidate
    candidates = sorted(
        [path for path in base_dir.glob(f"*/{filename}") if path.is_file()],
        key=lambda item: item.parent.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _parse_sections(markdown_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for row in markdown_text.splitlines():
        line = row.rstrip()
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = _compact(line[3:])
            lines = []
            continue
        if current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return sections


def _top_line(body: str, default_value: str) -> str:
    for row in body.splitlines():
        line = _compact(row).lstrip("- ").strip()
        if line and not line.startswith("#"):
            return line
    return default_value


def _score(text: str, keywords: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword in lowered)


def build_personalized_insight(runtime_path: Path) -> dict[str, str]:
    insight_path = _resolve_latest_file(runtime_path / "intelligence" / "insights", "ai.md")
    digest_path = _resolve_latest_file(runtime_path / "intelligence" / "digests", "ai.md")
    context_path = _resolve_latest_file(runtime_path / "assistant" / "context", "assistant-context.json")

    insight_text = _read_text(insight_path) if insight_path else ""
    digest_text = _read_text(digest_path) if digest_path else ""
    context_payload = _read_json(context_path) if context_path else {}

    context_blob = _compact(
        " ".join(
            [
                str((context_payload.get("context") or {}).get("identity") or ""),
                str((context_payload.get("context") or {}).get("working_style") or ""),
                str((context_payload.get("context") or {}).get("active_projects") or ""),
            ]
        )
    ).lower()

    sections = _parse_sections(insight_text) if insight_text else {}
    candidate_pool: list[tuple[str, str]] = []
    for key in (
        "Yang Lagi Penting",
        "Yang Perlu Kamu Lakukan",
        "Peluang untuk Kamu",
        "Bahan Konten & Branding",
        "Yang Layak Dipelajari",
    ):
        body = sections.get(key, "")
        if body:
            candidate_pool.append((key, body))

    if not candidate_pool and digest_text:
        candidate_pool = [("Digest", digest_text)]

    target_keywords = (
        "agent",
        "coding",
        "workflow",
        "context engineering",
        "mcp",
        "memory",
        "claude",
        "codex",
        "github",
        "observability",
        "automation",
        "dashboard",
        "assistant",
        "forge",
        "product layer",
    )
    context_terms = tuple(set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", context_blob)))[0:40]

    best_title = "Insight"
    best_body = ""
    best_score = -1
    for title, body in candidate_pool:
        text = f"{title}\n{body}"
        score = _score(text, target_keywords) + _score(text, context_terms)
        if score > best_score:
            best_score = score
            best_title = title
            best_body = body

    relevant = _top_line(best_body, "Belum ada insight kuat yang bisa dipersonalisasi.")
    has_context = bool(context_payload)
    limited_note = " (personalization limited: assistant context missing)" if not has_context else ""

    why_you = (
        "Selaras dengan fokus dan pola kerja kamu di assistant context."
        if has_context
        else "Insight diambil dari artifact terbaru tanpa context personal."
    )
    paos_forge = "Relevan untuk PAOS/Forge karena berdampak ke kualitas context loop, assistant surface, atau alur eksekusi."
    work_career = "Bisa dipakai untuk prioritas kerja mingguan, positioning karier, dan keputusan next step teknis."
    content_opportunity = "Bisa jadi bahan konten ringkas: what changed, why it matters, dan aksi konkret."
    recommended = "Pilih 1 aksi kecil dari insight ini dan jalankan hari ini, lalu validasi hasilnya di context/brief berikutnya."

    return {
        "relevant_insight": f"{best_title}: {relevant}{limited_note}",
        "why_it_matters_to_you": why_you,
        "paos_forge_relevance": paos_forge,
        "work_career_relevance": work_career,
        "content_opportunity": content_opportunity,
        "recommended_action": recommended,
    }
