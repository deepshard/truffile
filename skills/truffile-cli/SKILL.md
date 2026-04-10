---
name: truffile-cli
description: |
  Use the `truffile` CLI to manage Truffle devices and the lifecycle of
  Truffle apps — scan for devices, pair with one, scaffold a new app,
  validate it, deploy it, list installed apps, and delete them. Use this
  skill whenever the user wants to build, ship, or manage Truffle apps from
  the command line. For talking to the agent on the device use the
  `truffile-chat` skill; for raw model inference use the `truffile-infer`
  skill.
---

# truffile cli (build, deploy, and manage)

This skill covers everything in the `truffile` CLI **except** the chat REPL
and raw model inference (those have their own skills, `truffile-chat` and
`truffile-infer`).

## When to use this skill

Reach for this skill when the user wants to:

- discover and pair with a Truffle device
- scaffold a new Truffle app
- validate an app's manifest and python before deploying
- deploy an app to a connected device
- list or delete apps installed on the device
- list connected devices or available models
- disconnect from a device

## Output discipline

Most of these commands print human-readable output to stdout with colored
decoration. They are not designed for piping in the same way `chat` and
`infer` are — but they are predictable: exit `0` on success, `1` on error,
`130` on Ctrl+C. Validation and deploy errors are written to stderr.

## First-run onboarding (important)

The CLI now ships with a first-run onboarding step. **The first time you run
any command that needs a device** (`chat`, `infer`, `deploy`, `delete`,
`models`, `list apps`), if no device is connected the CLI will:

1. Show a welcome banner
2. Ask for the user's truffle number (e.g. `1234`, normalized to `truffle-1234`)
3. Ask for their user id (offering the previously-stored one as a default)
4. Run `truffile connect <device> --user-id <id>` for them
5. Prompt them to **physically tap "approve" on the Truffle device screen**
6. Continue with the original command after success

This means an agent usually does **not** need to call `truffile connect`
manually — just run the actual command and let onboarding fire. Only call
`connect` explicitly when scripting non-interactive setups (CI, fresh install
automation), where you can pass `--user-id` to skip the prompt.

**Onboarding never fires inside a Truffle app container** — see the next
section.

## Running inside a Truffle app container

When `truffile` is invoked from inside a Truffle app container (FG or BG),
the CLI auto-detects the in-container context and **short-circuits all of
discovery, pairing, and onboarding**. The container is already holding a
full user session token on a gRPC channel that reaches the host firmware,
so there is nothing to set up — every command "just works" against the host
device the container is running on.

### How detection works

The CLI checks for three env vars at startup:

- `APP_ID` — the bundle id of the running app
- `APP_SESSION_TOKEN` — the installing user's session token
- `GRPC_ADDRESS` — the host firmware's gRPC address (typically `10.22.0.1:80`)

If all three are present, the CLI:

1. Probes the host firmware once (one `System_GetID` + one `System_GetInfo`
   call) to learn the device id, serial, firmware version, ip, mac, and
   timezone.
2. Injects a synthetic device into in-memory storage pointing at the host.
   **Nothing is persisted to disk.**
3. Marks that device as the active one for the rest of the CLI invocation.
4. Skips mDNS discovery entirely and routes every subsequent command at
   `10.22.0.1:80` (gRPC) or `http://10.22.0.1/if2/v1/...` (inference HTTP).

The probe runs once per CLI invocation and is cached. If it fails (firmware
momentarily down, envoy hiccup), the CLI falls back to a placeholder device
name and writes a one-line warning to stderr — the actual command you invoke
will surface the real error from the firmware.

### What changes inside a container

| Command | In-container behavior |
|---|---|
| `truffile scan` | Skips mDNS. Prints a single "DEVICES" block with the host device, its serial/ip/mac/firmware/timezone, and a `via: in-container short-circuit` line |
| `truffile connect [anything]` | Prints "Already connected to truffle-XXXX via in-container session" and exits 0. The device argument is ignored — there's nothing to pair with |
| `truffile disconnect [anything]` | No-op. Prints "disconnect is a no-op inside a Truffle app container" and exits 0. The session token comes from the runtime and lives for the container's lifetime |
| `truffile list devices` | Shows the synthetic host device as `(active)` |
| `truffile list apps` | Goes to the host firmware via gRPC with the env session token |
| `truffile deploy ./my-app` | Builds and deploys to the host — same as if you were on the LAN, but no pairing or device picker |
| `truffile delete N` | Same — removes apps from the host |
| `truffile models` | Lists models on the host via IF2 HTTP |
| `truffile create` / `truffile validate` | Pure local — unchanged |
| First-run onboarding | **Does not fire.** `last_used_device` is set by the synthetic injection, so the guard naturally short-circuits |

