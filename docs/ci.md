# CI operations

RockyRoad CI uses GitHub-hosted `ubuntu-latest` runners and the canonical
`scripts/verify` gate. Public repositories must not register persistent
self-hosted runners.

## Trust boundary

Actions are pinned to full commit SHAs, the workflow token has read-only
contents permission, checkout does not persist its token, and no application or
repository secrets are supplied to the job. CI runs on pushes to `main` and
manual dispatches. Do not add a `pull_request` trigger that executes untrusted
workflow changes without review.

## Dispatch

A successful push to `main` starts CI automatically. A maintainer can also use
the workflow's **Run workflow** control. Local completion remains
`scripts/verify`.
