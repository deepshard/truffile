---
name: truffile-app-management
description: |
  Manage installed Truffle apps from the command line using `truffile`: list
  app-store apps, install apps from the store, update one or all store apps,
  delete installed apps, and verify the final installed state. Use when the user
  asks to install, update, remove, uninstall, delete, or inspect Truffle apps.
---

# Truffle App Management

Use this skill for app lifecycle tasks on a connected Truffle device: list,
install, update, and delete.

Assume the session token is already available in env when running from an
agent/app container. `truffile connect` should show the device is already
connected; do not ask the user for tokens.

## Preflight

```bash
truffile connect truffle-1234
truffile list apps
```

For store-aware operations:

```bash
truffile list store
truffile list store --json
```

Use `--json` when scripting or when you need reliable parsing.

## Install From Store

Install by store app name, slug, or bundle id:

```bash
truffile install store notion
truffile install store exa --field EXA_API_KEY="$EXA_API_KEY" --no-interactive
truffile install store arxiv --field ARXIV_RESEARCH_INTERESTS="agents, llms" --no-interactive
truffile install store notion --json
```

Rules:

- Repeat `--field KEY=VALUE` for text-step fields.
- Use `--no-interactive` when an agent should fail instead of prompting.
- OAuth installs may print an auth URL and ask for the callback/code.
- Browser/VNC apps are rejected by CLI store install; tell the user to install
  those in Symphony Settings.

Verify after install:

```bash
truffile list apps
```

## Update Store Apps

Update one app:

```bash
truffile update store notion
truffile update store notion --json
```

Update every store-installed app with an available update:

```bash
truffile update store --all
truffile update store --all --json
```

Reauthentication rule: if update reaches an auth/text/VNC step that cannot run
safely as an update, stop and report:

```text
Update needs reauthentication. Please go to Settings to update this app.
```

Verify after update:

```bash
truffile list store
truffile list apps
```

## Delete Installed Apps

Always list apps immediately before deleting because indices are positional:

```bash
truffile list apps
```

Delete by index:

```bash
truffile delete 1
truffile delete 1 2 3
```

Delete everything only when the user explicitly asks:

```bash
truffile delete all
```

Rules:

- Re-list before deleting if anything changed.
- Prefer exact index deletion over interactive selection for agent workflows.
- Confirm before `delete all` unless the user explicitly requested a full wipe.
- Report what was removed and what remains.
