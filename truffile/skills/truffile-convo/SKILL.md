---
name: truffile-convo
description: |
  Drive the stateful on-device Truffle agent through `truffile convo`. Use for
  one-shot prompts, Main or side-thread targeting, durable follow-ups, thread
  history and actions, local hide/restore, fenced completion, installed-app
  discovery, machine-readable JSON, and safe error handling without entering
  the interactive REPL.
---

# truffile convo

Use `truffile convo` for the stateful on-device agent. Use `truffile infer` for
raw model inference or deterministic local MCP testing.

## Operating rules

- Prefer one-shot mode for agent work. Supply a prompt or action flag so the
  command exits when it completes.
- Prefer `--json --quiet`. Parse stdout only after checking the exit code.
- Let a prompt with no target create a new side thread on first send.
- Select Main with `--main` only when the user explicitly requests Main.
- Reuse the returned decimal `thread_id` for follow-ups.
- Add `--timeout SECONDS` when the caller requires a deadline. Timeout is
  opt-in; expiry requests an interrupt and exits `124`.
- Never retry or resend automatically after exit `75`. A lost completion
  fence retains durable output but does not prove the original turn finished.
- Treat setup, OAuth, and action interaction results as incomplete. Ask the
  user to finish them in a supported client.

## Mode triggers

With a TTY and no prompt or action, `truffile convo` opens an interactive REPL
in an unsent side-thread draft. `truffile convo --main` also stays interactive.
Use `truffile convo --resume` to open the interactive thread picker at startup.

Any prompt, action, list flag, explicit non-Main target, or non-TTY stdin uses
one-shot mode and exits after the result.

## Prompt sources

| Input | Behavior |
|---|---|
| positional `PROMPT...` | Join words with spaces |
| `--prompt-file PATH` | Read UTF-8 prompt text from a file |
| `--stdin` | Read prompt text from stdin |
| piped stdin | Read automatically when no positional or file prompt exists |

Combine positional, file, and stdin sources when needed. Truffile joins their
non-empty contents with blank lines.

```bash
truffile convo --new --json --quiet --timeout 120 \
  "Run a safe diagnostic and summarize it"

cat instructions.md | truffile convo --stdin --json --quiet --timeout 120
truffile convo --prompt-file instructions.md --json --quiet --timeout 120
```

## Target flags

The target flags are mutually exclusive.

| Flag | Target |
|---|---|
| no target | New side-thread draft; first send creates the thread |
| `--new` | Explicit new side-thread draft |
| `--main` | Main, thread `0` |
| `--thread NAME_OR_ID` | Existing thread by exact case-insensitive title or decimal ID |
| `--thread-id ID` | Existing thread by decimal ID |
| `--resume-last` | Visible thread with the newest node |

Use a decimal ID when titles are ambiguous.

```bash
truffile convo --thread "QA debug" --json --quiet "continue"
truffile convo --thread-id 123 --json --quiet "continue"
truffile convo --resume-last --json --quiet "continue"
truffile convo --main --json --quiet "message for Main"
```

## Action and output flags

| Flag | Behavior |
|---|---|
| `--rename NAME` | Rename an existing thread, or rename a new thread after its first send |
| `--history` | Print selected-thread history; require `--thread`, `--thread-id`, `--main`, or `--resume-last` |
| `--interrupt` | Request interruption in the selected thread and exit |
| `--hide THREAD` | Hide a side thread in local Truffile state and exit |
| `--restore THREAD` | Restore a locally hidden side thread and exit |
| `--include-hidden` | Include locally hidden threads in lists and selection |
| `--list-chats [N]` | List up to `N` threads; default `15` |
| `--list-threads [N]` | Synonym for `--list-chats` |
| `--list-apps` | List installed apps for discovery only |
| `--json` | Emit one machine-readable JSON document on stdout |
| `--quiet`, `-q` | Suppress non-result diagnostics |
| `--show-thinking` | Emit durable thinking summaries on stderr in text mode |
| `--timeout SECONDS` | Set an opt-in settlement deadline greater than zero |

Use one terminal list/action flag per invocation. `--list-apps`,
`--restore`, `--hide`, `--list-chats`/`--list-threads`, and `--interrupt`
return without sending prompt text. Run `--history` by itself when using JSON;
combining it with a prompt or rename prints the history document before the
later result. Use `--rename NAME` without a prompt only after selecting an
existing thread; combining rename with a new prompt renames after the send.

```bash
truffile convo --list-threads 20 --json --quiet
truffile convo --list-threads 20 --include-hidden --json --quiet
truffile convo --thread-id 123 --history --json --quiet
truffile convo --thread-id 123 --rename "Release notes" --json --quiet
truffile convo --thread-id 123 --interrupt --json --quiet
truffile convo --hide 123 --json --quiet
truffile convo --restore 123 --json --quiet
truffile convo --list-apps --json --quiet
```

## Interactive commands

Use interactive mode only when a human needs the REPL.

