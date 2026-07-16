---
name: truffle-app-creator
description: |
  Create Truffle apps from scratch or by porting existing MCP servers and open source projects.
  Use when the user asks to "make an app", "create a truffle app", "build an integration",
  "port this to truffle", or wants to connect a new service to their Truffle device.
  Guides through research, architecture decisions, implementation, testing, and deployment.
---

# Truffle App Creator

Build Truffle apps step by step — from idea to deployed, tested app.

## When to use

Activate when the user wants to:
- create a new Truffle app for a service
- port an existing MCP server to Truffle
- connect a new API or service to their Truffle
- understand how Truffle apps work

## Workflow

### Step 1: Understand what the user wants

Interview the user:
- what service or API do they want to connect?
- what should the agent be able to DO with it? (foreground tools)
- what should happen automatically in the background? (background monitoring)
- does the service need API keys or is it public?

Explain the difference between foreground and background clearly:
- foreground: tools the agent calls during a conversation (search, send, check)
- background: scheduled jobs that submit context to the background agent running on their Truffle that decides whether submiited context is worth posting or taking an action on or not
- they run in separate containers and cannot talk to each other directly
- use app variables to share state between them

### Step 2: Research existing solutions

Before building from scratch, search for:
- existing MCP servers for the service (check mcp.io, github, npm)
- open source libraries or SDKs for the API
- existing Truffle apps that do something similar

Use web search to find options. Present them to the user with pros/cons:
- if an MCP server exists: can we proxy it or wrap it?
- if an SDK exists: can we build tools on top of it?
- if nothing exists: we build from scratch using the API docs

Ask the user which approach they prefer.

### Step 3: Decide the app architecture

Based on the user's answers, determine:
- app shape: foreground only, background only, or hybrid
- auth type: API key/text config, OAuth, or public. Browser/VNC apps are not
  supported through the current CLI flow.
- base image: minimal for API apps

Reference: see references/auth-patterns.md for the decision tree.

### Step 4: Scaffold the app

Create the matching starter, then extend it with client code and tests:

```bash
truffile create my-app --type foreground --path ./apps --json --non-interactive
```

Use `--type background` or `--type hybrid` when Step 3 calls for it. Omitting
`--type` keeps the compatibility default: `hybrid`.

The command generates only the selected entrypoints:
```
my-app/
├── truffile.yaml
├── icon.png
├── my_app_foreground.py    (if FG)
└── my_app_background.py    (if BG)
```

Add client, config, worker, and test files as needed. Generate `truffile.yaml`
with the correct steps for the chosen auth type. Reference: see
references/truffile-yaml.md.

Use the app patterns from references/app-patterns.md for the code structure.

### Step 5: Implement the client

Build the API client FIRST with injectable auth and transport:

```python
class MyClient:
    def __init__(self, auth, http):
        self._auth = auth
        self._http = http
```

This makes everything testable from the start.

### Step 6: Implement foreground tools (if FG)

Register tools using ForegroundApp and ToolSpec:

```python
from truffile.app_runtime import ForegroundApp, ToolSpec, err, ok

app = ForegroundApp("my-app")

@app.tool(ToolSpec(
    name="search",
    description="Search.",
    icon="magnifying-glass",
    annotations={"readOnlyHint": True, "destructiveHint": False},
))
async def search(query: str) -> dict:
    ...
```

Follow the rules in references/rules.md for naming, descriptions, error handling.

### Step 7: Implement background worker (if BG)

Subclass BackgroundWorkerApp with the 4 required methods. Follow the rules:
- first cycle seeds state, doesn't submit
- track seen IDs to prevent duplicates
- bound tracking sets
- submit generously, let the proactivity agent curate

### Step 8: Write tests immediately

Don't wait until the end. Write tests as you implement:

```bash
truffile validate ./my-app                         # yaml + source checks
python -m pytest ./my-app/tests/ -v                # unit tests
```

Use FakeHttpTransport and AppHarness. See references/testing-guide.md.

### Step 9: Validate and iterate

Run validation:
- `truffile validate ./my-app` — check manifest, file references, and Python syntax
- `truffile deploy --dry-run ./my-app` — inspect the deploy plan without changing the device
- `python -m pytest ./my-app/tests/` — run tests

Fix any issues. Repeat until everything passes.

### Step 10: Deploy and test

If the user has a device connected:
```bash
truffile deploy ./my-app
```

Then test with the agent:
```bash
truffile chat
you> [test the app's tools]
```

### Step 11: Create skills (optional)

Ask the user if they want to add skills — workflow guides that teach the agent how to use the app's tools effectively. Create SKILL.md files under skills/foreground/ and skills/background/.

## Error handling

Common issues during app creation:
- yaml parse errors: run `truffile validate` and fix the reported issues
- python syntax errors: run `truffile validate`
- missing files in truffile.yaml: run `truffile validate` and compare with the files step
- import errors: make sure all deps are in the bash install step
- auth failures during deploy: check env var names match between text step and code

## Reference scripts

| Script | What it does |
|--------|-------------|
| `scripts/fetch_docs.py` | pull docs from docs.truffle.net |
| `truffile validate <path>` | check truffile.yaml, referenced files, and Python syntax |
| `truffile deploy --dry-run <path>` | inspect the deploy plan without changing the device |

## Reference docs

| Doc | What it covers |
|-----|---------------|
| `references/app-patterns.md` | FG, BG, hybrid, proxy code patterns |
| `references/auth-patterns.md` | API key and public auth patterns with yaml examples |
| `references/testing-guide.md` | how to write tests with fakes and harness |
| `references/truffile-yaml.md` | full manifest format reference |
| `references/rules.md` | all rules for foreground, background, and general app development |
