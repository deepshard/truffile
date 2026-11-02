# Truffile SDK/CLI audit — 2026-10-30

## Latest acceptance

See [RELEASE_ACCEPTANCE.md](RELEASE_ACCEPTANCE.md) for the November 2 device
results, implemented upload/update/reset paths, real Todoist OAuth and patched
MCP dependency verification. The remaining sections preserve the initial audit;
their candidate limitations and dependency pin describe the October 30 state.

## Follow-up implementation

The findings and candidate column below describe the initial audit/first patch.
The follow-up adds native bundle deployment, separate update/replace modes,
friendly account pickers, and add/reconnect commands. See
[NATIVE_INSTALL.md](NATIVE_INSTALL.md) for the current behavior and verification
limits; the initial limitations below are retained as the audit record.

The native installer still uses builders. Uploaded updates and replacements
now have explicit public routing with read-only capability negotiation; older
clients keep their previous catalog-update/reset behavior. Full live testing
of those new upload routes requires running the accompanying PyFW change.

## Baseline and scope

Compared the clean PyPI `truffile==0.3.34` install with Truffile remote main
`7ac2238` and PyFW remote main `c3108488270ca3c1f0b9327c86953e64208dfe4b`.
The published CLI source matched that Truffile revision, apart from the release
version. The package and command are named **truffile**, not `truffle`.

Live tests ran on 6272 with PyFW `2026.10.29.4174+gc31084882`. Pairing credentials
were reused in an isolated local state directory. Tests used new side chats,
a scratch Obsidian vault, and a disposable native app with two synthetic
accounts. Existing user apps and credentials were not used as mutation targets.
The firmware fixes below were regression-tested locally; device firmware was
not replaced during this audit.

The wheel ships generated Truffle protocols and `truffile.app_runtime` copied
from PyFW. It does not ship the firmware's native installer implementation.
Generated bindings alone do not make the CLI a native installer client.

## Feature results

“Live” means observed on the device or scratch host setup. “Source/test” means
verified by source inspection or automated tests, not provider sign-in.

| Feature | Published baseline result | Candidate result / evidence |
| --- | --- | --- |
| Package installation/import/help | Pass in a clean Python 3.12 environment | Candidate wheel also installs independently |
| Discovery | `scan --timeout 3` discovers local devices | Unchanged |
| Saved-session connection | `connect truffle-6272` succeeds | Unchanged |
| Numeric device connection | `connect 6272` attempts `6272.local` and fails | Fixed; live saved-session connection succeeds |
| Installed app listing | Works, but JSON only includes name and UUID | Includes bundle identity, installed release, connection capability, accounts, status, saved permissions, and app error |
| Device listing JSON | Exits successfully with terminal text instead of JSON | Fixed and tested |
| Scaffold / validate / dry run | Generated starter passes local checks | Still a legacy scaffold; background code is a placeholder |
| Fresh builder deployment | Fails at finalization: `unknown app: <new UUID>` | PyFW fix allocates the default connection before bootstrap/publication; regression-tested, pending firmware rollout |
| Replace existing app | Source confirms deletion happens before the replacement build | CLI now refuses an existing bundle ID before creating a builder; never deletes it as an update strategy |
| Native current manifests | Google v5 incorrectly passes legacy validation; current GitHub/Notion connector manifests fail with legacy process errors | Unsupported native schemas now fail explicitly before deployment |
| Bundled examples | All seven bundled example manifests validate | This is not proof of provider authentication or live app behavior |
| Start a new Convo side chat | CLI reports missing child thread although firmware accepted the message and replied | Fixed; live new chat returns its answer and canonical thread ID |
| Convo follow-up/history/list | Existing-thread operations work | Live follow-up/history/rename/hide/restore/idle interrupt pass |
| Models / direct inference | Model listing and streaming/nonstreaming inference succeed | No change needed for tested path |
| Bundled skills/examples export | `load all` succeeds | Guidance corrected for current limitations and permissions |
| Native text/API-key install | No high-level CLI command | Raw public RPC fixture install succeeds |
| Add second account | No high-level CLI command | Raw public RPC succeeds with a separate connection |
| Reconnect account | No high-level CLI command | Raw public RPC succeeds on the fixture and retains its connection ID |
| Inspect/rename/account permissions | Missing CLI/SDK conveniences | Added commands and SDK methods; live permission and rename succeed |
| Delete one connection | Missing CLI/SDK convenience | Added command and SDK method; tested on the disposable second account |
| Public update request | `start_update` queues registry reconciliation, ignoring supplied developer source | Explicitly documented; uploaded developer update still requires a different public contract |
| Obsidian local bridge | Unconfigured status correctly fails; attach/serve/local probe succeed on scratch vault | Device deployment remains affected by the builder bug until the firmware fix ships |
| Authentication callback parsing | Full callback URL with missing state is accepted | Missing/mismatched state rejected; raw provider code paste retained |
| Stored credentials | State written directly with umask-dependent permissions (0644 observed) | Atomic replacement with owner-only file permissions on POSIX |
| Script error signaling | Failed app deletion returns success; first-run EOF can report success | Nonzero failure, noninteractive unpaired commands do not prompt, JSON error for affected path |
| Release provenance | Published wheel lacks documented `PROTOCOL_SHA`; README writes the wrong repository SHA | Workflow stages protocol SHA plus three source revisions and tests the installed CLI against shipped bindings |

