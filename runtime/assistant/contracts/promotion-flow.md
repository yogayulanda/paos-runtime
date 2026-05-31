# Promotion Flow Contract

Purpose: provide suggest-only durable context promotion guidance for `/promote-memory`.

Required sections:
- Suggested Durable Updates
- Target files
- Why this should be promoted
- What should NOT be promoted
- Confidence
- Reminder

Allowed target suggestions:
- core/current-state.md
- domains/daily/notes.md
- domains/work/current-project.md
- domains/career/action-plan/next-actions.md
- domains/branding/content-topics/main-topics.md

Rules:
- Suggestion only: no write, no apply patch, no commit, no push.
- Read from existing assistant artifacts and memory recall only.
- Keep output compact and deterministic.
