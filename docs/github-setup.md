# GitHub setup checklist

One-time manual configuration needed on github.com before the automated pipeline runs end-to-end. Required on the canonical repo before P5 ships; forks need the same steps to run their own preset.

The workflows (`refresh.yml` for P5, `pages.yml` for P7) cannot do these steps on their own — they have to be done in the web UI (or via `gh` CLI) before the first run.

---

## 0. Email privacy (before the first `git push`)

GitHub blocks pushes with `GH007: Your push would publish a private email address` if (a) **Settings → Emails → "Keep my email addresses private"** is on AND (b) your commits' author email is your real address rather than the noreply alias. Both are the default for accounts created in recent years, so this trips most forkers on their first push.

Two clean fixes:

1. **Use the noreply alias** (recommended — keeps your real email out of the public commit history forever):

   ```bash
   # 1. Find your noreply alias: <user-id>+<login>@users.noreply.github.com
   gh api /user --jq '"\(.id)+\(.login)@users.noreply.github.com"'

   # 2. Lock new commits in *this* repo to that alias (local config, not global):
   git config user.email "<id>+<login>@users.noreply.github.com"

   # 3. Rewrite existing commits' author + committer email (one-shot, before push):
   git filter-branch -f --env-filter '
     if [ "$GIT_AUTHOR_EMAIL" = "your.real@email.com" ]; then
       export GIT_AUTHOR_EMAIL="<id>+<login>@users.noreply.github.com"
     fi
     if [ "$GIT_COMMITTER_EMAIL" = "your.real@email.com" ]; then
       export GIT_COMMITTER_EMAIL="<id>+<login>@users.noreply.github.com"
     fi
   ' -- --all
   ```

   `filter-branch` rewrites every reachable commit in seconds — safe pre-push since nothing is on the remote yet. After the rewrite, `git push -u origin main` succeeds. The `refs/original/refs/heads/*` backup refs left by `filter-branch` can be deleted once the push lands.

2. **Toggle the protection off** at `https://github.com/settings/emails` (uncheck "Block command line pushes that expose my email"). Faster, but your real email lands in the public commit history of every prior commit, permanently.

Forks that originate from an already-public repo don't need this step — the upstream history is already noreply-aliased.

---

## 1. Repository secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Required? | Used by | Notes |
|---|---|---|---|
| `ADZUNA_APP_ID` | Optional* | `src/jobpipe/sources/adzuna.py` | Free tier via [developer.adzuna.com](https://developer.adzuna.com/). The Adzuna adapter no-ops gracefully when absent, but you lose Eurozone breadth. |
| `ADZUNA_APP_KEY` | Optional* | `src/jobpipe/sources/adzuna.py` | Same. |

\* "Optional" = the run still succeeds without them; the Adzuna source is skipped fail-isolated. ATS adapters (Greenhouse / Lever / Ashby / Personio) and benchmark adapters (CSO / Eurostat) are credential-free, so you get a partial dataset with no secrets at all.

`GITHUB_TOKEN` is auto-injected by Actions per run — do not create a PAT for it. LLM secrets are not used in v1 ([ADR-013](../DECISIONS.md#adr-013--hn-algolia--llm-client-descoped-from-v1)).

Verify after adding:

```bash
gh secret list
# expected: ADZUNA_APP_ID, ADZUNA_APP_KEY
```

---

## 2. Workflow permissions

**Settings → Actions → General → Workflow permissions**

- Select **Read and write permissions** (needed for `gh release upload` in `refresh.yml`).
- Leave "Allow GitHub Actions to create and approve pull requests" **off** — the pipeline never opens PRs.

**Settings → Actions → General → Fork pull request workflows from outside collaborators**

- Set to **Require approval for first-time contributors** — defence-in-depth so an unrelated fork PR cannot trigger a workflow with our secrets attached.

---

## 3. GitHub Pages

**Settings → Pages → Build and deployment**

- **Source: GitHub Actions** (not "Deploy from a branch").
- Leave **Custom domain** blank — the dashboard lives at `https://<owner>.github.io/jobmarket_analyzer/`.

Verify:

```bash
gh api repos/:owner/:repo/pages | jq '.build_type, .html_url'
# expected: "workflow", "https://<owner>.github.io/jobmarket_analyzer/"
```

This setting is required by `pages.yml` (lands in P7) which uses `actions/upload-pages-artifact` + `actions/deploy-pages`. See [ADR-016](../DECISIONS.md#adr-016--github-pages-deploy-via-actionsdeploy-pages-from-the-monorepo).

---

## 4. Code security

**Settings → Code security and analysis**

- **Secret scanning** → enabled.
- **Push protection** → enabled.
- **Dependabot alerts** → enabled.

These are free for public repos. They catch any future accidental secret-in-commit before it reaches the public history.

---

## 5. Environments (not required for v1)

We do not configure a `github-pages` environment with required reviewers or branch protection in v1. The deploy workflow runs without an explicit environment.

If you later want to harden the deploy path (e.g. require manual approval before each Pages deploy, or restrict to `main` only), create a `github-pages` environment, set its deployment branch to `main`, and reference it from `pages.yml` (`environment: github-pages`). That's a v1.1 concern.

---

## 6. First-run smoke check

After P5 lands and `refresh.yml` exists, manually trigger one run to confirm:

```bash
gh workflow run refresh.yml
gh run watch
```

Then verify:

```bash
gh release view latest                    # should list postings/*.parquet and benchmarks/*.parquet
gh release list --limit 5                 # should show "latest" plus the dated tag
```

After P7 lands and `pages.yml` exists, the first deploy happens automatically after a successful `refresh.yml`. Visit the URL shown by `gh api repos/:owner/:repo/pages`.