## Root causes and first fixes

### Convo acceptance changed

The current server returns the accepted user node inside the new side thread.
The CLI only checked the older `child_thread` anchor response. It therefore
reported failure after a successful send. The fix accepts the current positive
`thread_id` and retains support for the old response shape. It does not resend
the message. If an acknowledgement is still unrecognized, inspect history
before retrying to avoid duplicate requests.

### Builder finalization assumes the app already exists

`AppBuilderService._finish_build_session` resolved a default connection from
the app database before a new app had been published. The fix allocates a new
connection UUID, uses it as the bootstrap snapshot provider, and passes the
same UUID into the atomic app/skills publication. Complete, empty-skill,
interrupted-transfer, and cancelled-transfer paths are regression-tested.
This fix needs PyFW deployment; upgrading the CLI alone cannot repair it.

### Legacy replacement is not an update

`deploy --replace` deleted the old app before building. That can lose accounts,
credentials, aliases, permissions, and the working app on failure. The first
fix is a guard, not an implementation of native updates. Both ordinary deploy
and `--replace` refuse an existing bundle ID. A distinct development bundle ID
is safe for an independent fixture; it is not a migration of existing users.

### Native lifecycle support exists below the CLI

Current public RPCs support fresh native installation, add-account,
reconnection, account metadata/permission changes, and account deletion. A
direct protocol fixture verified these without real provider credentials.
The CLI currently only exposes the new inspect/rename/permission/delete subset.

`Apps_InstallApp(start_update)` is specifically a catalog-reconciliation nudge.
It returns a finish message before an asynchronous update necessarily completes.
Passing a file source does not turn it into a developer upload. The initial
audit harness incorrectly treated that terminal response as an upload result;
inspection of the installed bundle and server route corrected the result.
No developer-code-update or credential-preservation claim is based on it.

PyFW already has `install_developer_update_stream`, used by the internal app
debug console. It shares the serialized update worker. Public
`start_new.replace_app_uuid` routes to **reset**, not that developer update
method. A new public SDK update flow must not confuse these operations.

### Permission defaults have different scopes

Account flags are 0 (inherit default), 1 (read), 3 (read/write), and 11
(read/write with review). The ASK bit is reserved and rejected. The new CLI
preserves existing review notes when `--notes` is omitted and targets exactly
one account. It reports saved flags, not a computed effective decision.

The device-wide permission-default setter clears existing account overrides.
It must not be presented as merely choosing a default for future installs.
Firmware also has registry initial-install permission configuration; exposing
that safely is separate work. App manifests/tool annotations must not grant
themselves user authority.

Permission RPC success can precede release of the app's operation lane. An
immediate subsequent rename was rejected as another operation in progress;
the rename succeeded after the first operation completed. Automatic retry of
uncertain writes would be the wrong fix. The SDK needs operation status.

## Remaining work, in implementation order

