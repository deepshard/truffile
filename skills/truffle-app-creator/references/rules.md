# Rules for Truffle Apps

## Foreground Rules

- tools must return ok() or err() response dicts
- every tool needs a name, description, and icon
- set readonly=True for tools that only read data
- destructive tools (purchases, deletions, sends) must say so in description
- catch exceptions and return err(), don't let them propagate
- report auth failures to firmware via report_app_error with needs_intervention=True
- tool parameters should have sensible defaults for optional fields
- client should be injectable (accept auth and http transport as constructor params)

## Background Rules

- background workers submit context for the proactivity agent to evaluate
- be comprehensive — submit everything relevant, let the agent curate
- be idempotent — running twice should not produce duplicate submissions
- track seen IDs to prevent re-submitting old content
- bound your tracking sets (max 1500-5000 entries) to prevent memory growth
- persist state to JSON files, not just in-memory
- first cycle should seed state without submitting (avoid stale content on startup)
- use PRIORITY_HIGH for urgent content (mentions, alerts), PRIORITY_LOW for informational

## FG/BG Separation

- foreground and background run in SEPARATE containers
- they CANNOT call each other's functions or share memory
- use app variables (get_app_var/set_app_var) to share state between FG and BG

## General Rules

- all config from environment variables — define a config.py
- don't hardcode service URLs, credentials, or user-specific values
- log to stdout with PYTHONUNBUFFERED=1
- keep files focused: one module per concern (client, config, auth, bg_worker)
- snake_case for tool names: search_items, send_message
- use type hints
- write tests from the start, not at the end
