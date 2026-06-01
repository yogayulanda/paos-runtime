# PAOS External Agent Starter

Use PAOS MCP as the source of truth when available.
Find the latest accepted or pending PAOS action.
Inspect relevant context/evidence.
Continue safely with local validation.

Hard boundaries:
- Do not mutate memory durably unless explicit approval-safe path is requested.
- Do not mutate scheduler, GitHub, repo remote, or gateway.
- Do not enable/start Hermes gateway.
- Do not expose public API/tunnel.
- Handoff is draft/manual context only (handoff != execution).
- Accepted action is direction only (accepted != executed).
- No commit/push unless explicitly requested.

Phase 10 ops expectations:
- Keep natural-language UX primary.
- Treat slash commands as fallback/admin/debug only.
- Validate with `venv/bin/python runtime/assistant/jobs/validate_commit_readiness.py` before handoff.
- Ensure final gateway state remains stopped.

Report format:
1. Summary
2. Files changed
3. Validations run (pass/fail)
4. Blockers/risks
5. Next safe step

If you cannot access PAOS MCP, say so clearly and ask for the smallest context needed.
