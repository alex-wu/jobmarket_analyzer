# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities **privately**, not via public issues.

- Use [GitHub private vulnerability reporting](https://github.com/alex-wu/jobmarket_analyzer/security/advisories/new)
  (Security tab → "Report a vulnerability").
- If that form is unavailable, open a blank issue titled "security contact
  request" with **no details** and a maintainer will reach out privately.

Include: affected component (pipeline `src/jobpipe`, dashboard `site/`, or a
GitHub Actions workflow), reproduction steps, and impact.

## Disclosure process

1. Acknowledgement within **72 hours** of the report.
2. Triage and severity assessment within **7 days**.
3. Fix targeted within **30 days** for high/critical, **90 days** otherwise.
4. Coordinated disclosure: a GitHub Security Advisory is published once a fix
   is on `main`, crediting the reporter unless they prefer otherwise.

## Scope

- Weekly data pipeline (`src/jobpipe`) and its GitHub Actions workflows.
- Static dashboard deployed to GitHub Pages (`site/`).
- Release artifacts (`latest-*` and dated `data-*` parquet bundles).

Out of scope: vulnerabilities in upstream data providers (Adzuna), GitHub
itself, or third-party dependencies with no exploit path through this project
(report those upstream; Dependabot tracks advisories here).

## Supported versions

Only the `main` branch and the most recent release assets are supported.
Older dated releases are immutable snapshots and are not patched.

## Supply-chain controls

- Release assets are signed keyless via Sigstore cosign; each asset ships a
  `<asset>.sigstore.json` bundle. The signing identity is pinned to the
  `refresh` and `sign-releases-backfill` workflows on `main`. Verify with:

  ```sh
  cosign verify-blob \
    --bundle <asset>.sigstore.json \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity-regexp '^https://github\.com/alex-wu/jobmarket_analyzer/\.github/workflows/(refresh|sign-releases-backfill)\.yml@refs/heads/main$' \
    <asset>
  ```
- GitHub Actions are pinned to full commit SHAs; Dependabot keeps them current.
- CodeQL, OpenSSF Scorecard, actionlint and Dependabot alerts run continuously.
