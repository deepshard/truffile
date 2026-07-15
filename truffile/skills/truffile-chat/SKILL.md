---
name: truffile-chat
description: |
  Compatibility guidance for the deprecated truffile chat command. Route new
  persistent agent work to the truffile-agent skill and use chat only when an
  existing script cannot yet be migrated.
---

# Truffile chat compatibility

`truffile chat` is a one-release compatibility alias. For all new work, load
and follow the sibling `truffile-agent` skill instead:

```bash
truffile run "new request"
truffile run --resume <task-id> "follow-up"
truffile run --last "follow-up"
truffile task list --json
```

Existing commands continue to map as follows:

| Legacy command | Canonical command |
|---|---|
| `truffile chat "prompt"` | `truffile run "prompt"` |
| `truffile chat --task-id ID "follow-up"` | `truffile run --resume ID "follow-up"` |
| `truffile chat --resume-last "follow-up"` | `truffile run --last "follow-up"` |
| `truffile chat` | `truffile` |
| `truffile chat --list-tasks N` | `truffile task list --limit N` |

Do not add new uses of `truffile chat`. Migrate scripts to `run` and `task` so
they receive fail-closed resume behavior, stable exit codes, explicit device
selection, and the current JSON contract.
