import re


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def route_intent(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not normalized:
        return "unknown"

    if _contains_any(normalized, ("dashboard", "ringkasan", "overview", "home screen")):
        return "dashboard"
    if _contains_any(normalized, ("operating summary", "status paos hari ini", "apa status paos hari ini", "daily operating summary")):
        return "operating_summary"
    if _contains_any(normalized, ("buat daily plan", "daily plan dari context", "daily plan dari context memory source", "rencana harian dari context")):
        return "daily_plan"
    if _contains_any(normalized, ("hari ini", "harus ngapain", "prioritas", "today", "daily")):
        return "daily"
    if _contains_any(normalized, ("insight", "relevan", "signal", "penting")):
        return "insight_relevance"
    if _contains_any(normalized, ("terakhir", "ngerjain", "memory", "inget", "riwayat")):
        return "memory"
    if _contains_any(normalized, ("handoff", "lanjutkan di codex", "lanjutkan di claude", "serahin")):
        return "handoff"
    if _contains_any(normalized, ("masuk repo paos", "promote", "promosi", "durable", "simpan ke paos")):
        return "context_update"
    if _contains_any(
        normalized,
        (
            "context saya sehat gak",
            "konteks saya sehat gak",
            "context sehat",
            "konteks sehat",
            "health context",
            "context health",
            "cek context",
            "cek konteks",
            "kondisi context",
            "kondisi konteks",
            "health check",
        ),
    ):
        return "context_health"
    if _contains_any(normalized, ("opportunity", "peluang", "bisa dikerjain")):
        return "opportunities"
    if _contains_any(normalized, ("status", "siap jalan", "readiness", "runtime")):
        return "status"

    return "unknown"
