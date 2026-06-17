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
  supported through CLI store install yet.
- base image: minimal for API apps

Reference: see references/auth-patterns.md for the decision tree.

### Step 4: Scaffold the app

Create the directory structure, the command truffile create does this, read the docs first:
```
my-app/
├── truffile.yaml
├── icon.png
├── my_app_foreground.py    (if FG)
├── my_app_background.py    (if BG)
├── bg_worker.py            (if BG)
├── client.py
├── config.py
└── tests/
    ├── conftest.py
    ├── test_my_app_unit.py
    └── test_my_app_app_shells.py
```

Generate truffile.yaml with the correct steps for the chosen auth type. Reference: see references/truffile-yaml.md.

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
python scripts/check_python.py ./my-app/          # syntax check
python scripts/validate_yaml.py ./my-app/          # yaml check
python -m pytest ./my-app/tests/ -v                # unit tests
```

Use FakeHttpTransport and AppHarness. See references/testing-guide.md.

### Step 9: Validate and iterate

Run the validation scripts:
- `python scripts/validate_yaml.py ./my-app/` — check manifest
- `python scripts/check_python.py ./my-app/` — check all python files
- `python scripts/list_app_files.py ./my-app/` — verify file list matches truffile.yaml
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
- yaml parse errors: run validate_yaml.py and fix the reported issues
- python syntax errors: run check_python.py
- missing files in truffile.yaml: run list_app_files.py and compare with the files step
- import errors: make sure all deps are in the bash install step
- auth failures during deploy: check env var names match between text step and code

## Reference scripts

| Script | What it does |
|--------|-------------|
| `scripts/fetch_docs.py` | pull docs from docs.truffle.net |
| `scripts/fetch_repo.py` | browse example apps from the truffile repo |
| `scripts/validate_yaml.py` | check truffile.yaml format and structure |
| `scripts/check_python.py` | syntax-check all python files |
| `scripts/list_app_files.py` | list files with sizes |

## Reference docs

| Doc | What it covers |
|-----|---------------|
| `references/app-patterns.md` | FG, BG, hybrid, proxy code patterns |
| `references/auth-patterns.md` | API key and public auth patterns with yaml examples |
| `references/testing-guide.md` | how to write tests with fakes and harness |
| `references/truffile-yaml.md` | full manifest format reference |
| `references/rules.md` | all rules for foreground, background, and general app development |
