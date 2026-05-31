Purpose: define Phase 5A controlled write flow for durable context updates.

Scope:
- Draft-first, preview-first, explicit-apply only.
- Source input from existing promotion suggestion logic.
- No scheduler, no GitHub source, no Hermes bridge, no public HTTP/SSE/MCP.
- No auto commit or auto push.

Telegram commands:
- `/draft-context-update`
  - Generates a compact draft from promotion suggestions.
  - Stores draft artifact under `.runtime/assistant/write-drafts/`.
- `/preview-context-update`
  - Renders compact preview of latest draft target files and proposed additions.
  - Read-only, no mutation.
- `/apply-context-update CONFIRM`
  - Applies latest draft only when explicit `CONFIRM` token is present.
  - Without `CONFIRM`, no mutation.

Allowlisted durable targets:
- `core/current-state.md`
- `domains/daily/notes.md`
- `domains/work/current-project.md`
- `domains/career/action-plan/next-actions.md`
- `domains/branding/content-topics/main-topics.md`

Safety rules:
- Block absolute paths.
- Block path traversal.
- Block unknown targets.
- Block archive paths.
- Require draft artifact before preview/apply.
- Apply writes audit artifact and per-target backups before mutation.
- If personal-context root is missing/unreadable, return warning and do not apply.

Artifacts:
- Draft pointer: `.runtime/assistant/write-drafts/latest.json`
- Dated draft: `.runtime/assistant/write-drafts/YYYY-MM-DD/context-update-draft.json`
- Apply audit: `.runtime/assistant/write-drafts/applied/<timestamp>-audit.json`
