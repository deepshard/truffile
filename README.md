# 🍄‍🟫 Truffile

Python SDK/CLI for Truffle devices.

## What It Does

- discovers and connects to your Truffle (`scan`, `connect`, `disconnect`)
- validates and deploys apps from `truffile.yaml` (`validate`, `deploy`)
- manages installed apps (`list apps`, `delete`)
- talks to inference directly (`models`, `chat`)
- exposes an OpenAI-compatible local proxy (`proxy`)

## Start making your Own Apps

- app schema and validation: `truffile/truffile/schema/app_config.py`
- schedule parsing: `truffile/truffile/schedule.py`
- deploy planning + builder flow: `truffile/truffile/deploy/builder.py`
- generated TruffleOS protos vendored in: `truffile/truffle/`
- examples:
  - `truffile/example-apps/kalshi`
  - `truffile/example-apps/reddit`

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
truffile validate [app_dir]
truffile deploy [app_dir]
truffile deploy --dry-run [app_dir]
truffile list apps
truffile delete
truffile models
truffile chat "hello"
truffile proxy --host 127.0.0.1 --port 8080
```

## Inference Interfaces

Direct IF2:
- list models: `GET /if2/v1/models`
- chat completions: `POST /if2/v1/chat/completions`

CLI wrappers:
- `truffile models`
- `truffile chat` (streaming by default)

## Proxy

`truffile proxy` serves OpenAI-compatible routes locally and forwards to device IF2:

- `GET /v1/models`
- `POST /v1/chat/completions`

Default local base URL:
- `http://127.0.0.1:8080/v1`

Reasoning behavior:
- default: proxy can inject reasoning into `content` as `<think>...</think>`
- `--no-think-tags`: keeps reasoning separate as `reasoning_content` in stream deltas

## Proto Sync

Refresh vendored protos from firmware repo:

```bash
./scripts/sync_protos.sh
```
