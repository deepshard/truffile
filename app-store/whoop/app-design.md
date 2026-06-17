# App Design: WHOOP

Status: working spec for the WHOOP foreground app modernization pass

## Overview

The WHOOP app connects Truffle to a user's WHOOP account through OAuth and
exposes read-only foreground tools for profile, body measurement, cycle,
recovery, sleep, workout, and compact recent-summary data.

The app is foreground-only. It does not submit background context today.

## User Stories

- "Check my WHOOP recovery today and tell me how ready I look."
- "Summarize my sleep from last night and call out the biggest factors."
- "Review my recent strain and workouts for the last week."
- "Compare my recovery, sleep, and strain trends over a date range."
- "Show my latest WHOOP cycle, recovery, sleep, and workouts in one snapshot."
- "Fetch details for this WHOOP sleep, workout, or cycle ID."
- "Explain the WHOOP data with health-context caveats and no medical claims."

## Non-Goals

- no write, coaching, or plan-generation API calls
- no background digest yet
- no diagnosis, treatment advice, or medical claims
- no browser automation install path
- no provider API shape rewrite beyond lightweight return metadata
- no cross-user or team data

## Authentication and Onboarding

The app installs through WHOOP OAuth as defined in [truffile.yaml](./truffile.yaml).

The OAuth step requests:

- `offline`
- `read:profile`
- `read:body_measurement`
- `read:cycles`
- `read:recovery`
- `read:sleep`
- `read:workout`

The installer writes token JSON to `/root/.whoop-truffle/oauth.json` and exports
that path through `WHOOP_TOKEN_STORE_PATH`.

Runtime config lives in [config.py](./config.py). Token handling lives in
[whoop_auth.py](./whoop_auth.py). The auth loader can use an installed token
store, raw local `WHOOP_ACCESS_TOKEN` / `WHOOP_REFRESH_TOKEN` variables, and
client credentials for refresh.

## Foreground Runtime

The foreground runtime is implemented in [foreground.py](./foreground.py).

The runtime uses:

- `truffile.app_runtime.ForegroundApp`
- `truffile.app_runtime.ToolSpec`
- [whoop_client.py](./whoop_client.py) for provider API calls and token refresh

All current tools are read-only and non-destructive.

## Tools and Return Contracts

- `whoop_status`: verifies OAuth/API connectivity and returns auth status plus
  the basic profile.
- `get_profile_basic`: returns the authenticated user's WHOOP profile.
- `get_body_measurements`: returns body measurements and max heart rate.
- `list_cycles`: returns `records`, `count`, `next_token`, and `query` metadata
  for cycle list requests.
- `get_cycle_by_id`: returns one `cycle` plus the requested `cycle_id`.
- `list_recovery`: returns recovery `records`, `count`, `next_token`, and
  `query` metadata.
- `get_recovery_for_cycle`: returns one `recovery` plus the requested
  `cycle_id`.
- `list_sleep`: returns sleep `records`, `count`, `next_token`, and `query`
  metadata.
- `get_sleep_by_id`: returns one `sleep` plus the requested `sleep_id`.
- `get_sleep_for_cycle`: returns one cycle-linked `sleep` plus the requested
  `cycle_id`.
- `list_workouts`: returns workout `records`, `count`, `next_token`, and
  `query` metadata.
- `get_workout_by_id`: returns one `workout` plus the requested `workout_id`.
- `get_recent_whoop_summary`: returns profile, body measurements, latest cycle,
  latest recovery, latest sleep, recent workouts, and workout pagination data.

When WHOOP records include `timezone_offset`, the app annotates start/end and
created/updated timestamps with UTC and local interpretations. This preserves
raw provider fields while making time-zone handling explicit.

## Background Status

The WHOOP app currently has no background runtime. A future background pass
could submit compact daily readiness or sleep/strain summaries, but this pass
does not add background behavior.

## Skills

Foreground skills live under [skills/foreground](./skills/foreground):

- `recovery-and-readiness`
- `sleep-analysis`
- `workout-and-strain-review`
- `health-trend-summary`

The skills focus on sequencing tools, date ranges, pagination, interpretation,
and health-context caveats.

## Eval Prompts

Eval sources live in:

- [evals/instructions.md](evals/instructions.md)
- [evals/prompts.md](evals/prompts.md)

Prompts cover everyday WHOOP questions, discoverability, date ranges, ID-based
detail lookups, safe health-context framing, and a foreground smoke-test prompt.

## Live Smoke Expectations

Use `.env.example` as the local input template. A safe live smoke should:

1. verify `whoop_status`
2. call `get_recent_whoop_summary`
3. list cycles, recovery, sleep, and workouts with a small limit
4. call ID detail tools only when a real ID is available from prior list results
5. confirm no write/destructive tools exist

Do not call provider APIs during unit/app-shell tests.

## Limitations and Future Work

- WHOOP field names and nested score shapes are provider-defined and passed
  through mostly unchanged.
- The app has no background digest, preferences, or notification thresholds.
- There are no app-owned resources because WHOOP data is structured JSON, not
  private file bytes.
- Health interpretation should remain conservative and source-attributed to
  WHOOP metrics.
