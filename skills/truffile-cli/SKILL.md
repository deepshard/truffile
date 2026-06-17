---
name: truffile-cli
description: |
  Use the `truffile` CLI to manage Truffle devices and Truffle apps from the
  command line: scan/connect, create, validate, deploy, list installed apps,
  list app-store apps, install app-store apps, update app-store apps, delete
  apps, and manage the Obsidian bridge app. Use `truffile-chat` for talking to
  the agent and `truffile-infer` for raw model inference.
---

# truffile CLI

Use this for Truffle device and app lifecycle work. For focused install, update, delete, or app-store inspection tasks, prefer `truffile-app-management`.

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

### List Store Apps

```bash
truffile list store
truffile list store --json
```

This lists app-store apps and indicates installed/update status when the
device can be queried.

### Install From Store

```bash
truffile install store notion
truffile install store exa --field EXA_API_KEY="$EXA_API_KEY" --no-interactive
truffile install store arxiv --field ARXIV_RESEARCH_INTERESTS="agents, llms" --no-interactive
truffile install store notion --json
```

Browser/VNC apps are intentionally rejected by bundle inspection. The CLI
prints a message telling the user to install those in Symphony Settings.

### Update From Store

```bash
truffile update store notion
truffile update store --all
truffile update store notion --json
```

If an update reaches an auth step, stop and report that the update needs
reauthentication in Settings.

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
- VNC/browser apps are not supported through CLI store install yet.
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
