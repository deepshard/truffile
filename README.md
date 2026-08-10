# 🍄‍🟫 Truffile

Python SDK/CLI for Truffle devices.

## What It Does

- discovers and connects to your Truffle (`scan`, `connect`, `disconnect`)
- copies bundled agent resources into your workspace (`load`)
- validates and deploys apps from `truffile.yaml` (`validate`, `deploy`)
- manages installed apps (`list apps`, `delete`)
- talks to the on-device agent (`convo`) or inference directly (`models`, `infer`)

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
truffile convo
```

`truffile create` scaffolds a hybrid app starter with:
- `truffile.yaml` (foreground + background process config)
- copy-file steps for generated `*_foreground.py` and `*_background.py`
- `icon.png` copied from `docs/Truffle.png` (deploy requires an icon)

`truffile load all` copies bundled agent-readable resources into your current
workspace:

- `./truffile/skills/` for CLI/chat/infer/app-creation skills
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


## Convo chat

`truffile convo` opens an interactive REPL backed only by the authenticated
user's Convo. It defaults to an unsent new side thread; the first message
creates that thread. Use `truffile convo --main` or `/main` to opt into Main.
`/new` always starts another unsent side thread.

Useful REPL commands include `/threads`, `/history`, `/rename <name>`,
`/interrupt`, `/hide`, `/restore`, `/main`, and `/new`. Main is thread `0`.
System/Bulletin threads, including thread `-1`, are not shown and cannot be
selected for chat.

The same command is first-class for scripts and agents:

```bash
# New side thread, wait for the completion fence, print JSON, then exit.
truffile convo --new --rename "QA debug" --json --timeout 120 \
  "Reply with a short device status summary"

# Follow up by exact thread name or decimal id.
truffile convo --thread "QA debug" --json "continue"
truffile convo --thread-id 123 --json "continue"

# Inspect/list/rename/interrupt without entering the REPL.
truffile convo --list-chats --json
truffile convo --thread-id 123 --history --json
truffile convo --thread-id 123 --rename "Release notes"
truffile convo --thread-id 123 --interrupt
```

One-shot mode writes the final text (or one JSON document with `--json`) to
stdout and exits nonzero for invalid selection, runtime/agent failure,
interaction-required state, interruption, lost completion fence, or timeout.
`--timeout` is opt-in; expiry interrupts the selected thread and exits `124`.
JSON includes canonical `thread_id` and `backend: "convo"`, plus the
one-release `task_id` compatibility key. The `--task-id`, `--list-tasks`, and
`/tasks` spellings remain aliases for one release and accept decimal Convo
thread IDs—not legacy Task UUIDs.

Old Task histories are intentionally not listed or migrated. Local hide is
reversible and device/user scoped: it never deletes a server thread. Per-chat
app restrictions do not exist in the Convo protocol, so `--app` and dynamic
`/<app>` sends are rejected explicitly; `/apps` and `--list-apps` remain
available. Setup/OAuth/action cards are reported as interaction required and
must be completed in a supported client in v1.

## Inference Interfaces

Direct IF2:
- list models: `GET /if2/v1/models`
- chat completions: `POST /if2/v1/chat/completions`

CLI wrappers:
- `truffile models`
- `truffile infer` (streaming by default)

## Proto Sync

The tracked `truffle.*_pb2` packages are pinned by `truffle/PROTOCOL_SHA`.
Refresh them from the generated Python tree and protocol repo:

```bash
./scripts/sync_protos.sh
```

## Development Loop

The supported app development loop is CLI-first:

```bash
truffile create my-app --path ./apps
truffile validate ./apps/my-app
truffile deploy --dry-run ./apps/my-app
truffile deploy ./apps/my-app
```

After deploy, use `truffile convo` to exercise the on-device agent. Convo v1
cannot enforce a per-thread app allowlist; inspect installed apps with
`truffile convo --list-apps`. Use `truffile delete` to remove test apps from the
connected device.

## Clean package verification

```bash
python3.12 -m venv /tmp/truffile-convo-clean
/tmp/truffile-convo-clean/bin/python -m pip install -e .
/tmp/truffile-convo-clean/bin/python -c \
  'from truffile.transport.client import TruffleClient; print("ok")'
/tmp/truffile-convo-clean/bin/truffile convo --help

/tmp/truffile-convo-clean/bin/python -m pip wheel --no-deps -w /tmp/truffile-wheel .
python3.12 -m venv /tmp/truffile-convo-wheel
/tmp/truffile-convo-wheel/bin/python -m pip install /tmp/truffile-wheel/truffile-*.whl
/tmp/truffile-convo-wheel/bin/truffile convo --help
```

For the owner device acceptance sequence, run
`scripts/smoke_convo_6272.sh` after connecting an already approved
`truffle-6272` session. The script uses safe text-only prompts and covers
list/new/rename/history/one-shot/interrupt; finish with the printed manual REPL
check for streaming interruption.
