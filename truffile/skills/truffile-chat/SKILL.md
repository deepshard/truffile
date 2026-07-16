---
name: truffile-chat
description: |
  Talk to the Truffle agent on a connected Truffle device using the
  `truffile chat` CLI without dropping into the interactive REPL. Use when the
  user wants to send a message to the agent, attach apps to a task, list
  installed apps or recent tasks, resume a previous task, or get the agent's
  response back as JSON for further processing. Everything is doable through
  CLI args — no interactive input is required.
---

# truffile chat (non-interactive)

`truffile chat` runs a conversation against the agent that lives on a
connected Truffle device. With no positional prompt and a TTY stdin it drops
into an interactive REPL, but **every feature is available through CLI flags**
so an agent can shell out to it without ever entering interactive mode.

## When to use this skill

Reach for `truffile chat` (rather than `truffile infer`) when:

- the user wants the **Truffle agent** (with its memory, task history, and
  attached apps) to do something — not just a raw model completion
- they want to attach a specific Truffle app to the task (Slack, Gmail,
  Notion, etc.) so the agent can use that app's tools
- they want to resume an existing task, list past tasks, or list installed apps
- they want a structured JSON response with task id, title, tool calls, and
  attached apps for follow-up scripting

If they just want a one-off model completion with no tools or memory, use the
sibling skill `truffile-infer` instead.

## One-shot mode triggers

`truffile chat` runs as a one-shot (no REPL, exit when done) if **any** of
these are present:

- a positional prompt: `truffile chat "send a slack message"`
- `--stdin` or stdin is piped from another command
- `--prompt-file path.txt`
- `--list-apps` or `--list-tasks`
- `--task-id <id>` (resume a specific task)
- `--resume-last` (resume the most recent task)

Otherwise it drops into the REPL.

## Output rules (very important for agents)

In one-shot mode:

- **stdout** is reserved for the agent's final response. In plain mode it is
  the agent text content only. In `--json` mode it is a structured object.
- **stderr** carries decoration: tool-call status, attached-app confirmations,
  error diagnostics, and (with `--show-thinking`) the agent's thinking
  summaries. Pass `--quiet` to silence stderr entirely.
- Exit code is `0` on success, `1` on error, `130` on Ctrl+C.
- JSON is compact by default. Thinking summaries and tool names are omitted
  unless requested, and response content is bounded by `--max-output-bytes`.

`--json` payload shape:

```json
{
  "schema_version": "1",
  "status": "ok",
  "task_id": "uuid-of-the-task",
  "title": "Generated task title",
  "device": "truffle-1234",
  "content": "the agent's final response text",
  "content_bytes": 39,
  "returned_bytes": 39,
  "truncated": false,
  "task_status": "ready",
  "run_state": "TASK_RUN_STATE_READY",
  "pending_user_response": false,
  "attached_apps": ["Slack", "Gmail"]
}
```

`pending_user_response: true` means the agent is waiting for a follow-up
message — call `truffile chat --task-id <id> "answer"` to continue.
Add `--include-thinking`, `--include-tools`, or `--full` only when that detail
is needed.

## Full flag reference

### Conversation
| Flag | What it does |
|---|---|
| `PROMPT...` (positional) | Joined with spaces and used as the user message |
| `--prompt-file PATH` | Read prompt from a file |
| `--stdin` | Force read prompt from stdin (auto-detected if piped) |

### Task targeting
| Flag | What it does |
|---|---|
| `--task-id ID` | Resume a specific task. With a prompt: send follow-up. Without: peek state |
| `--resume-last` | Resume the most recent task on the device |
| `--resume` | (REPL only) Open the interactive task picker |

### App attachment
| Flag | What it does |
|---|---|
| `--app NAME_OR_UUID` | Attach an app (repeatable). Matches by uuid → exact name → slug → substring |

### Discovery
| Flag | What it does |
|---|---|
| `--list-apps` | Print installed apps and exit (`slug<TAB>name<TAB>uuid` per line) |
| `--list-tasks [N]` | Print recent N tasks (default 15) and exit (`id<TAB>updated<TAB>title`) |

### Output
| Flag | What it does |
|---|---|
| `--json` | Emit a structured JSON object on stdout |
| `--show-thinking` | Include the agent's thinking summaries on stderr |
| `--include-thinking` | Include thinking summaries in JSON |
| `--include-tools` | Include tool names in JSON |
| `--full` | Include both thinking summaries and tool names in JSON |
| `--max-output-bytes N` | Bound returned UTF-8 content bytes (default 65536) |
| `--quiet`, `-q` | Suppress all stderr decoration |
| `--timeout SECONDS` | Stop waiting and interrupt a known task after this limit |

## Cookbook

### Send a basic message and capture the response
```bash
truffile chat --quiet "what tasks should I work on today?"
```
stdout is the agent's reply, nothing else.

### Pipe a prompt in
```bash
cat instructions.md | truffile chat --quiet
```

### Get a structured JSON response
```bash
truffile chat --quiet --json "summarize my recent unread emails" | jq -r .content
```
For follow-ups, you can also pull `task_id` out of the JSON:
```bash
TID=$(truffile chat --quiet --json "..." | jq -r .task_id)
truffile chat --quiet --task-id "$TID" "now categorize them by urgency"
```

