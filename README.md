# 🍄‍🟫 Truffile

Python SDK/CLI for Truffle devices.

## What It Does

- discovers and connects to your Truffle (`scan`, `connect`, `disconnect`)
- copies bundled agent resources into your workspace (`load`)
- validates and deploys apps from `truffile.yaml` (`validate`, `deploy`)
- installs and updates apps, adds or reconnects accounts, and manages permissions
  (`deploy`, `list apps`, `connections`, `delete`)
- talks to the on-device agent (`convo`) or inference directly (`models`, `infer`)

See [native installation and account management](NATIVE_INSTALL.md) for the
current workflow and firmware requirements. [The SDK audit](SDK_AUDIT.md) records
the original failures and follow-up scope.

## Start making apps

Use Python 3.12 or newer:

```bash
python -m pip install --upgrade truffile
truffile connect 6272
truffile load all
truffile create my-app --path ./apps
truffile validate ./apps/my-app
truffile deploy ./apps/my-app
```

For first-time pairing, enter your User ID from Symphony Settings and approve
the session on the device. The CLI reuses the saved session afterward.

The manifest defines app identity, foreground tools or a remote MCP connector,
optional background work, installation steps, and account setup. Normal deploy
passes it to firmware's native installer and builders. Use install-scoped steps
for shared code and connection-scoped steps for account credentials.

