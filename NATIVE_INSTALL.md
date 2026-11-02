# Installing and managing apps

Normal `deploy` uploads the original bundle to firmware's native installer.
Firmware uses its existing builder containers to run the install plan. The CLI
handles progress, uploads, setup forms, and browser authorization. It does not
reimplement connection isolation or rewrite the manifest into a legacy plan.

```bash
truffile connect 6272
truffile validate ./my-app
truffile deploy ./my-app
truffile deploy ./my-app --update
truffile deploy ./my-app --replace
```

`deploy` accepts a directory containing `truffile.yaml` or a `.truffle` ZIP.
For a directory, files are packaged with stable ordering/timestamps. `.git`,
virtual environments, Python caches, `.env`/`.env.*`, and existing `.truffle`
archives are excluded. `.truffleignore` supports relative glob patterns and
directory prefixes, one per line. Symlinks, escaping archive paths and duplicate
archive entries are rejected. Bundles are limited to 200 MiB expanded.

`validate` and `deploy --dry-run` perform local bundle preflight. The manifest
is passed through unchanged: firmware performs full schema and install-plan
validation, including connection scopes, connectors, static resources, base
image, and resource profile. A preflight pass is not proof that a particular
firmware supports every declared feature.

## Install, update, replace

| Command | Meaning |
| --- | --- |
| `deploy ./app` | Fresh installation. An existing matching bundle ID requires an explicit update or replace choice. |
| `deploy ./app --update` | Rebuild and publish code through firmware's existing developer update path, preserving installed account identities and setup. |
| `deploy ./app --replace` | Use the native reset path with the uploaded bundle; run fresh setup and replace the old accounts. The CLI confirms this reset. |
| `deploy ./app --replace --yes` | Explicitly confirm replacement for automation. |

Both update and replacement require the PyFW developer-upload capability
introduced with the accompanying SDK firmware changes. The CLI checks support
using a read-only request **before** starting either mutation. Older firmware
gets an upgrade-required error. It never falls back to deleting the app or to
a catalog reset. The server retains its existing behavior for older clients.

The public RPC without the developer-upload opt-in still means catalog update
reconciliation. A developer upload opts in explicitly and is routed through the
same serialized native update/reset machinery used by firmware. Successful CLI
deployment verifies the installed bundle hash after the terminal response.

The direct builder remains available for development/debugging:

```bash
truffile deploy ./legacy-app --legacy-builder
truffile deploy ./legacy-app --interactive
truffile validate ./legacy-app --legacy-builder
```

`--interactive` opens the legacy builder shell. Normal native deployment already
prompts for account setup; it does not need that flag. Direct builder deployment
supports the older schema and fresh bundle IDs only. Use normal deployment for
modern manifests, updates and replacements.

## Accounts and permissions

Friendly app names, bundle IDs and UUIDs are accepted. Account aliases and UUIDs
are accepted too. If a name is ambiguous, the terminal shows matching choices.

```bash
truffile connections list Google
truffile connections add Google
truffile connections reconnect Google
truffile connections delete Google
truffile connections rename Google Work
truffile connections permissions Google read-only
```

For reconnect/delete/rename/permissions, omitting the account opens a numbered
picker. The rename example chooses an account and names it `Work`; the permission
example chooses an account and makes it read-only. To select directly:

```bash
truffile connections reconnect Google "work@example.com"
truffile connections rename Google "work@example.com" Work
truffile connections permissions Google Work auto-review --notes "Review external writes"
truffile connections delete Google Work --yes
```

Deletion asks for confirmation unless `--yes` is provided. Scripts must provide
an unambiguous account and `--yes` for deletion. `--json` and `--non-interactive`
never open a picker or prompt. No selection silently means “all accounts.”

Permission modes are `default`, `read-only`, `read-write`, and `auto-review`.
`default` removes the account override so device policy applies. Omitted
`--notes` preserves the current review notes. These commands do not alter
device-wide defaults or grant an app permission automatically.

## Authentication

Native text/password forms, including API-key setup, are rendered in the
terminal. Password inputs are hidden. For automation, supply a JSON map of
field names to string values:

```bash
truffile deploy ./app --non-interactive --json --answers-file /private/setup.json
truffile connections add "My App" --json --answers-file /private/second-account.json
```

Keep answer files outside the source tree. The explicitly supplied answer file
is excluded from directory uploads even if it is inside the tree. Never include
credentials in a prebuilt bundle. Field keys can be `name` or `step_index.name`
when separate steps use the same field name. Supplied values are not printed.

For OAuth, the CLI shows the authorization URL and accepts a callback URL or
provider approval code. URL callbacks must match the pending state. On POSIX,
firmware-provided localhost callbacks can complete automatically; pasting is
also available when the browser is on another computer or the port is busy.
Browser/VNC setup cards show the device setup URL and follow the card's completion
behavior. Native device-code approval displays the link and waits for the
provider process to finish without asking for a callback paste.
Provider-specific consent, token refresh and custom setup still run
through the firmware install plan, not through a new CLI token store.

Interactive authorization is not silently completed in JSON/noninteractive
mode. Missing input returns an interaction-required error and requests
cancellation. Rerun interactively or supply form answers as appropriate.

`--timeout` defaults to 900 seconds for install/add/reconnect. A timeout or
disconnect is not permission to retry blindly: cancellation is requested, but
the operation may already have committed. Inspect the app before retrying.
Mutations are serialized on firmware, so an immediate follow-up command can
report that another operation is still finishing.

## Current verification boundary

On updated 6272, fresh native installs, uploaded updates and replacements pass
live acceptance. An update preserves two synthetic accounts and their IDs,
credentials, aliases, permissions and review notes. Failed builds retain the
previous app. Successful replacement resets the accounts only after its build
succeeds. Add-account and reconnect are also verified.

Todoist's real OAuth installation works with consent in a Mac browser and a
pasted localhost callback. Tool discovery and a read-only provider call pass.
A second distinct Todoist account and Robinhood authorization are still pending.
See [RELEASE_ACCEPTANCE.md](RELEASE_ACCEPTANCE.md) for exact evidence and limits.

Older firmware's update/replace capability rejection was previously checked
without replacing existing apps. Windows/macOS CLI execution and browser/VNC
sign-in remain separate acceptance tests.
