# SDK release acceptance — 2026-11-02

This continues the [October audit](SDK_AUDIT.md). The SDK candidate is PR #53;
PyFW PR #425 is merged. Live tests use 6272 on
`2026.10.31.4200+gb4391bb3d`, which advertises developer-upload support. They do
not restart or replace firmware. The installed SDK wheel contains that exact
PyFW runtime and protocol revision `e12791a0795496bf8fec5674664a17f08ebe330a`.

## Observed on 6272

| Test | Result |
| --- | --- |
| Numeric connect with an existing session, device JSON, discovery, model listing | Pass |
| Direct inference | Expected response returned |
| New Convo side thread, follow-up, history | Pass; expected responses, same thread |
| Create, validate, deterministic dry run, deploy generated starter | Pass, including its ping tool |
| Explicit legacy builder deployment | Pass for a fresh foreground/background starter; valid JSON result |
| Public app installation and tool call | Pass |
| Text/password native install and second account | Pass with two synthetic identities |
| Friendly-name account rename and permission controls | Separate aliases, flags and review notes saved |
| Uploaded update | New tool code runs for both accounts; app UUID, both connection IDs, aliases, permission flags, review notes and credential fingerprints preserved |
| Failed uploaded update | Intentional builder failure returns nonzero; previous bundle, both accounts and working tool retained |
| Failed replacement | Intentional builder failure returns nonzero; previous bundle and accounts retained |
| Successful replacement | Same app UUID, new account ID and credentials, old accounts removed, uploaded replacement code runs |
| Reconnect | Selected account ID retained; supplied replacement credentials used by the tool |
| Todoist provider OAuth | Installed from the CLI; consent on a Mac, pasted localhost callback accepted; 47 tools discovered; read-only `user-info` succeeds |
| Second distinct Todoist account | Fresh authorization succeeds; per-account reads return two different provider identities; original connection unchanged |
| Real OAuth account preservation during upload | Todoist update installs a changed bundle without sign-in; both account IDs, aliases, permissions and authenticated provider identities remain unchanged, verified by post-update reads |
| Robinhood provider OAuth | Discovery, dynamic registration and authorization URL succeed; awaiting user sign-in; no trades attempted |
| Existing user apps | All 38 baseline apps retain their bundle IDs, connection IDs, status and saved permission flags |

Only disposable test apps are update/reset targets. Synthetic secrets are
checked by fingerprints, not published. Provider identities, callback codes,
credentials and raw device evidence are excluded from this repository.

## Dependency and local verification

The SDK retains the existing MCP 1.26.0 pin. The coordinated dependency upgrade
is deferred at the maintainer's request, and the upgrade-only
[PyFW PR #432](https://github.com/deepshard/pyfw/pull/432) is withdrawn. It is not a
functional requirement for the SDK install, account or update changes. The
dependency advisories in the initial audit remain a separate maintenance item.

Final candidate verification with MCP 1.26.0:

- Installed-wheel CLI suite: 255 tests and one subtest pass after the setup-expiry
  correction below.
- Installed-wheel credential and SIGTERM checks: all four canonical/alias
  variants pass.
- Installed wheel dependency consistency (`pip check`): pass.

The device acceptance above uses the running b4391bb3d firmware without an MCP
upgrade. No firmware update or PyPI publication was performed during these tests.

## Setup-expiry correction

Todoist account addition expired on firmware after 15 minutes, while the CLI
continued waiting for a paste under its longer command timeout. A later callback
then produced the misleading `Internal error from Core` instead of showing the
expiry. No second account was created, and the first account was unchanged.

The SDK now receives installer messages concurrently with terminal input. Server
errors, disconnects and completion dismiss pending prompts; newer setup cards
replace older prompts; loading messages keep flowing. A received terminal result
takes precedence over a paste that is ready simultaneously. All input/callback
tasks are cleaned up without automatically retrying the installation.

Regression coverage includes a real local gRPC stream expiring while the OAuth
paste prompt and localhost listener are active, verifying that both are closed.
A fresh provider callback completed the second account. The corrected installed
CLI also passed a normal text/password installation and the real two-account
Todoist update described above. Disposable fixtures were removed afterward.

## Remaining release evidence

Finish Robinhood sign-in and a read-only call. That provider check is pending
user interaction, not completed. Provider refresh/revocation over time, browser/VNC setup,
Windows/macOS CLI execution and full Obsidian deployment remain outside this
pass; a Mac browser callback is not proof of running the CLI on macOS.