| Command | Behavior |
|---|---|
| `/threads` | List and switch visible Convo threads |
| `/new` | Start an unsent side-thread draft |
| `/main` | Select Main explicitly |
| `/history` | Print selected-thread history |
| `/title` | Print the selected thread title |
| `/rename <name>` | Rename the selected thread |
| `/interrupt` | Interrupt work in the selected thread |
| `/hide [name\|id]` | Hide a side thread locally |
| `/restore [name\|id]` | Restore a locally hidden side thread |
| `/deploy <path>` | Deploy an app |
| `/delete app [name]` | Delete an installed app |
| `/create <name>` | Scaffold an app |
| `/devices` | List connected devices |
| `/exit` | Exit Convo |

`/tasks`, `/resume`, and `/switch` are one-release compatibility entries for
the same Convo thread picker. `/delete task` is a compatibility entry for
local hide, not server deletion.

## Thread and visibility model

- Treat Main as thread `0`.
- Treat a bare launch as an unsent side-thread draft, not Main.
- Expect the first send from a draft to create the side thread.
- Exclude system and Bulletin threads, including `-1`, from user selection.
- Keep local hide state scoped to the device and authenticated user.
- Never describe `--hide` or `/hide` as server deletion.
- Do not hide Main or a system thread.

The command uses only the authenticated user's Convo backend. Old `Task_*`
histories are not migrated or listed after the one-way cutover.

## Stdout and stderr

Without `--json`, write final response content to stdout. Write diagnostics,
text-mode errors, and thinking requested by `--show-thinking` to stderr.

With `--json`, expect exactly one JSON document on stdout. Add `--quiet` to
suppress non-result diagnostics. Do not parse stdout from a nonzero command as
a successful reply; inspect the error/status fields first.

## Turn-result JSON

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

Expect `thinking` and `tool_calls` to be arrays when present. Handle `status`
values `ok`, `error`, `interaction_required`, `interrupted`, `timeout`, and
`fence_lost`.

## List and action JSON

Thread listing returns `threads`, the one-release `tasks` alias with identical
rows, and `backend`:

```json
{
  "threads": [
    {
      "thread_id": "123",
      "task_id": "123",
      "title": "QA debug",
      "thread_kind": "NODE",
      "created": "2026-08-10T18:30:00+00:00",
      "updated": "2026-08-10T18:31:00+00:00",
      "latest_node_id": "456",
      "last_read_node_id": "456",
      "unread_count": 0,
      "has_unread": false,
      "hidden_local": false
    }
  ],
  "tasks": [
    {
      "thread_id": "123",
      "task_id": "123",
      "title": "QA debug",
      "thread_kind": "NODE",
      "created": "2026-08-10T18:30:00+00:00",
      "updated": "2026-08-10T18:31:00+00:00",
      "latest_node_id": "456",
      "last_read_node_id": "456",
      "unread_count": 0,
      "has_unread": false,
      "hidden_local": false
    }
  ],
  "backend": "convo"
}
```

History returns:

```json
{
  "history": [
    {
      "node_id": "456",
      "thread_id": "123",
      "kind": "ai",
      "content": "...",
      "thinking": [],
      "tool_calls": [],
      "created": "2026-08-10T18:31:00+00:00"
    }
  ],
  "backend": "convo"
}
```

Local hide and restore return, respectively:

```json
{"thread_id": "123", "hidden_local": true}
```

```json
{"thread_id": "123", "restored_local": true}
```

Rename returns `thread_id`, `title`, and `backend`. Interrupt returns
`thread_id` and `interrupted: true`. App listing returns `apps` rows with
`name`, `bundle_id`, and `uuid`. JSON errors contain `backend`, `device`,
`status`, and `error` when available.

## Exit-code contract

| Code | Meaning | Required handling |
|---|---|---|
| `0` | Success | Parse/use the result |
| `1` | Connection, authentication, runtime, or agent error | Report the error; do not assume a reply |
| `2` | Invalid input/selection or unsupported `--app` | Correct the invocation or target |
| `3` | Setup/OAuth/action interaction required | Ask the user to complete it in a supported client |
| `75` | Completion fence lost | Preserve output; never retry automatically |
| `124` | Opt-in timeout expired | Treat as timed out after interrupt request |
| `130` | Turn or process interrupted | Treat as interrupted, not successful |

## Compatibility and migration

Treat `task_id`, `--task-id`, `--list-tasks`, and `/tasks` as one-release
aliases carrying decimal Convo thread IDs. Never interpret them as legacy Task
UUIDs or backend access.

Expect a legacy UUID to fail before selection with:

```text
legacy Task chats are not available after the Convo cutover; --thread-id/--task-id requires a decimal Convo thread id
```

## Installed apps

Convo v1 has no per-thread app allowlist. `--app` and dynamic `/<app>` sends
fail explicitly. Interactive `/apps` is removed. Use `--list-apps` or
`truffile list apps` for discovery only.

Never claim that an app was attached to, selected for, or enforced on a Convo
thread. The agent may discover installed tools through normal routing.

## Safe chained follow-up

Check the first exit code before extracting `thread_id` or sending another
message:

```bash
response="$(truffile convo --new --json --quiet --timeout 120 "first question")" || exit $?
thread_id="$(printf '%s' "$response" | jq -r .thread_id)"
truffile convo --thread-id "$thread_id" --json --quiet --timeout 120 \
  "follow-up question"
```

Stop on any nonzero result. In particular, do not resend after timeout,
interruption, interaction-required state, or fence loss without explicit user
direction and a new safety decision.
