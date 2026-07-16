# 🍄‍🟫 Truffile

Python SDK/CLI for Truffle devices.

## Agent setup

Give this to Codex, Claude Code, or another coding agent from the workspace
where you want to use Truffile. Replace the placeholder with what you want to
do with your Truffle:

> Set up the latest Truffile in this workspace, then **<what you want to do with your Truffle>**. Follow the
> [installation guide](https://docs.truffle.net/sdk/installation). Run
> `truffile load all --json` and `truffile doctor --json`, then follow the
> copied skills. Continue through all work that does not need me. Ask only for
> Symphony onboarding or my User ID, approval on the physical Truffle,
> credentials, or confirmation before deployment or a destructive action.

How the pieces fit:

- Symphony onboards the Truffle and supplies the User ID used for pairing.
- Truffile gives a coding agent a local CLI and SDK for the device.
- `truffile chat` talks to the on-device agent, including its tasks and apps.
- `truffile infer` calls the raw on-device model and can test MCP servers.
- The user still approves pairing on the device and authorizes deployments or
  destructive actions.

## What It Does

- discovers and connects to your Truffle (`scan`, `connect`, `disconnect`)
- copies bundled agent resources into your workspace (`load`)
- diagnoses the local-to-device path (`doctor`)
- validates and deploys apps from `truffile.yaml` (`validate`, `deploy`)
- manages installed apps (`list apps`, `delete`)
- talks to the on-device agent (`chat`) or raw inference service (`infer`)

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
truffile --version
truffile load all --json
truffile doctor --json
truffile scan --json --non-interactive
truffile connect <device> --user-id <user-id> --json --non-interactive
truffile create <app-name> --path ./apps --json --non-interactive
truffile validate ./apps/<app-name> --json
truffile deploy ./apps/<app-name> --dry-run --json --non-interactive
truffile deploy ./apps/<app-name> --json --non-interactive
truffile list apps --json
truffile delete <app-name> --dry-run --json --non-interactive
truffile delete <app-name> --yes --json --non-interactive
truffile models --json
truffile chat --quiet --json "your request"
truffile infer --quiet --json "your prompt"
```

For a first connection, onboard the device in
[Symphony](https://docs.truffle.net/client/overview), copy the User ID from
Symphony Settings, run the `scan` and `connect` commands above, then approve
the new session on the Truffle. Installation and local validation do not
require a connected device.

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

## Development Loop

The supported app development loop is CLI-first:

```bash
truffile create my-app --path ./apps --json --non-interactive
truffile validate ./apps/my-app --json
truffile deploy ./apps/my-app --dry-run --json --non-interactive
truffile deploy ./apps/my-app --json --non-interactive
```

After deploy, use `truffile chat` to attach the app to a task and exercise its
tools with the on-device agent. Preview removal with `truffile delete <app>
--dry-run --json --non-interactive`; only add `--yes` after the user confirms.