Read the [app-building guide](https://docs.truffle.net/sdk/building-apps),
[account and authentication guide](https://docs.truffle.net/sdk/accounts), and
[deployment guide](NATIVE_INSTALL.md). The exported skills under
`./truffile/skills/` teach coding agents the same workflow. Bundled examples
include older process-based recipes; use the native account guide for new
multi-account integrations.

## App Types and Runtime Model

Apps can be:

- foreground (`fg`): exposes MCP tools the agent can call during requests and conversations
- background (`bg`): runs on schedule and emits context for proactivity, enabling the device to trigger actions and write/update memory
- both (`fg` + `bg`): one app package can provide MCP tools and scheduled context emission

How to think about it:

- FG path is tool-serving: app process is used as a callable capability surface (MCP)
- BG path is context/proactivity: scheduled runs feed the proactive agent with fresh signals
- Proactivity can take actions and persist memory based on BG outputs

In practice:

- use `fg` when you need direct tool invocation from agent requests
- use `bg` when you need periodic monitoring, summaries, or event-driven context
- use `both` when the same app should both expose tools and continuously feed proactivity/memory

## Core Commands

```bash
truffile scan
truffile connect 6272
truffile create [app_name]
truffile load all
truffile validate [app_dir]
truffile deploy [app_dir]
truffile deploy --dry-run [app_dir]
truffile list apps --json
truffile connections list <app-uuid-or-bundle-id> --json
truffile delete <app-name>
truffile models
truffile convo
```

`truffile create` scaffolds a hybrid app starter with:
- `truffile.yaml` (foreground + background process config)
- copy-file steps for generated `*_foreground.py` and `*_background.py`
- `icon.png` copied from the package's bundled stock icon (deploy requires an icon)

`truffile load all` copies bundled agent-readable resources into your current
workspace:

- `./truffile/skills/` for CLI/Convo/infer/app-creation skills
- `./truffile/examples/` for bundled example apps such as ArXiv, Exa, Notion,
  Obsidian, Viator, WHOOP, and Home Assistant

Use `truffile load skills` or `truffile load examples` to copy only one group.

## Native installation and account management

Normal deployment packages the app and uses firmware's native installer and
builder. The original manifest is preserved, including accounts, connection
credentials, connectors, resources, and base/resource choices.

```bash
truffile deploy ./my-app
truffile deploy ./my-app --update
truffile deploy ./my-app --replace
truffile connections list Google
truffile connections add Google
truffile connections reconnect Google
truffile connections delete Google
truffile connections permissions Google read-only
```

`--update` preserves accounts and settings. `--replace` runs fresh setup and
resets accounts after confirmation. Both require firmware with developer-upload support;
the CLI checks support before requesting a mutation. Normal deploy refuses an
existing bundle ID until you choose one of those modes.

Friendly names and exact IDs both work. Omitting an account opens a terminal
picker; scripts must select explicitly. JSON/noninteractive commands never
prompt. Use `--answers-file` for scripted text/API-key setup, and interactive
mode for browser sign-in. Password values are hidden.

`validate` and `deploy --dry-run` perform bundle preflight; firmware validates
full manifest semantics. `--legacy-builder` retains the old direct builder path
and its schema validator. `--interactive` opens that legacy builder's debug
shell; it is not required for ordinary setup prompts.

See [the complete workflow](NATIVE_INSTALL.md) for account selection, permission
modes, OAuth, packaging rules, cancellation, and test coverage. The background
starter remains a placeholder that an app author needs to implement.

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
`/<app>` sends and interactive `/apps` are unavailable. Use
`truffile convo --list-apps` or `truffile list apps` for discovery only. No app
is attached to or restricted for a chat. Setup/OAuth/action cards are reported
as interaction required and must be completed in a supported client in v1.

## Inference Interfaces

Direct IF2:
- list models: `GET /if2/v1/models`
- chat completions: `POST /if2/v1/chat/completions`

CLI wrappers:
- `truffile models`
- `truffile infer` (streaming by default)

## Generated proto staging

The repo-root `truffle/` generated package and `scripts/` directory are
deliberately gitignored and are not vendored in Git. A published `truffile`
wheel already contains its generated bindings, so normal users only need:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install truffile
.venv/bin/python -c \
  'from truffile.transport.client import TruffleClient; print("ok")'
.venv/bin/truffile convo --help
```

For an editable install or local wheel build from a source checkout, first
copy the matching generated Python package from `pyfw`. Set `PYFW_CHECKOUT` to
that checkout's absolute path; in the standard workspace layout it is the
directory two levels above this repository.

```bash
PYFW_CHECKOUT=/absolute/path/to/pyfw
test -f "$PYFW_CHECKOUT/python/truffle/os/convo_pb2.py"
test -f "$PYFW_CHECKOUT/python/truffle/os/notification_pb2.py"
cp -a "$PYFW_CHECKOUT/python/truffle" ./truffle
```

The staged `truffle/` tree stays ignored. Do not add it to Git. When producing
a distributable wheel, record the exact source revision used to generate the
bindings:

```bash
cp "$PYFW_CHECKOUT/protos.sha" truffle/PROTOCOL_SHA
```

`PROTOCOL_SHA` identifies the protocol repository revision, not the PyFW
revision. The release workflow also stages `truffile/app_runtime` from PyFW
and writes `truffile/BUILD_INFO.json` with `pyfw_sha`, `truffile_sha`, and
`protocol_sha`. Source checkouts need that matching runtime staged too:

```bash
cp -a "$PYFW_CHECKOUT/python/app_runtime" ./truffile/app_runtime
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

## Editable install and wheel verification

Start from a clean source clone and stage the generated package as described
above. An editable install imports that ignored tree in place:

```bash
python3.12 -m venv /tmp/truffile-convo-clean
/tmp/truffile-convo-clean/bin/python -m pip install -e .
/tmp/truffile-convo-clean/bin/python -c \
  'from truffile.transport.client import TruffleClient; print("ok")'
/tmp/truffile-convo-clean/bin/truffile convo --help
```

For a distributable wheel, first write `truffle/PROTOCOL_SHA`, then build and
inspect the wheel. The wheel embeds the staged `truffle` package, including
`.pyi` files and `PROTOCOL_SHA`, and is self-contained after installation.

```bash
cp "$PYFW_CHECKOUT/protos.sha" truffle/PROTOCOL_SHA
/tmp/truffile-convo-clean/bin/python -m pip wheel --no-deps -w /tmp/truffile-wheel .
TRUFFILE_WHEEL="$(find /tmp/truffile-wheel -maxdepth 1 -name 'truffile-*.whl' -print -quit)"
/tmp/truffile-convo-clean/bin/python -m zipfile -l "$TRUFFILE_WHEEL" \
  | grep -E 'truffle/os/(convo|notification)_pb2\.(py|pyi)|truffle/PROTOCOL_SHA'

python3.12 -m venv /tmp/truffile-convo-wheel
/tmp/truffile-convo-wheel/bin/python -m pip install "$TRUFFILE_WHEEL"
/tmp/truffile-convo-wheel/bin/python -c \
  'from truffile.transport.client import TruffleClient; print("ok")'
/tmp/truffile-convo-wheel/bin/truffile convo --help
```

## Convo acceptance sequence

With an already approved device session, use this text-only sequence. It does
not create a new pairing or print credentials:

```bash
truffile convo --list-threads 5 --json --quiet

OPENING="$(truffile convo --new --rename "Convo acceptance" \
  --json --quiet --timeout 120 "Reply with the single word ready")"
THREAD_ID="$(printf '%s' "$OPENING" | python -c \
  'import json, sys; print(json.load(sys.stdin)["thread_id"])')"

truffile convo --thread-id "$THREAD_ID" --history --json --quiet
truffile convo --thread-id "$THREAD_ID" --json --quiet --timeout 120 \
  "Follow up with the single word complete"
truffile convo --thread-id "$THREAD_ID" --interrupt --json --quiet
```

Run each later command only if the opening command exits successfully. For the
manual streaming-interruption check, run `truffile convo --resume`, choose the
acceptance thread, send a request that takes long enough to stream, and press
**Esc** or **Ctrl+C**. Confirm the request is interrupted and the REPL remains
usable.
