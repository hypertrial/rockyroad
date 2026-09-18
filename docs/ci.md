# CI operations

RockyRoad uses one repository-scoped macOS ARM64 self-hosted runner because the
private repository's GitHub Free hosted-runner allowance is exhausted. The
workflow runs the canonical `scripts/verify` gate without paid runner minutes.

## Trust boundary

The runner is persistent and executes as the local macOS user. Workflow code is
therefore trusted code with that user's filesystem permissions; it is not a
sandbox. CI intentionally runs only on pushes to `main` and manual dispatches by
repository maintainers. Pull requests, including private forks, never dispatch
to this runner. Maintainers must review changes to workflows, dependency
manifests, install scripts, and test/build commands before merging them.

Actions are pinned to full commit SHAs, the workflow token has read-only
contents permission, checkout does not persist its token, and no application or
repository secrets are supplied to the job. Do not broaden the workflow to
`pull_request` unless the runner has first moved to an isolated, unprivileged
account or disposable VM with no personal credentials.

## Runner operation

The repository runner is named `rockyroad-mac-arm64` and has the labels
`self-hosted`, `macOS`, `ARM64`, and `rockyroad`. It is installed at
`~/.local/share/actions-runner/rockyroad` and starts as a LaunchAgent. Its logs
are under
`~/Library/Logs/actions.runner.hypertrial-rockyroad.rockyroad-mac-arm64`.

From the runner directory, inspect or control the service with:

```bash
./svc.sh status
./svc.sh start
./svc.sh stop
```

If a job remains queued, confirm that the Mac is awake, the service is running,
and the runner appears online under **Repository settings → Actions → Runners**.
The official runner updates itself automatically when GitHub requires a newer
compatible version. Check service logs and the runner page after an update.

## Dispatch and rollback

A successful push to `main` starts CI automatically. A maintainer can also use
the workflow's **Run workflow** control for a trusted revision.

To return to GitHub-hosted runners, replace the `runs-on` labels with the desired
hosted image and restore any platform-specific setup, then stop and uninstall
the local service with `./svc.sh stop` and `./svc.sh uninstall`. Remove the
runner registration in repository settings. Hosted execution may remain blocked
until billing or included minutes are available; the local verification command
remains `scripts/verify` throughout the rollback.