### When you'd actually use this

The point of in-container mode is to let an app-deployed agent (e.g. one
running inside a Truffle app's BG container) drive the host Truffle for
follow-up automation: enumerate installed apps, deploy a sibling app,
delete a stale app, send a chat message to the agent, run a quick
inference. From inside the container you can just type:

```bash
truffile list apps
truffile chat --quiet --json "summarize the last hour of slack"
truffile infer --quiet "..."
truffile deploy ./bundled-helper
```

…and they all hit the host firmware directly through the env-provided
session — no LAN, no mDNS, no prompts, no setup.

### Outside a container, nothing changes

If any of the three env vars is missing (which is the case on dev laptops
and any normal LAN client), the CLI behaves exactly as documented elsewhere
in this skill. The in-container path is purely additive and only fires when
all three vars are present. You can always check by running `env | grep -E
'^(APP_ID|APP_SESSION_TOKEN|GRPC_ADDRESS)='` from a shell — if it prints
nothing, you're not in container mode.

### Security note for contributors

This feature reuses the exact same handshake every running Truffle app
already uses today via the `app_runtime` package — same env contract, same
auth metadata wire format (`session` + `app-id` headers/metadata), same
gRPC methods. No firmware changes, no new RPCs, no new secrets. The
session token is read from `os.environ` at runtime, lives only in memory,
is never persisted to `state.json`, and is masked in any debug output.

## Command reference

### Device discovery and pairing

#### `truffile scan [--timeout SECONDS]`
Browse the local network via mDNS for Truffle devices. Default timeout 5s.
Lists discovered devices and lets the user pick one to connect to.
```bash
truffile scan
truffile scan --timeout 10
```

#### `truffile connect <device> [--user-id ID]`
Pair with a specific device by name. Without `--user-id`, prompts
interactively (with the stored id as a default if present). With `--user-id`,
runs non-interactively. The user still needs to **physically approve on the
Truffle screen**.
```bash
truffile connect truffle-1234
truffile connect truffle-1234 --user-id abc-user-id-from-recovery-codes
```
Once paired, a token is stored locally and the device becomes the active
"last used" device for future commands.

#### `truffile disconnect [device|all]`
Clear stored credentials. With no argument or `all`, clears every device.
With a device name, clears just that one.
```bash
truffile disconnect              # clears everything
truffile disconnect all          # same
truffile disconnect truffle-1234 # clears one device
```

#### `truffile list devices`
List the devices that have stored credentials, marking the active one.
```bash
truffile list devices
```

### App authoring

#### `truffile create [name] [--path PATH]`
Scaffold a new Truffle app directory containing `truffile.yaml`,
`<slug>_foreground.py`, `<slug>_background.py`, and a stock `icon.png`. If
`name` or `--path` is omitted, the command prompts interactively.
```bash
truffile create my-cool-app --path ./apps    # non-interactive
truffile create                              # interactive: prompts for both
```
The app is created at `<path>/<name>/`. The next step it suggests is
`truffile validate <path>`.

#### `truffile validate [path]`
Validate the truffile.yaml manifest, install steps, python files, and icon
in an app directory. Local-only (does not need a device). Reports warnings
and errors.
```bash
truffile validate                  # validate the current directory
truffile validate ./apps/my-app
```
Use this in iteration loops while building an app — fast feedback before
spending time on a real deploy.

### Deploy

#### `truffile deploy [path] [--dry-run] [--shell] [--interactive] [--no-finalize]`
Validate, build, upload, and install an app on the connected device. The
default path is the current directory. Walks through every install step,
runs the validator, and finalizes. Will trigger first-run onboarding if no
device is connected.

```bash
truffile deploy                            # deploy ./
truffile deploy ./apps/my-app              # deploy a specific dir
truffile deploy ./apps/my-app --dry-run    # validate + show plan, don't push
truffile deploy ./apps/my-app --interactive  # confirm at each step
truffile deploy ./apps/my-app --shell      # drop into a shell on the device
truffile deploy ./apps/my-app --no-finalize  # build and upload, skip finalize
```

| Flag | Purpose |
|---|---|
| `--dry-run` | Build the deploy plan, print it, do not contact the device |
| `--interactive` | Pause for confirmation between each install step |
| `--shell` | After deploy, drop into an interactive shell on the device |
| `--no-finalize` | Skip the final commit step (useful for incremental debugging) |

The typical iteration loop is:
```bash
truffile validate ./apps/my-app && truffile deploy ./apps/my-app
```

### Apps installed on the device

#### `truffile list apps`
List apps currently installed on the active device. Output is numbered so
indices line up with `truffile delete`.
```bash
truffile list apps
```

#### `truffile delete [selection ...]`
Delete one or more apps from the connected device. Accepts:
- nothing → drops into interactive picker
- `all` → deletes every installed app (asks confirmation first)
- numbers (space- or comma-separated) → deletes those by index
- piped stdin works too

```bash
truffile delete                # interactive picker
truffile delete all            # delete every app
truffile delete 1              # delete app #1
truffile delete 1 2 3          # delete apps 1, 2, 3
truffile delete 1, 2, 3        # commas also work
echo "all" | truffile delete   # piped
```
Bad input (out-of-range, non-numeric) falls back to the interactive picker.

### Models and misc

#### `truffile models`
List the inference models available on the active device. Same data as
`truffile infer --list-models` but in human-readable form.
```bash
truffile models
```

#### `truffile help`
Show the global welcome / help screen.
```bash
truffile help
```

## Typical workflows

### Workflow: brand-new user, first app
```bash
# 1. Scaffold the app
truffile create my-app --path ./apps

# 2. Edit ./apps/my-app/truffile.yaml and the python files...

# 3. Validate as you go
truffile validate ./apps/my-app

# 4. Deploy. First-run onboarding fires automatically here:
#    - asks for truffle number + user id
#    - runs `truffile connect` for you
#    - you tap approve on the device
#    - then the actual deploy continues
truffile deploy ./apps/my-app

# 5. Test it from the command line via the chat skill
truffile chat --quiet --app my-app "what tools do you expose?"
```

### Workflow: scripted setup (CI / fresh machine)
```bash
truffile connect truffle-1234 --user-id "$TRUFFLE_USER_ID"
# (user still needs to tap approve on the device once)
truffile deploy ./apps/my-app
```

### Workflow: iterating on an existing app
```bash
# fast local check
truffile validate ./apps/my-app

# preview without pushing
truffile deploy ./apps/my-app --dry-run

# full deploy
truffile deploy ./apps/my-app

# verify what's installed
truffile list apps

# remove old version if needed
truffile delete 1
```

### Workflow: cleaning up
```bash
truffile list apps                # see what's there
truffile delete all               # wipe everything from the device
truffile disconnect all           # forget all paired devices
```

## How this skill relates to the others

| Want to do this | Use |
|---|---|
| Build / validate / deploy / manage apps and devices | **truffile-cli** (this skill) |
| Send a message to the Truffle agent on a device | `truffile-chat` |
| Run raw model inference (no agent, no apps) | `truffile-infer` |

## Gotchas

- **Inside a Truffle app container,** discovery/pairing/onboarding are all
  short-circuited automatically — see the "Running inside a Truffle app
  container" section above. From inside a container, every command targets
  the host Truffle directly with no setup.
- **Deploy needs a device.** First-run onboarding will collect one if none is
  set, but the user will need to physically approve on the Truffle screen.
- **`truffile validate` runs locally.** It does not contact the device, so
  it's a fast inner loop while authoring an app.
- **`truffile create` is interactive by default.** Pass both `name` and
  `--path` to make it non-interactive.
- **`truffile delete` indices come from `truffile list apps`.** They are
  position-based, not stable identifiers — re-list before deleting if you've
  changed anything.
- **Only `bash`, `files`, and `text` install step types are supported.** OAuth
  and VNC step types are rejected by `validate` with a clear error. Use a
  `text` step to collect tokens or credentials instead.
- **`truffile.app_runtime`** is the canonical SDK import path inside an app's
  python files. It ships with the installed package even though it's
  gitignored in the source repo — apps can rely on it.
- **The previously-used user id is remembered across runs.** After the first
  successful `truffile connect`, future `connect` invocations offer it as a
  default and the onboarding flow uses it automatically.
