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
| Create, validate, deterministic dry run, deploy generated starter | Pass |
| Public app installation and tool call | Pass |
| Text/password native install and second account | Pass with two synthetic identities |
| Friendly-name account rename and permission controls | Separate aliases, flags and review notes saved |
| Uploaded update | New tool code runs for both accounts; app UUID, both connection IDs, aliases, permission flags, review notes and credential fingerprints preserved |
| Failed uploaded update | Intentional builder failure returns nonzero; previous bundle, both accounts and working tool retained |
| Failed replacement | Intentional builder failure returns nonzero; previous bundle and accounts retained |
| Successful replacement | Same app UUID, new account ID and credentials, old accounts removed, uploaded replacement code runs |
| Reconnect | Selected account ID retained; supplied replacement credentials used by the tool |
| Todoist provider OAuth | Installed from the CLI; consent on a Mac, pasted localhost callback accepted; 47 tools discovered; read-only `user-info` succeeds |
| Second distinct Todoist account | Awaiting user authorization; not yet a real-provider isolation pass |
| Robinhood provider OAuth | Discovery, dynamic registration and authorization URL succeed; awaiting user sign-in; no trades attempted |
| Existing user apps | All 38 baseline apps retain their bundle IDs, connection IDs, status and saved permission flags |

Only disposable test apps are update/reset targets. Synthetic secrets are
checked by fingerprints, not published. Provider identities, callback codes,
credentials and raw device evidence are excluded from this repository.

## Dependency and local verification

The SDK now pins MCP 1.30.0, the patched maintenance release for the existing
1.x API. The accompanying PyFW change aligns its firmware, agent-runtime and
base-minimal pins. This addresses the four dependency advisories recorded in
the initial audit. It does not claim that every affected server transport was
exposed by Truffle.

With MCP 1.30.0:

- Installed-wheel CLI suite: 248 tests and one subtest pass.
- Installed-wheel credential and SIGTERM checks: all four canonical/alias
  variants pass.
- App-runtime OAuth, foreground and remote-MCP suites: 232 tests and 20
  subtests pass, including authenticated HTTP refresh and session cleanup.
- Firmware MCP client, installer OAuth and agent-runtime MCP wire tests:
  69 pass. Two checkpoint-bootstrap tests require the full firmware integration
  environment and were excluded from this isolated dependency run.
- Installed wheel dependency consistency (`pip check`): pass.

The device acceptance above uses the running b4391bb3d firmware. It is not
validation of a newly rebuilt firmware image containing the dependency bump.
No firmware update or PyPI publication was performed during these tests.

## Remaining release evidence

Finish Todoist with a genuinely different second account, verify per-account
reads and an uploaded update with those real OAuth accounts, then finish
Robinhood sign-in and a read-only call. These are pending user interaction,
not completed tests. Provider refresh/revocation over time, browser/VNC setup,
Windows/macOS CLI execution and full Obsidian deployment remain outside this
pass; a Mac browser callback is not proof of running the CLI on macOS.