### Attach an app and let the agent use its tools
```bash
truffile chat --quiet --app slack "send #general a heads-up that I'm out today"
```
App matching is forgiving — `slack`, `Slack`, `slack` slug, or the full uuid
all resolve to the same app. Repeat `--app` to attach more than one:
```bash
truffile chat --quiet --app slack --app gmail \
  "compare my last 5 slack DMs and unread emails, surface anything urgent"
```

### List installed apps
```bash
truffile chat --list-apps --quiet
# slack            Slack          87ff7123-f9b5-4175-8c98-25338b8cf64d
# google-(beta)    Google (Beta)  df98c737-ff53-401f-9ca7-1326ec8ca8ec
```

As JSON for scripting:
```bash
truffile chat --list-apps --json --quiet | jq '.apps[] | .name'
```

### List recent tasks
```bash
truffile chat --list-tasks 10 --quiet
# task_id<TAB>updated<TAB>title
```

As JSON:
```bash
truffile chat --list-tasks 5 --json --quiet \
  | jq '.tasks[] | {task_id, title, status, pending_user_response}'
```

### Resume the most recent task and add a follow-up
```bash
truffile chat --quiet --resume-last "tell me more about the second item"
```

### Resume a specific task by id
```bash
truffile chat --quiet --task-id 0c83cc07-4ee5-410f-8c0a-be8152644f24 \
  "what was the original question for this task?"
```

### Peek a task without sending a new message
```bash
truffile chat --quiet --json --task-id <id> | jq .content
```

Use `--full` only for explicit debugging:
```bash
truffile chat --quiet --json --full --task-id <id>
```

### Show what the agent was thinking on stderr
```bash
truffile chat --show-thinking "explain why my last deploy failed"
# stderr: --- thinking --- ... --- end thinking ---
# stdout: the final answer
```

### Read prompt from a file
```bash
truffile chat --quiet --prompt-file ./long-instructions.md
```

## Common patterns for agents

**Pattern: ask the agent and capture a clean string**
```bash
ANSWER=$(truffile chat --quiet "...")
```

**Pattern: capture both task id and response for chained follow-ups**
```bash
RESPONSE=$(truffile chat --quiet --json "...")
TID=$(echo "$RESPONSE" | jq -r .task_id)
TEXT=$(echo "$RESPONSE" | jq -r .content)
# later:
truffile chat --quiet --task-id "$TID" "follow-up question"
```

**Pattern: precondition check (does device have a slack app installed?)**
```bash
if truffile chat --list-apps --json --quiet | jq -e '.apps[] | select(.name == "Slack")' >/dev/null; then
  truffile chat --quiet --app slack "..."
fi
```

**Pattern: discover then attach**
```bash
APP_NAME=$(truffile chat --list-apps --quiet | head -1 | cut -f2)
truffile chat --quiet --app "$APP_NAME" "..."
```

## chat vs infer — when to use which

| Want this | Use |
|---|---|
| Run a model completion with no apps, memory, or task plumbing | `truffile infer` |
| Talk to the Truffle agent (with memory, app tools, task history) | `truffile chat` |
| Attach a specific Truffle app (Slack, Gmail, etc.) to a request | `truffile chat --app` |
| List installed Truffle apps | `truffile chat --list-apps` |
| Connect to an arbitrary MCP server | `truffile infer --mcp` |
| Resume a previous conversation | `truffile chat --task-id` or `--resume-last` |
| Get raw model JSON with usage stats | `truffile infer --json` |
| Get the agent's reply with task metadata | `truffile chat --json` |

## Gotchas

- **Inside a Truffle app container,** `truffile chat` auto-detects the host
  device via the runtime's env vars (`APP_ID`, `APP_SESSION_TOKEN`,
  `GRPC_ADDRESS`) and routes everything at the host firmware directly. No
  pairing, no onboarding, no device picker — just run the command. App
  attachment, task resume, JSON output, and `--list-apps`/`--list-tasks`
  all work the same way they do on a LAN client. See the `truffile-cli`
  skill's "Running inside a Truffle app container" section for the full
  contract.
- **No device connected in machine mode → structured failure.** Run
  `truffile doctor --json`, then onboard in Symphony and connect with the
  non-interactive command in the `truffile-cli` skill. Interactive mode can
  still walk a human through the same flow. Pairing requires the user to
  physically approve the session on the Truffle.
- **App matching is fuzzy.** `slack` matches `Slack`. If two app names overlap,
  the first match wins — use the uuid for absolute precision.
- **`--task-id` without a prompt does NOT send a message.** It just opens the
  task and dumps current state. Combine with `--json` to inspect, or with a
  prompt to send a follow-up.
- **`--resume-last` picks the most recently updated task,** which is usually
  the one the user was just looking at — but not always.
- **`--quiet` suppresses error explanations on stderr too.** Drop it during
  development if you want to see what's going wrong.
- **The agent on the device is stateful.** Sending a new message without
  `--task-id` or `--resume-last` always starts a fresh task — old conversation
  context is not carried over.
- **Tool calls are surfaced on stderr** in plain mode. In `--json` mode they
  appear in the `tool_calls` array. With `--quiet`, you only see them via the
  JSON payload.