| Priority | Work | Acceptance criteria |
| --- | --- | --- |
| P0 | Merge/release the builder fix and CLI correctness fixes | New scaffold deploy succeeds on updated firmware; new Convo succeeds with both supported acknowledgement shapes; existing app never deleted by deploy |
| P1 | Canonical native manifest validation, packaging, and installation | Validate with the same versioned schema as firmware; honor connections, scopes, connectors, skills, resources, base image and resource profile; reject unsupported firmware before side effects |
| P1 | Public developer update contract | Route explicitly to native developer update, return durable operation ID, distinguish enqueue from completion; do not overload registry refresh or reset |
| P1 | Safe update acceptance suite | Change tool code while preserving app UUID, every connection ID, credential generations, aliases, permissions and account data; failed update leaves the old app usable; test app-global and account-scoped migrations |
| P1 | CLI/SDK native install driver | Drive upload, welcome, text/password, validation, OAuth and supported custom/browser interactions; return actionable interaction-required results instead of hanging |
| P1 | Add/reconnect commands | Add two accounts; reconnect exactly one; cancel or fail validation without modifying the other; retain permission overrides and intentional aliases according to the firmware contract |
| P1 | Authentication lifecycle | Use connection credential APIs; support refresh/rotation; keep secrets out of bundle/logs/JSON; validate OAuth state and provider-specific code handoff; exercise actual provider flows |
| P1 | Upgrade the pinned MCP dependency | Move off 1.26.0 to a version addressing the four open advisories below; verify PyFW/runtime transport compatibility, authenticated sessions, and client shutdown before release |
| P1 | Operation status, deadlines and cancellation | Expose terminal status and correlation ID; report pending/unknown outcomes; no blind write retries; recover after disconnect/timeout without duplicate install or duplicate chat |
| P1 | User-controlled initial permissions | Separate per-account overrides, initial-install preferences, and device-wide policy/reset; show effective versus saved permissions; preserve existing users on updates |
| P2 | Native authoring templates | Provide working public, API-key/text, OAuth, connector and background examples; remove placeholder success impressions; test packaged files and resources |
| P2 | Consistent machine output | One JSON document or explicit event stream, progress only on stderr, stable error codes and nonzero exits across all commands, including pairing/auth failures |
| P2 | Actionable installer errors | Invalid fixture destination `/fixture.py` produced only an internal-error reference; return a safe manifest path error for invalid absolute destinations |
| P2 | Packaging/release contract | Record all source revisions; run installed-wheel CLI/runtime tests against the exact generated protocols; define supported firmware range and test oldest supported version |
| P2 | Docs and skills migration | Replace legacy recipes with versioned native examples once the client supports them; document add/reconnect/update/default permissions and provider-specific authentication |
| P2 | Obsidian portability and reproducibility | Test full native deployment, Windows/macOS service lifecycle, and updates; review dependency on external `screen` and mutable app-source downloads |

The current PR intentionally delivers the verified first fixes plus existing
account controls. It does **not** claim the native installer migration is done.

### Dependency advisories

GitHub reports four open Dependabot alerts for `mcp==1.26.0` in
`pyproject.toml`: three high and one medium. The listed first patched versions
are 1.27.2 for [HTTP session principal validation](https://github.com/advisories/GHSA-jpw9-pfvf-9f58)
and [experimental task ownership](https://github.com/advisories/GHSA-hvrp-rf83-w775),
1.28.1 for [WebSocket Host/Origin validation](https://github.com/advisories/GHSA-vj7q-gjh5-988w),
and 1.30.0 for [unbounded StreamableHTTP sessions](https://github.com/advisories/GHSA-84m7-p3x7-pcfv).
These are confirmed dependency alerts, not a claim that each affected transport
or feature is exposed by every Truffle app. Exposure and the coordinated
dependency upgrade remain to be tested; this PR does not change that pin.

## Authentication coverage

| Model | Legacy CLI | Native path / remaining evidence |
| --- | --- | --- |
| Public/no auth | Bash/files steps exist | Full native fixture uses synthetic account configuration; real public app install still needs a release gate |
| API key/password/text | Promoted into process environment; legacy validation handler | Native connection-scoped synthetic install/add/reconnect verified |
| Browser OAuth | Local OAuth handler, token-file output; callback parser regression-tested | Real provider consent, redirect/paste, refresh and multi-account isolation not exercised in this audit |
| Device code/custom approval | No complete high-level CLI flow | Must map supported native interaction types to a deliberate CLI handoff |
| Browser/VNC | Explicitly unsupported by legacy validator | Needs native driver capability and separate interactive acceptance coverage |

## Verification and limits

The published baseline suite had 204 passing tests and one failure caused by
an obsolete test fixture assuming a removed Convo protobuf field. The fixture
now tests that legacy rendering shape independently from current generated
bindings. The candidate source passes all 225 tests plus one subtest. The wheel
is tested separately from outside the checkout against its shipped protocols.

The wheel runtime smoke suite passed canonical imports, the compatibility
alias, credential reads/writes, and SIGTERM shutdown for both import paths.
All 39 targeted PyFW builder regression and capacity/cleanup unit checks pass;
no live firmware deployment is implied by those results. The broader test
selection also found a stale capacity-test fixture without an authenticated
RPC context; that fixture is corrected to reach and test capacity rejection.
Database-backed generation/cancellation tests require a separate integration
environment and were excluded from the isolated unit run.

Not live-tested: new pairing approval, real Google/Outlook/other provider
sign-ins, native uploaded code updates, older firmware, Windows/macOS,
browser/VNC install, destructive user deletion or hard Convo reset, and full
Obsidian device deployment. Existing-thread follow-up and idle interruption
do not prove every in-flight tool/approval cancellation path.

Private raw evidence is retained locally under
`support-runs/truffile-audit-20261030`; it contains device state and must not be
committed or copied wholesale into issues. The table above is the shareable
audit record.
