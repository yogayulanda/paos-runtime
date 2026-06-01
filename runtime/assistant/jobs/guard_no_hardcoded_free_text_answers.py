from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

FILES = [
    ROOT / "bot" / "commands" / "assistant_query.py",
    ROOT / "runtime" / "assistant" / "brief" / "generator.py",
    ROOT / "runtime" / "assistant" / "action_loop" / "daily.py",
    ROOT / "runtime" / "assistant" / "mcp" / "server.py",
    ROOT / "runtime" / "assistant" / "memory" / "personal_context.py",
]

FORBIDDEN_SNIPPETS = (
    "_release_focus_block",
    "_render_daily_polished",
    "_render_general_question_fallback",
    "_render_identity_answer",
    "_render_working_style_answer",
    "_render_current_build_answer",
    "_render_personal_context_answer",
    "live Telegram UX personal-context aware",
    "release blocker sebelum rilis stabil",
    "context priority & identity grounding",
    "failure live pada prompt pagi/next/fokus/siapa saya",
    "rapikan 3 polish terakhir v1.0.0 sebelum commit",
    "selesaikan polish live Telegram, bukan tambah fitur baru",
    "bikin v1.0.0 terasa enak dipakai di Telegram",
    "Saya belum kebaca jelas",
    "Coba tulis tujuanmu",
    "GitHub Copilot besok bisa dibagi jadi dasar penggunaan",
    "materi training GitHub Copilot besok bisa dibagi",
    "Americano biasanya enak dicampur",
    "2026-05-28: PAOS v3 setup selesai",
    "Tag inference strength",
    "Daily Action Draft",
    "Run assistant diagnostics, then execute the top Build opportunity and regenerate the brief.",
)


def main() -> int:
    hits: list[str] = []
    for path in FILES:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for snippet in FORBIDDEN_SNIPPETS:
            if snippet in text:
                hits.append(f"{path.relative_to(ROOT)} :: {snippet}")

    if hits:
        print("guard_no_hardcoded_free_text_answers: FAIL")
        for item in hits:
            print(item)
        return 2

    print("guard_no_hardcoded_free_text_answers: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
