---
name: truffile-agent
description: |
  Use the Truffile CLI for persistent on-device agent work: start tasks,
  resume exact context across CLI invocations, attach apps, inspect status and
  logs, wait, interrupt, rename, and delete tasks. Use truffile-infer for raw
  stateless model inference.
---

# Truffile Agent

Use `run` for non-interactive work and bare `truffile` for interactive work.
A successful run returns a `task_id`; preserve it whenever later turns must
use the same context.

## Start and Resume

```bash
truffile run --quiet --json "analyze this problem"
truffile run --resume <task-id> --quiet --json "continue with the fix"
truffile run --last --quiet --json "continue"
```

Prefer an explicit task ID in automation because another process can update a
newer task.

Never drop `--resume` and retry as a new run after a resume error. Resume is
fail-closed: a missing task, a task that is not waiting for input, and a
timeout are distinct nonzero outcomes.

## Prompt and Device Inputs

```bash
truffile run --device truffle-1234 "prompt"
truffile run --prompt-file ./instructions.md
cat instructions.md | truffile run --stdin
```

Use `--timeout <seconds>` for bounded automation. Exit code 124 means timeout.

## Apps

Attach apps with exact names, unique slugs, or UUIDs:

```bash
truffile run --app whoop --app notion "prepare a health summary"
```

Ambiguous app substrings are rejected instead of selecting the first match.

## Task Operations

```bash
truffile task list --limit 15 --json
truffile task show <task-id> --json
truffile task status <task-id> --json
truffile task logs <task-id> --json
truffile task wait <task-id> --timeout 120 --json
truffile task interrupt <task-id> --json
truffile task rename <task-id> "descriptive name"
truffile task delete <task-id> --yes
```

Use `--yes` only when deletion is explicitly intended. Without it, deletion
will not proceed noninteractively.

## Output Contract

With `--json`, stdout contains one JSON object. Progress goes to stderr and is
suppressed by `--quiet`. Successful agent output includes `task_id`, `device`,
`operation`, `status`, `run_state`, and `content`. Errors include
`error.code` and `error.message` and return nonzero.

Use `run --ephemeral` only for a new task whose context must be deleted after
its result is returned. It cannot be combined with `--resume` or `--last`.
Normal runs persist by default.

## Interactive Use

```bash
truffile
truffile "start with this prompt"
truffile resume
truffile resume <task-id> "optional first prompt"
truffile resume --last
```

`truffile agent ...`, `truffile chat`, and `truffile shell` are temporary
compatibility routes. New scripts should use `run` and `task`; interactive
work should use bare `truffile` and `resume`.
