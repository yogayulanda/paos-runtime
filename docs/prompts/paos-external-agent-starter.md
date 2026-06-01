# PAOS External Agent Starter

Use PAOS MCP as the source of truth when available.
Find the latest accepted or pending PAOS action.
Inspect relevant context/evidence.
Continue safely with local validation.
Do not mutate memory durably, scheduler, GitHub, repo remote, or gateway.
Handoff is draft/manual context only (handoff != execution).
Accepted action is direction only (accepted != executed).
No commit/push unless explicitly requested.
Report format:
1. Summary
2. Files changed
3. Validations run (pass/fail)
4. Blockers/risks
5. Next safe step
If you cannot access PAOS MCP, say so clearly and ask for the smallest context needed.
