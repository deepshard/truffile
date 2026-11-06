# Changelog

## 0.3.35 — 2026-11-05

- Deploy original app bundles through firmware's native installer and builders,
  including account-aware manifests and remote MCP connectors.
- Upload code with `deploy --update` while preserving accounts and settings.
  Use `--replace` for a confirmed reset and fresh setup. Both check firmware
  support before requesting a mutation.
- Add and reconnect accounts, select apps by friendly name, choose accounts
  interactively, and manage aliases, permissions and review notes.
- Drive text/password forms, OAuth callbacks and device setup cards. Expired
  or disconnected setup sessions dismiss stale prompts and callback listeners.
- Fix numeric device connection, Convo completion compatibility, and structured
  app/device listings. Record SDK, runtime and protocol revisions in wheels.
- Update public guides and bundled app-authoring skills for native deployment
  and connection-scoped authentication.

Python 3.12 or newer is required. Developer uploads require firmware advertising
the new capability; older firmware returns an upgrade-required error. MCP stays
at 1.26.0. Native local validation is bundle preflight; firmware performs complete
manifest validation. See [release acceptance](RELEASE_ACCEPTANCE.md) for tested
flows and coverage limits, including the unverified Robinhood provider flow.
