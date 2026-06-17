---
name: truffile-cli
description: |
  Use the `truffile` CLI to manage Truffle devices and Truffle apps from the
  command line: scan/connect, create, validate, deploy, list installed apps,
  delete apps, and manage the Obsidian bridge app. Use `truffile-chat` for
  talking to the agent and `truffile-infer` for raw model inference.
---

# truffile CLI

Use this for Truffle device and app lifecycle work.

## Connection Assumptions

When running inside a Truffle app or agent container, assume the runtime has
already provided the session token in env. `truffile connect` should report
that the device is already connected. Do not ask the user for tokens.

For normal laptop use, `truffile` may use stored device state or onboarding.
If a command needs a device and none is connected, let the CLI guide the user.

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
truffile connect truffle-1234
truffile list devices
truffile disconnect truffle-1234
truffile disconnect all
```

Inside a container, `connect` is effectively a no-op success because the
session comes from env.

### Create and Validate an App

```bash
truffile create my-app --path ./apps
truffile validate ./apps/my-app
```

Run validation before deploy. Validation is local and does not need a device.

### Deploy a Local App Directory

```bash
truffile deploy ./apps/my-app
truffile deploy ./apps/my-app --dry-run
truffile deploy ./apps/my-app --interactive
truffile deploy ./apps/my-app --shell
```

Use `--dry-run` before a risky deploy. Use `--shell` only for debugging.

### Delete Installed Apps

```bash
truffile list apps
truffile delete 1
truffile delete 1 2 3
truffile delete all
```

Indices come from `truffile list apps`; re-list immediately before deleting.

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

- Current manifest step types include `bash`, `files`, `text`, `oauth`, and
  `welcome`.
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
