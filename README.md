# 🍄‍🟫 Truffile

Python SDK/CLI for Truffle devices.

## What It Does

- discovers and connects to your Truffle (`scan`, `connect`, `disconnect`)
- validates and deploys apps from `truffile.yaml` (`validate`, `deploy`)
- manages installed apps (`list apps`, `delete`)
- talks to inference directly (`models`, `chat`)

## Start making your Own Apps

- app schema and validation: `truffile/truffile/schema/app_config.py`
- schedule parsing: `truffile/truffile/schedule.py`
- deploy planning + builder flow: `truffile/truffile/deploy/builder.py`
- generated TruffleOS protos vendored in: `truffile/truffle/`
- app store examples:
  - `truffile/app-store/kalshi`
  - `truffile/app-store/reddit`

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
truffile validate [app_dir]
truffile deploy [app_dir]
truffile deploy --dry-run [app_dir]
truffile list apps
truffile delete
truffile models
truffile chat
```

`truffile create` scaffolds a hybrid app starter with:
- `truffile.yaml` (foreground + background process config)
- copy-file steps for generated `*_foreground.py` and `*_background.py`
- `icon.png` copied from `docs/Truffle.png` (deploy requires an icon)


In `truffile chat`, runtime controls are slash commands (not launch flags):

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
- `truffile chat` (streaming by default)

## Proto Sync

Refresh vendored protos from firmware repo:

```bash
./scripts/sync_protos.sh
```

## Contributors

Contributors are welcome to submit apps to the Truffle App Store.

To submit:
- open a PR with your app under the `app-store/` folder
- include a screen recording of your app in action

The Truffle team will deploy accepted apps to the App Store for everyone with Truffle to use and your name will be featured there!
There may be small changes needed to make the app run optimally, but most features and the credit will remain yours.
