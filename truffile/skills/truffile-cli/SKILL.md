---
name: truffile-cli
description: |
  Use the `truffile` CLI to manage Truffle devices and Truffle apps from the
  command line: scan/connect, create, validate, deploy, list installed apps,
  manage existing connections and permissions, delete apps, and manage the
  Obsidian bridge app. Use `truffile-convo` for
  the stateful on-device agent and `truffile-infer` for raw model inference.
---

# truffile CLI

Use this for Truffle device and app lifecycle work.

## Connection Assumptions

When running inside a Truffle app or agent container, assume the runtime has
already provided the session token in env. `truffile connect` should report
that the device is already connected. Do not ask the user for tokens.

For normal laptop use, the user must first onboard their Truffle through the
Symphony desktop client:

https://docs.truffle.net/client/overview

After onboarding, ask the user for the User ID from **Symphony > Settings** if
they have not already provided it. `truffile connect` uses that User
ID and then the user must approve the new session on the Truffle device.
Stored credentials are reused after the first approval.

Useful checks:

```bash
truffile connect truffle-1234
truffile list devices
truffile list apps
```

## Core Commands

### Discover and Connect

```bash
truffile scan
truffile connect truffle-1234 --user-id "$TRUFFLE_USER_ID"
truffile list devices
truffile disconnect truffle-1234
truffile disconnect all
```

Inside a container, `connect` is effectively a no-op success because the
session comes from env.

### Create and Validate an App

```bash
truffile load all
truffile create my-app --path ./apps
truffile validate ./apps/my-app
```

`truffile load all` copies bundled skills and example apps into
`./truffile/skills` and `./truffile/examples` so the agent can inspect them
directly in the current workspace. Use `truffile load skills` or
`truffile load examples` for only one resource group.

Run validation before deploy. Validation is local and does not need a device.
Normal validation checks bundle structure and basic metadata; run
`python -m compileall -q ./apps/my-app` separately for Python syntax. Firmware
performs full manifest and install-plan validation during deployment.

### Deploy a Local App Directory

```bash
truffile deploy ./apps/my-app
truffile deploy ./apps/my-app --dry-run
truffile deploy ./apps/my-app --json --non-interactive
truffile deploy ./apps/my-app --interactive
```

Use `--dry-run` before a risky deploy. Use `--interactive` only for debugging
inside the build container before finalizing.

Normal deploy uploads the original bundle to firmware's native installer, which
uses builder containers. Local validation/dry run is bundle preflight; firmware
performs full schema/plan validation. Current native manifests retain their
account scopes, connectors, resource files, base image, and resource profile.

For an installed bundle ID, choose explicitly:

```bash
truffile deploy ./apps/my-app --update
truffile deploy ./apps/my-app --replace
```

Update preserves accounts and settings. Replace runs fresh setup and resets
accounts, with confirmation (`--yes` for scripts). Both require the matching
PyFW developer-upload capability. Older firmware is rejected before mutation.
Never fall back to deleting an app when an update is unavailable.

`--legacy-builder` retains the older direct builder path for fresh app IDs.
`--interactive` opens that builder's debug shell; normal deployment already
prompts for sign-in. Legacy schema limits still apply to that explicit path.

### Connections and Permissions

```bash
truffile connections list Google
truffile connections add Google
truffile connections reconnect Google
truffile connections delete Google
truffile connections permissions Google read-only
truffile connections rename Google Work
```

Friendly app names and bundle IDs/UUIDs work. Omitting the account opens a
numbered picker. The rename example picks an account and names it Work. Exact
account aliases/UUIDs can be supplied before the new name or permission mode.
`default` also selects the default connection. Delete confirms the selected
account; `--yes` confirms explicitly for scripts. Never infer all accounts.

Permission modes are `default`, `read-only`, `read-write`, and `auto-review`.
The listing reports saved flags; default inherits device policy. Omitted
`--notes` preserves notes. Do not use the device-wide default setter as an
initial-install preference: it resets existing account overrides too.
New accounts inherit device policy. There is no atomic install-time permission
option in this CLI; apply account overrides after setup.

Use `--answers-file /private/answers.json` for install/add/reconnect form values.
Keep credentials outside the app source tree. The named answer file is excluded
from directory uploads. JSON/noninteractive mode never prompts and requires
exact account selection. OAuth/browser setup requires interactive sign-in;
URL callbacks must match state. A timeout/disconnect requests cancellation but
may have raced a commit: inspect the app before retrying.

### Delete Installed Apps

```bash
truffile list apps --json
truffile delete my-app
truffile delete 1
truffile delete 1 2 3
truffile delete all
```

Prefer deleting by app name, slug, or uuid. Numeric indices still work, but
they are less safe for agent workflows because app ordering can change.

### Manage Users And Convo

```bash
truffile users clear-other
truffile users clear-other --force --json
truffile convo reset
truffile convo reset --hard
truffile convo reset --hard --force
```

`users clear-other` deletes old users that are not associated with the current
authenticated account. Without `--force`, it prompts and shows the current
account's user ID and username first.

`convo reset` is a soft reset: it restarts the agent/runtime path and keeps
Convo history. `convo reset --hard` clears persisted Convo nodes, threads, and
runtime state, then recreates core threads. Use `--force` only when the user
has already explicitly approved the hard reset.

### Obsidian

Obsidian has a special local bridge flow:

```bash
truffile obsidian attach --vault /path/to/vault
truffile obsidian status
truffile obsidian test
truffile obsidian deploy
```

`truffile obsidian deploy` starts/probes the local bridge, stages the Obsidian
app, injects bridge env, and deploys without asking for bridge URL/token again.

## App Authoring Notes

- Normal deploy delegates step execution and semantic validation to firmware.
- Text/password, OAuth, and browser/VNC cards are presented by the CLI; actual
  support depends on the device installer version and provider plan.
- The explicit legacy builder still supports only its older step subset.
- Use `truffile.app_runtime` imports in app code.
- Read-only tools should use MCP annotations, for example:

```python
ToolSpec(
    name="search_items",
    description="Search items.",
    icon="magnifying-glass",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
```

## Output Habits

- Use `--json` when available for scripting.
- Keep stdout clean when feeding another command.
- Relay important command results to the user; they do not see shell output.
