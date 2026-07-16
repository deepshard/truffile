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

## Agent workflow

1. Preserve the user's original goal; setup is a prerequisite, not the result.
2. Run `truffile --version`, `truffile load all --json`, and
   `truffile doctor --json` before guessing about state.
3. Prefer `--json --non-interactive` for commands that support them. Treat
   stdout as machine output and report the command's `code`, `message`, and
   any `next_action` when it fails.
4. Continue through local create and validation even when no device is paired.
5. Pause only for a human boundary: Symphony onboarding, User ID, physical
   device approval, credentials, deployment approval, or destructive action
   confirmation.

## Connection Assumptions

When running inside a Truffle app or agent container, assume the runtime has
already provided the session token in env. `truffile connect` should report
that the device is already connected. Do not ask the user for tokens.

For normal laptop use, the user must first onboard their Truffle through the
Symphony desktop client:

https://docs.truffle.net/client/overview

After onboarding, ask the user for the User ID from Symphony **Settings** if
they have not already provided it. `truffile connect` uses that User ID and
then the user must approve the new session on the Truffle device. Stored
credentials are reused after the first approval.

Useful checks:

```bash
truffile doctor --json
truffile scan --json --non-interactive
truffile connect truffle-1234 --user-id "$TRUFFLE_USER_ID" \
  --json --non-interactive --approval-timeout 120
truffile list devices --json
truffile list apps --json
```

`connect` can return discovery, authentication, or approval failures as
structured JSON. Pairing always requires the user to approve the new session
on the physical Truffle. Do not ask them to paste a session token.

## Core Commands

### Discover and Connect

```bash
truffile scan --json --non-interactive
truffile connect truffle-1234 --user-id "$TRUFFLE_USER_ID" \
  --json --non-interactive --approval-timeout 120
truffile list devices --json
truffile disconnect truffle-1234 --json
truffile disconnect all --json
```

Inside a container, `connect` is effectively a no-op success because the
session comes from env.

### Create and Validate an App

```bash
truffile load all --json
truffile create my-app --path ./apps --json --non-interactive
truffile validate ./apps/my-app --json
```

`truffile load all` copies bundled skills and example apps into
`./truffile/skills` and `./truffile/examples` so the agent can inspect them
directly in the current workspace. Use `truffile load skills` or
`truffile load examples` for only one resource group.

Run validation before deploy. Validation is local and does not need a device.

### Deploy a Local App Directory

```bash
truffile deploy ./apps/my-app --dry-run --json --non-interactive
truffile deploy ./apps/my-app --json --non-interactive
truffile deploy ./apps/my-app --json --non-interactive --replace
truffile deploy ./apps/my-app --interactive
```

Run `--dry-run` first. Deploy only when the user asked for deployment, and use
`--replace` only when they approved replacing the installed bundle. Use
`--interactive` only for debugging inside the build container.

### Delete Installed Apps

```bash
truffile list apps --json
truffile delete my-app --dry-run --json --non-interactive
truffile delete my-app --yes --json --non-interactive
```

Prefer deleting by app name, slug, or uuid. Numeric indices still work, but
they are less safe for agent workflows because app ordering can change. Never
add `--yes` until the user has confirmed the exact apps shown by `--dry-run`.

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

- Use `--json` when available for scripting. Successful payloads contain
  `schema_version` and `status: "ok"`; failures contain `status: "error"` plus
  stable `code`, `message`, and `retryable` fields. They include `next_action`
  when a concrete recovery command or human action is known.
- Keep stdout clean when feeding another command.
- Relay important command results to the user; they do not see shell output.
