# CI/CD practices

Reference for how this repo's pipelines are wired. Distilled from P9 cleanup
(2026-05-15). Future phases should extend the pipeline along these lines.

## What's enabled

| Capability | Source | Verify |
|---|---|---|
| Lint + type + test (Python) | `.github/workflows/ci.yml` | `gh run list -w ci.yml --limit 1` |
| Pages build + smoke + deploy | `.github/workflows/pages.yml` | `gh run list -w pages.yml --limit 1` |
| Daily data refresh + release | `.github/workflows/refresh.yml` | `gh run list -w refresh.yml --limit 1` |
| Workflow YAML lint | `.github/workflows/lint-workflows.yml` | path-filtered; runs on `.github/workflows/**` changes |
| CodeQL (Python + JS) | `.github/workflows/codeql.yml` | `gh api repos/alex-wu/jobmarket_analyzer/code-scanning/alerts` |
| OpenSSF Scorecard | `.github/workflows/scorecard.yml` | <https://scorecard.dev/viewer/?uri=github.com/alex-wu/jobmarket_analyzer> |
| Dependabot version updates | `.github/dependabot.yml` | Insights → Dependency graph → Dependabot |
| Dependabot security updates | repo Security settings (UI) | `gh api repos/alex-wu/jobmarket_analyzer --jq '.security_and_analysis.dependabot_security_updates'` |
| Secret scanning + push protection | repo Security settings (UI) | `gh api repos/alex-wu/jobmarket_analyzer --jq '.security_and_analysis'` |
| Auto-merge for Dependabot patch+minor | `.github/workflows/dependabot-automerge.yml` | next Dependabot PR auto-merges on green CI |
| Branch protection on `main` (status checks) | repo Branches settings (or `gh api`) | `gh api repos/alex-wu/jobmarket_analyzer/branches/main/protection` |

## Why these choices

- **Public repo → all free GHAS features apply.** CodeQL, secret scanning,
  Dependabot security alerts, Scorecard — all free, no licensing.
- **Grouped Dependabot updates.** Minor + patch land as ONE PR per ecosystem
  per week (~3 PRs/week baseline). Caps PR noise while keeping deps fresh.
  Major bumps come ungrouped because they need attention.
- **Auto-merge for patch + minor only.** Removes weekly toil for routine
  bumps. Majors and security alerts stay manual.
- **Light branch protection.** Required status checks (`test` + `build-and-deploy`)
  only; no review requirement (solo project). Linear history matches the
  squash-merge norm. `enforce_admins: false` keeps emergency-override
  available.
- **No SHA-pinning of actions yet.** Major-version tags (`@v6`) + Dependabot
  tracking is sufficient for a portfolio-scale repo. Escalate to SHA pins
  when the OpenSSF Scorecard score drops or when going past `v1.0.0`.

## Workflow triggers

| Workflow | Triggers | Concurrency | Notes |
|---|---|---|---|
| `ci` | push to `main`, PR to `main` | `ci-${{ github.ref }}` cancel-in-progress | Required check |
| `pages` | push to `main` under `site/**`, `workflow_run` after `refresh`, `workflow_dispatch` | `pages` no-cancel | Required check |
| `refresh` | cron `0 6 * * *`, `workflow_dispatch` | `refresh` no-cancel | Data ingest |
| `codeql` | push to `main`, PR to `main`, cron `0 8 * * 1` | matrix per language | Findings → Security tab |
| `scorecard` | branch_protection_rule, push to `main`, cron `0 9 * * 1` | `scorecard` no-cancel | Score → scorecard.dev |
| `lint-workflows` | PR or push touching `.github/workflows/**` | `lint-workflows-${{ github.ref }}` cancel-in-progress | actionlint |
| `dependabot-automerge` | `pull_request` from `dependabot[bot]` | — | Patch + minor only |

Cron timing is staggered Monday 06/08/09 UTC so Dependabot fires first,
CodeQL runs against any post-Dependabot state, then Scorecard sees the
freshest workflow set.

## Checklist for adding a new workflow

1. `name:` matches the filename stem (e.g. `lint-workflows.yml` → `name: lint-workflows`).
2. `permissions:` block declared at workflow OR job level — default to `read-all` or `contents: read` and escalate only where needed.
3. `concurrency:` group set; cancel-in-progress for fast-feedback workflows, no-cancel for deploys + uploads.
4. `timeout-minutes:` on every job.
5. Actions pinned to a major-version tag (`@v6`), not `@main` or `@latest`. Dependabot will keep them fresh.
6. Secrets via `${{ secrets.X }}`, never hardcoded. Reference `GITHUB_TOKEN` only for write actions; for read-only data, omit it.
7. Long-running shell blocks: `set -euo pipefail` at the top.
8. If touching `.github/workflows/**`, the `lint-workflows` job will gate it.

## Action version policy

- **Major tag (`@v6`)** for all `actions/*` + `github/*` + `ossf/*` + `astral-sh/*` actions. Dependabot opens a PR per major bump; auto-merge handles patch + minor.
- **No `@main` / no `@latest`** — unpinned actions are a supply-chain risk and a Scorecard penalty.
- **SHA pinning** is overkill at this scale. Revisit if:
  - OpenSSF Scorecard drops below 7
  - The project tags `v1.0.0` and starts to be reused externally
  - A third-party action is added (i.e. anything outside `actions/`, `github/`, `ossf/`, `astral-sh/`, `dependabot/`)

## When to escalate the security stack

| Trigger | Add |
|---|---|
| Scorecard score < 7 | Pin all actions to SHA (Dependabot still tracks via `# v6.0.0` comments) |
| Repo tagged `v1.0.0` | `zizmor` workflow audit (catches `pull_request_target` misuse, expression injection) |
| External contributors arrive | `required_pull_request_reviews: 1` in branch protection; CODEOWNERS file |
| Private fork sprouts | GitHub Advanced Security license (CodeQL + secret scanning are paid on private repos) |

## Known upstream warnings (non-blocking)

`npm install` in `site/` emits 4 deprecation warnings on a fresh checkout.
All chain off `@observablehq/framework@1.13.4`, not our direct deps:

- `inflight@1.0.6` ← `@rollup/plugin-commonjs@25.0.8` ← framework
- `glob@8.1.0` ← `@rollup/plugin-commonjs@25.0.8` ← framework
- `glob@10.5.0` ← `rimraf@5.0.10` + framework (deduped)
- `whatwg-encoding@3.1.1` ← `jsdom@23.2.0` ← framework

Trace: `cd site && npm ls inflight glob whatwg-encoding`.

These will clear when Observable Framework upgrades its rollup-commonjs +
jsdom pins. Dependabot will open the PR. Not something to fix locally.

The P7 handover doc misdiagnosed these as puppeteer's chain; bumping
puppeteer 23 → 24 cleared a `puppeteer-core@24.43.x` peer mismatch but
did not affect these 4. See P9 session log for the corrected diagnosis.

## Manual setup (one-time)

- **Pages source** = "GitHub Actions" — set in repo Settings → Pages.
- **Branch protection** — applied via `gh api` (one-time; see P9 plan for the exact PUT payload).
- **`delete_branch_on_merge`** — `gh repo edit --delete-branch-on-merge`.

All other config (Dependabot, CodeQL, Scorecard, auto-merge, actionlint) is
declared in-repo and picks up automatically once merged to `main`.
