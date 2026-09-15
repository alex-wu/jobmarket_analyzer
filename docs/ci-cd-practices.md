# CI/CD practices

Reference for how this repo's pipelines are wired. Distilled from the
2026-05-15 CI/CD cleanup. Future work should extend the pipeline along these lines.

## What's enabled

| Capability | Source | Verify |
|---|---|---|
| Lint + type + test (Python) | `.github/workflows/ci.yml` | `gh run list -w ci.yml --limit 1` |
| Pages build + smoke + deploy | `.github/workflows/pages.yml` | `gh run list -w pages.yml --limit 1` |
| Weekly data refresh + release (matrix per preset) | `.github/workflows/refresh.yml` | `gh run list -w refresh.yml --limit 1` |
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
- **Light branch protection.** Required status checks are `test` plus the two
  CodeQL jobs (`analyze (python)`, `analyze (javascript)`); the Pages deploy is
  *not* a required check. No review requirement (solo project). Linear history matches the
  squash-merge norm. `enforce_admins: false` keeps emergency-override
  available.
- **No SHA-pinning of actions yet.** Major-version tags (`@v6`) + Dependabot
  tracking is sufficient for a portfolio-scale repo (exception: `astral-sh/setup-uv`
  publishes no floating major tag, so it is pinned to an exact `vX.Y.Z`). Escalate to SHA pins
  when the OpenSSF Scorecard score drops or when going past `v1.0.0`.

## Workflow triggers

| Workflow | Triggers | Concurrency | Notes |
|---|---|---|---|
| `ci` | push to `main`, PR to `main` | `ci-${{ github.ref }}` cancel-in-progress | Required check |
| `pages` | push to `main` under `site/**` or the workflow file, `workflow_run` after `refresh`, `workflow_dispatch` | `pages` no-cancel | Deploy (not a required check) |
| `refresh` | cron `0 6 * * 1` (weekly Mon 06:00 UTC), `workflow_dispatch` | `refresh-${{ matrix.preset }}` no-cancel | Data ingest, matrix = literal preset list (no glob over `config/runs/`) |
| `codeql` | push to `main`, PR to `main`, cron `0 8 * * 1` | matrix per language | Findings → Security tab |
| `scorecard` | branch_protection_rule, push to `main`, cron `0 9 * * 1` | `scorecard` no-cancel | Score → scorecard.dev |
| `lint-workflows` | PR or push touching `.github/workflows/**` | `lint-workflows-${{ github.ref }}` cancel-in-progress | actionlint |
| `dependabot-automerge` | `pull_request` from `dependabot[bot]` | — | Patch + minor only |

Cron timing is staggered Monday 06/08/09 UTC so Dependabot fires first,
CodeQL runs against any post-Dependabot state, then Scorecard sees the
freshest workflow set. `refresh` shares the 06:00 Monday slot since the
pivot ([ADR-018](../DECISIONS.md#adr-018--weekly-cadence--multi-country-single-run))
— different workflow file, same hour — so weekly data freshness aligns
with the dependency-update cycle.

## Multi-preset parallelism (post-2026-05-17 pivot)

Per [ADR-019](../DECISIONS.md#adr-019--multi-preset-latest-preset_id-release-naming),
`refresh.yml` matrixes over a hand-maintained preset list (each entry must have a matching `config/runs/{preset}.yaml`; nothing globs the directory):

```yaml
strategy:
  matrix:
    preset: [data_analyst_eu]   # extend as new presets land
  fail-fast: false              # one preset's failure must not block others

concurrency:
  group: refresh-${{ matrix.preset }}
  cancel-in-progress: false
```

Per-preset concurrency group prevents same-preset races (two `data_analyst_eu`
runs cannot collide on `latest-data_analyst_eu`), while allowing cross-preset
parallelism. Release tag scheme: `latest-{preset_id}` (moving),
`data-{preset_id}-YYYY-MM-DD` (immutable archive).

Adding a preset: append `preset_id` to `strategy.matrix.preset`, push. Next
weekly cron (or `workflow_dispatch`) runs it. The dashboard side is NOT yet
automatic — `pages.yml` hardcodes `PRESET_ID: data_analyst_eu` and downloads
only that release, and `site/src/data/postings.parquet.js` pins the same
constant; both need un-hardcoding for a new preset to surface. Multi-preset
enumeration is queued per ADR-019.

## Checklist for adding a new workflow

1. `name:` matches the filename stem (e.g. `lint-workflows.yml` → `name: lint-workflows`).
2. `permissions:` block declared at workflow OR job level — default to `read-all` or `contents: read` and escalate only where needed.
3. `concurrency:` group set; cancel-in-progress for fast-feedback workflows, no-cancel for deploys + uploads.
4. `timeout-minutes:` on every job.
5. Actions pinned to a full commit SHA with a trailing `# vX.Y.Z` comment (`uses: actions/checkout@3d3c42e… # v7.0.1`). Dependabot bumps the SHA and the comment together.
6. Secrets via `${{ secrets.X }}`, never hardcoded. Reference `GITHUB_TOKEN` only for write actions; for read-only data, omit it.
7. Long-running shell blocks: `set -euo pipefail` at the top.
8. If touching `.github/workflows/**`, the `lint-workflows` job will gate it.

## Action version policy

- **Full commit SHA + version comment** for every action: `uses: owner/repo@<40-hex-sha> # vX.Y.Z`. Adopted 2026-09-15 for OpenSSF Scorecard Pinned-Dependencies (tag pins score 0; a tag can be moved, a SHA cannot). Dependabot (`github-actions` ecosystem) rewrites the SHA and the comment in one PR; auto-merge handles patch + minor.
- **No `@vN` / `@main` / `@latest`** — resolve a new action's SHA with `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha` and record the exact tag in the comment.
- `uv sync --frozen` (lockfile) and `npm install` (deliberately no lockfile, see `pages.yml`) are the remaining non-SHA installs; Scorecard flags the npm one. Accepted trade-off until the lockfile policy changes.

## Release signing

`refresh.yml` signs every staged asset with Sigstore cosign (keyless, OIDC
identity = the workflow) and uploads a `<asset>.sigstore.json` bundle next to
it. Scorecard Signed-Releases checks the 5 most recent releases, so a fresh
repo (or one with pre-signing releases still in the window) needs the manual
`sign-releases-backfill` workflow once. Verification recipe in `SECURITY.md`.

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
- `glob@10.5.0` ← framework (our direct `rimraf@6.x` brings `glob@13`, not this one)
- `whatwg-encoding@3.1.1` ← `jsdom@23.2.0` ← framework

Trace: `cd site && npm ls inflight glob whatwg-encoding`.

These will clear when Observable Framework upgrades its rollup-commonjs +
jsdom pins. Dependabot will open the PR. Not something to fix locally.
(Note: these are *not* in puppeteer's chain — bumping puppeteer does not
affect them.)

## Manual setup (one-time)

- **Pages source** = "GitHub Actions" — set in repo Settings → Pages.
- **Branch protection** — applied via `gh api` (one-time; see [docs/github-setup.md](github-setup.md)).
- **`delete_branch_on_merge`** — `gh repo edit --delete-branch-on-merge`.

All other config (Dependabot, CodeQL, Scorecard, auto-merge, actionlint) is
declared in-repo and picks up automatically once merged to `main`.
