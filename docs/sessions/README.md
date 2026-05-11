# Session logs

Per-session handover notes for future coders and Claude Code sessions. The goal: someone (human or agent) walking in cold should be able to read the latest log and immediately know what's done, what's blocked, what's next, and what landmines to avoid.

## Convention

- **One file per session** under `docs/sessions/YYYY-MM-DD-<short-slug>.md`.
  - `<short-slug>` describes the scope, e.g. `bootstrap-p0-p1`, `p2-normalise`, `p3-ats-adapters`, `p4-benchmarks-fixup`.
  - If a date already has a session, append `-2`, `-3`, etc.
- **The newest file is always the canonical handover.** Older files are historical and should not be edited except for typo fixes.
- **Each file is self-contained.** Don't assume the reader has read earlier sessions. Repeat the relevant context. Keep tight (≤ 600 lines).

## Template

Every session log has these top-level sections (in order):

1. **Premise** — what the user asked for in the session, condensed to bullets.
2. **Plan** — pointer to the plan file at `~/.claude/plans/...` plus an inline summary so the log stands alone.
3. **What landed** — concrete deliverables, grouped by phase or topic.
4. **Issues + resolutions** — surprises, dead ends, scope adjustments. Note the WHY so future sessions don't re-litigate.
5. **External sources consulted** — URLs from research / docs that informed decisions, so the next session knows where to look.
6. **Branch + commit state** — which branches exist, what's merged, what's pending.
7. **Handover** — explicit "next session starts here", verification still owed, and known pitfalls.

## Conventions for the writer

- **Token-efficient.** Bullet fragments OK. Code blocks for commit hashes, file paths, command snippets.
- **Be honest about pitfalls.** A "we tried X but had to back out because Y" entry is more valuable than glossing over the detour.
- **Link, don't duplicate.** Architectural decisions live in `DECISIONS.md`; phase progress in `README.md` and `CHANGELOG.md`; this folder captures the *narrative* and *context* a static doc can't.
- **Don't dump conversation transcripts.** Distill into actionable handover notes.

## Reading order for a new session

1. This file (you are here).
2. The newest log in `docs/sessions/`.
3. The relevant phase section of `README.md` and `DECISIONS.md`.
4. The latest `CHANGELOG.md` entry.
5. The plan file at `~/.claude/plans/...` if still present.
