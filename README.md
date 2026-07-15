# 🍄‍🟫 Truffile

Python SDK/CLI for Truffle devices.

## What It Does

- discovers and connects to your Truffle (`scan`, `connect`, `disconnect`)
- copies bundled agent resources into your workspace (`load`)
- validates and deploys apps from `truffile.yaml` (`validate`, `deploy`)
- manages installed apps (`list apps`, `delete`)
- runs persistent agent tasks (`run`, `resume`, `task`)
- talks to inference directly (`models`, `infer`)

## Start making your Own Apps

- app schema and validation: `truffile/truffile/schema/app_config.py`
- schedule parsing: `truffile/truffile/schedule.py`
- deploy planning + builder flow: `truffile/truffile/deploy/builder.py`
- generated TruffleOS protos vendored in: `truffile/truffle/`
- bundled example apps live under `truffile/app-store/`
- bundled Codex skills live under `truffile/skills/`

`truffile.yaml` defines:
- metadata (`name`, `description`, `type`)
- process (`cmd`, `working_directory`, `environment`)
- files to upload
- optional run/build commands
- background schedule policy (for BG apps)

## App Types and Runtime Model

Apps can be:

- foreground (`fg`): exposes MCP tools that tasks/agents can call during active execution
- background (`bg`): runs on schedule and emits context for proactivity, enabling the device to trigger actions and write/update memory
- both (`fg` + `bg`): one app package can provide MCP tools and scheduled context emission

How to think about it:

- FG path is tool-serving: app process is used as a callable capability surface (MCP)
- BG path is context/proactivity: scheduled runs feed the proactive agent with fresh signals
- Proactivity can take actions and persist memory based on BG outputs

In practice:

- use `fg` when you need direct tool invocation from tasks
- use `bg` when you need periodic monitoring, summaries, or event-driven context
- use `both` when the same app should both expose tools and continuously feed proactivity/memory

## Core Commands

```bash
truffile scan
truffile connect <device>
truffile create [app_name]
truffile load all
truffile validate [app_dir]
truffile deploy [app_dir]
truffile deploy --dry-run [app_dir]
truffile list apps --json
truffile delete <app-name>
truffile models
truffile run "summarize my installed apps"
truffile task list
truffile infer "raw model prompt"
```

## Persistent Tasks

Tasks persist by default. Interaction mode and context selection are separate:
bare `truffile` is interactive, while `truffile run` is always
non-interactive. The returned `task_id` is the context handle for later runs.

```bash
# Start an interactive task, optionally with a first prompt.
truffile
truffile "Help me plan this release"

# Resume interactively. With no ID, open the task picker.
truffile resume
truffile resume <task-id> "Continue the release plan"
truffile resume --last

# Start new context non-interactively.
truffile run --json "Remember that the release color is cobalt"

# Continue exact context non-interactively.
truffile run --resume <task-id> --json "What is the release color?"

# Continue the most recently updated task non-interactively.
truffile run --last --json "Continue with the next step"
```

`run` without a context flag always starts a new task. `run --resume` and
`run --last` never silently create a replacement when context is missing or
not accepting input. Use `run --ephemeral` for a new result that should be
deleted immediately after completion; it cannot be combined with a resume
flag.

`run` accepts `--device`, `--json`, `--quiet`, and `--timeout`. Prompts can be
positional, read from `--prompt-file`, or read with `--stdin`; apps can be
attached with repeatable `--app` flags. Interactive `resume` accepts
`--device` and an optional first prompt.

### Task Management

```bash
truffile task list --limit 15 --json
truffile task show <task-id> --json
truffile task status <task-id> --json
truffile task logs <task-id> --json
truffile task wait <task-id> --timeout 120 --json
truffile task interrupt <task-id> --json
truffile task rename <task-id> "Release planning"
truffile task delete <task-id> --yes
```

Task lists are sorted newest-first and limited client-side. Destructive task
deletion requires confirmation, with `--yes` as the explicit noninteractive
form.

### Machine-Readable Contract

Successful `run` JSON includes at least:

```json
{
  "task_id": "...",
  "device": "truffle-1234",
  "operation": "run",
  "status": "waiting_for_user",
  "run_state": "TASK_RUN_STATE_READY",
  "content": "..."
}
```

JSON errors use an `error.code` and `error.message` and return nonzero. Stable
exit codes are `0` success, `1` execution error, `2` usage error, `3`
connection/authentication error, `4` not found, `5` state conflict, `124`
timeout, and `130` interruption.

The old `truffile agent ...`, `truffile chat`, and `truffile shell` forms
remain hidden compatibility routes for one release cycle. New automation
should use `run` and `task`; interactive work should use bare `truffile` and
`resume`.

`truffile create` scaffolds a hybrid app starter with:
- `truffile.yaml` (foreground + background process config)
- copy-file steps for generated `*_foreground.py` and `*_background.py`
- `icon.png` copied from `docs/Truffle.png` (deploy requires an icon)

`truffile load all` copies bundled agent-readable resources into your current
workspace:

- `./truffile/skills/` for CLI/agent/infer/app-creation skills
- `./truffile/examples/` for bundled example apps such as ArXiv, Exa, Notion,
  Obsidian, Viator, WHOOP, and Home Assistant

Use `truffile load skills` or `truffile load examples` to copy only one group.

## Obsidian Bridge Workflow

For a local Obsidian vault on your laptop, `truffile` can run a small host-side
bridge and deploy a bundled foreground app to the device:

```bash
truffile obsidian attach --vault ~/Documents/abd-vault
truffile obsidian serve
truffile obsidian deploy
```

Use `truffile obsidian status` to inspect the saved bridge configuration. The
bridge stores a scoped bearer token in the local `truffile` state file and the
bundled app uses that token to read, write, list, and search notes in the
configured vault.


In interactive `truffile`, runtime controls are slash commands:

- `/help` for all chat commands
- `/config` to show current chat config
- `/reasoning on|off`
- `/stream on|off`
- `/json on|off`
- `/tools on|off`
- `/max_tokens <int>`, `/temperature <float|off>`, `/top_p <float|off>`, `/max_rounds <int>`
- `/models` to switch model
- `/attach <path-or-url>` to attach an image for the next user message (local path or `http(s)` URL)
- `/system <text|clear>`
- `/mcp connect <http(s)://...>`, `/mcp tools`, `/mcp status`, `/mcp disconnect`

## Inference Interfaces

Direct IF2:
- list models: `GET /if2/v1/models`
- chat completions: `POST /if2/v1/chat/completions`

CLI wrappers:
- `truffile models`
- `truffile infer` (raw inference)
- `truffile run` (persistent on-device task)

## Proto Sync

Refresh the vendored protocol and app-runtime packages from an audited release
wheel:

```bash
python scripts/sync_generated_from_wheel.py path/to/truffile-X.Y.Z-py3-none-any.whl \
  --expected-sha256 <sha256>
```

The checked-in `generated-sources.json` records the current source wheel and
checksum. See `GENERATED_SOURCES.md` for the release procedure.

## Development Loop

The supported app development loop is CLI-first:

```bash
truffile create my-app --path ./apps
truffile validate ./apps/my-app
truffile deploy --dry-run ./apps/my-app
truffile deploy ./apps/my-app
```

After deploy, use `truffile run --app <name>` to attach the app to a task
and exercise its tools with the on-device agent. Use `truffile delete` to
remove test apps from the connected device.
