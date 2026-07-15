---
name: truffile-cli
description: |
  Use the `truffile` CLI to manage Truffle devices and Truffle apps from the
  command line: scan/connect, create, validate, deploy, list installed apps,
  delete apps, and manage the Obsidian bridge app. Use `truffile-agent` for
  persistent agent work and `truffile-infer` for raw model inference.
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

After onboarding, ask the user for the User ID from Symphony **Settings >
About** if they have not already provided it. `truffile connect` uses that User
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

### Deploy a Local App Directory

```bash
truffile deploy ./apps/my-app
truffile deploy ./apps/my-app --dry-run
truffile deploy ./apps/my-app --json --non-interactive --replace
truffile deploy ./apps/my-app --interactive
```

Use `--dry-run` before a risky deploy. Use `--interactive` only for debugging
inside the build container before finalizing.

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

- Current CLI deploy step types are `bash`, `files`, `text`, `oauth`, and
  `welcome`.
- `vnc` steps are rejected by `truffile validate`; browser/VNC apps are not
  supported through the current CLI flow.
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
