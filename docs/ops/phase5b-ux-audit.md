# Phase 5B UX Audit

## Telegram Command Audit

| Command | Current Behavior | Classification | Reason | Natural-Language Replacement | Risk Notes | Recommended Cleanup |
|---|---|---|---|---|---|---|
| `/start` | Entry greeting/help | keep | Standard Telegram entrypoint | "apa fokus saya sekarang?" | Low | Keep concise NL-first |
| `/help` | Help surface | keep | Fallback/admin discoverability | Any NL query | Low | Keep short, NL-first |
| `/hermes` | Hermes runtime status | keep | Ops/debug | "status Hermes gimana?" | Low | Keep fallback/admin |
| `/dashboard` | Assistant home summary | keep | Useful fallback view | "dashboard PAOS saya gimana?" | Low | Keep, de-emphasize in UX |
| `/context` | Context health | keep | Fallback/admin | "cek context saya sehat gak?" | Low | Keep |
| `/actions` | Action inbox fallback | keep | Admin/fallback to inspect queue | "apa action pending saya?" | Low | Keep as fallback only |
| `/daily` | Daily planner read | consolidate_to_natural_language | Natural flow already supports daily action/focus | "buat action hari ini" | Low | Hide from primary help |
| `/memory` | Memory read surface | hide_from_help | Internal/fallback only | "riwayat/progress saya apa?" | Medium (memory semantics confusion) | Keep available, hide |
| `/handoff` | Handoff rendering | consolidate_to_natural_language | NL handoff exists | "buat handoff codex dari accepted action" | Low | Hide detailed variants |
| `/today` | Daily summary | consolidate_to_natural_language | Overlaps NL daily/focus | "apa fokus saya sekarang?" | Low | Hide from primary help |
| `/brief` | Raw brief artifact | hide_from_help | Debug/fallback artifact read | "ringkas brief terbaru" | Low | Keep internal |
| `/opportunities` | Raw opportunity list | hide_from_help | Debug/fallback | "opportunity saya apa?" | Low | Keep internal |
| `/status` | Runtime/source status | keep | Ops fallback | "status runtime/source" | Low | Keep |
| `/ops` | VPS/runtime ops status | keep | Admin ops only | "ops runtime" | Medium | Keep admin-only |
| `/profile` | Personal profile summary | hide_from_help | Low-frequency fallback | "profile saya" | Low | Keep internal |
| `/insight` | Intelligence dashboard | hide_from_help | Non-core daily action UX | "insight terbaru apa?" | Low | Keep but de-emphasize |
| `/digest` | Digest artifact surface | hide_from_help | Non-core daily action UX | "digest AI terbaru" | Low | Keep but de-emphasize |
| `/update` | Pipeline run/update | safety_review | Operational trigger | "update pipeline" (admin only) | Medium (resource/side effects) | Keep admin, not promoted |
| `/promote-memory` | Suggest promotion targets | safety_review | Memory-adjacent flow | "saran promosi memory" | Medium | Keep hidden/admin |
| `/draft-context-update` | Build controlled draft | safety_review | Drafting mutation-oriented plan | "buat draft update context" | Medium/High | Keep hidden/admin |
| `/preview-context-update` | Preview draft apply plan | safety_review | Mutation-adjacent preview | "preview draft update context" | Medium/High | Keep hidden/admin |
| `/apply-context-update CONFIRM` | Applies controlled draft | safety_review | Writes files | No direct NL replacement in normal UX | High | Keep internal only; never primary UX |
| `/draft` | Phase4 draft boundary surface | remove_later | Superseded by Phase5 conversational loop for normal users | "buat action hari ini" / "buat handoff..." | Low | Keep for compatibility, remove later |

## MCP Tool Audit Summary

See `runtime/assistant/contracts/paos-mcp.md` classification matrix for:
- `read_only`
- `draft_only`
- `local_state_write`
- `forbidden_or_blocked`

Key boundary reminders:
- `paos_memory_write` forbidden in normal Telegram/Hermes flow.
- `paos_action_state_transition` is local-state only.
- `accepted != executed` and no external apply path.
