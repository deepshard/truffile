---
name: truffile-convo
description: |
  Drive the on-device Truffle agent through `truffile convo` without entering
  the REPL. Use for new or existing Convo threads, fenced replies, history,
  rename, interrupt, listing, and machine-readable output.
---

# truffile convo

Use `truffile convo` for the stateful on-device agent. Use `truffile infer` for
raw model inference. With a TTY and no action/prompt, `truffile convo` opens the
REPL; prompts and action flags are non-interactive and exit when complete.

## Agent-safe defaults

- A prompt with no target creates a new side thread on first send.
- Use `--main` only when the user explicitly wants Main (thread `0`).
- Prefer `--json --quiet` for automation. Stdout is one JSON document.
- Use `--timeout SECONDS` when the caller needs a deadline. It is opt-in;
  timeout interrupts the thread and exits `124`.
- Successful replies exit `0`. Selection/usage errors, agent/runtime errors,
  interaction-required state, interruption, and a lost completion fence are
  nonzero. Never retry a fence-lost send automatically.

## Core commands

```bash
# New named side thread.
truffile convo --new --rename "QA debug" --json --quiet --timeout 120 \
  "Run a safe diagnostic and summarize it"

# Continue by exact name or decimal id.
truffile convo --thread "QA debug" --json --quiet "continue"
truffile convo --thread-id 123 --json --quiet "continue"

# Main is explicit.
truffile convo --main --json --quiet "message for Main"

# Read-only/action forms.
truffile convo --list-chats --json --quiet
truffile convo --thread-id 123 --history --json --quiet
truffile convo --thread-id 123 --rename "Release notes" --json --quiet
truffile convo --thread-id 123 --interrupt --json --quiet
```

Piped and file prompts are also supported:

```bash
cat instructions.md | truffile convo --json --quiet --timeout 120
truffile convo --prompt-file instructions.md --json --quiet --timeout 120
```

## JSON result

```json
{
  "task_id": "123",
  "thread_id": "123",
  "backend": "convo",
  "title": "QA debug",
  "device": "truffle-6272",
  "content": "...",
  "thinking": null,
  "tool_calls": null,
  "pending_user_response": false,
  "attached_apps": null,
  "status": "ok",
  "error": null,
  "interrupted": false,
  "timed_out": false
}
```

`task_id`, `--task-id`, `--list-tasks`, and `/tasks` are one-release aliases;
their values are decimal Convo thread IDs. Legacy Task UUIDs and histories are
not accepted or listed.

## Local hide and protocol gaps

`--hide THREAD` hides a side thread only in local truffile state, scoped to the
device and authenticated user. Restore it with `--restore THREAD` (use its
decimal id if it is hidden). Main and system threads cannot be hidden. This is
not server deletion.

Convo v1 has no per-thread app allowlist. `--app` and dynamic `/<app>` sends
fail explicitly; use `--list-apps` only for discovery. Setup/OAuth/action nodes
return an interaction-required result and must be completed in a supported
client.

## Chained follow-up

```bash
response="$(truffile convo --new --json --quiet --timeout 120 "first question")"
thread_id="$(printf '%s' "$response" | jq -r .thread_id)"
truffile convo --thread-id "$thread_id" --json --quiet --timeout 120 \
  "follow-up question"
```

Do not send the follow-up if the first command exited nonzero. In particular,
a completion-fence loss retains durable partial output but does not prove the
turn completed and must not trigger an automatic resend.
