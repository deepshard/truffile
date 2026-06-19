---
name: truffile-infer
description: |
  Run a single one-shot inference on a connected Truffle device using the
  `truffile infer` CLI without dropping into the interactive REPL. Use when the
  user wants to invoke a model on their Truffle from the command line, pipe a
  prompt in, get JSON output back, list available models or tools, or call an
  MCP tool directly. Everything is doable through CLI args — no interactive
  input is required.
---

# truffile infer (non-interactive)

`truffile infer` runs raw model inference against the IF2 server on a connected
Truffle device. With no positional prompt and a TTY stdin it drops into an
interactive REPL, but **every feature is available through CLI flags** so an
agent can shell out to it without ever entering interactive mode.

## When to use this skill

Reach for `truffile infer` when:

- the user wants the local model on their Truffle to answer something quickly
- they want to pipe text into a model and capture the output
- they want the result as structured JSON for further processing
- they want to list available models or tools on the device
- they want to call an MCP tool directly without going through the model
- they want to attach images or use a system prompt for a one-off query

## One-shot mode triggers

`truffile infer` runs as a one-shot (no REPL, exit when done) if **any** of
these are present:

- a positional prompt: `truffile infer "what is 2 plus 2?"`
- `--stdin` or stdin is piped from another command
- `--prompt-file path.txt`
- `--list-models`
- `--list-tools`
- `--call <tool-name>`

If none of those apply, it drops into the interactive REPL with any other CLI
overrides applied.

## Output rules (very important for agents)

In one-shot mode:

- **stdout** is reserved for the answer. In plain mode it is the assistant's
  text content only. In `--json` mode it is a structured JSON object.
- **stderr** carries all decoration: spinners, "connecting…" messages,
  tool-call status, error diagnostics. Pass `--quiet` to silence stderr
  entirely.
- Exit code is `0` on success, `1` on error, `130` on Ctrl+C.

This means you can always do `truffile infer --quiet "..."` and get a clean,
parseable response on stdout with no preamble.

## Full flag reference

### Conversation
| Flag | What it does |
|---|---|
| `PROMPT...` (positional) | Joined with spaces and used as the user prompt |
| `--system TEXT` | System prompt |
| `--prompt-file PATH` | Read prompt from a file |
| `--stdin` | Force read prompt from stdin (auto-detected if piped) |

### Model
| Flag | What it does |
|---|---|
| `--model NAME` | Override default model on the device |
| `--list-models` | Print available models on the device and exit |

### Sampling
| Flag | What it does |
|---|---|
| `--temperature FLOAT` | Sampling temperature |
| `--top-p FLOAT` | Top-p / nucleus |
| `--max-tokens INT` | Max output tokens (default 2048) |
| `--reasoning {on,off}` | Toggle hidden reasoning trace (default on) |
| `--no-default-tools` | Disable the built-in `web_search` and `web_fetch` |
| `--max-rounds INT` | Max tool-use rounds (default 8) |

### Output
| Flag | What it does |
|---|---|
| `--json` | Emit a structured JSON object on stdout instead of plain text |
| `--show-reasoning` | Include the reasoning trace on stderr in plain mode |
| `--stream` / `--no-stream` | Force streaming on/off (default off in one-shot) |
| `--quiet`, `-q` | Suppress all stderr decoration |
| `--timeout SECONDS` | Per-request HTTP timeout |

### Images
| Flag | What it does |
|---|---|
| `--image PATH_OR_URL` | Attach an image (repeatable). Path or http(s) URL |

### MCP (Model Context Protocol)
| Flag | What it does |
|---|---|
| `--mcp URL` | Connect to a streamable-HTTP MCP server (repeatable) |
| `--list-tools` | List built-in tools and any tools from `--mcp` servers, exit |
| `--call TOOL` | Invoke a single tool by name and exit (no model call) |
| `--tool-args JSON` | JSON object of arguments for `--call` |

## Cookbook

### Basic prompt, plain text response
```bash
truffile infer --quiet "what is the capital of France?"
```
stdout:
```
Paris
```

### Pipe a prompt in from another command
```bash
cat question.txt | truffile infer --quiet
```

### Capture a structured JSON response
```bash
truffile infer --quiet --json "summarize: the sky is blue" | jq -r .content
```
The JSON object contains: `model`, `device`, `content`, `reasoning`,
`tool_calls`, and the full `messages` array.

### Use a system prompt
```bash
truffile infer --quiet \
  --system "You are a terse SQL tutor. Answer in <=2 sentences." \
  "what does INNER JOIN do?"
```

### Pick a specific model
```bash
truffile infer --list-models --quiet
truffile infer --quiet --model Qwen3.5-4B "hello"
```

### Control sampling
```bash
truffile infer --quiet \
  --temperature 0.2 --top-p 0.9 --max-tokens 256 \
  "write a haiku about debugging"
```

### Turn off reasoning for faster, smaller responses
```bash
truffile infer --quiet --reasoning off "what is 2+2?"
```

### Show reasoning trace alongside the answer
```bash
truffile infer --show-reasoning "explain how a binary search works"
# stderr gets the reasoning, stdout gets the final answer
```

### Attach an image
```bash
truffile infer --quiet --image ./screenshot.png "describe this image in one line"
truffile infer --quiet --image https://example.com/cat.jpg "what is in this image?"
```

### Read prompt from a file
```bash
truffile infer --quiet --prompt-file ./long-prompt.md
```

### List the model's available tools
```bash
truffile infer --list-tools --quiet
# built-in:web_search
# built-in:web_fetch
```

### Connect to an MCP server and let the model use its tools
```bash
truffile infer --quiet \
  --mcp https://github-mcp.local/mcp \
  "list my open pull requests"
```

### Connect to MCP and list its tools without invoking the model
```bash
truffile infer --list-tools --mcp https://github-mcp.local/mcp --quiet
```

### Call an MCP tool directly (skip the model entirely)
```bash
truffile infer --quiet \
  --mcp https://github-mcp.local/mcp \
  --call list_repositories \
  --tool-args '{"owner": "deepshard"}'
```
The tool result is printed as pretty-formatted JSON on stdout. Exits non-zero
if the tool reports an error.

### Call a built-in tool directly
```bash
truffile infer --quiet \
  --call web_search \
  --tool-args '{"query": "truffle ai", "max_results": 3}'
```

### Combine: system prompt + image + JSON output
```bash
truffile infer --quiet --json \
  --system "You are a careful image describer." \
  --image ./photo.jpg \
  --max-tokens 200 \
  "describe what you see, focusing on colors" \
  | jq -r .content
```

## Common patterns for agents

**Pattern: ask the local model and capture a clean string**
```bash
ANSWER=$(truffile infer --quiet --reasoning off "...")
```

**Pattern: get JSON and extract a field**
```bash
truffile infer --quiet --json "..." | jq -r .content
```

**Pattern: precondition check**
```bash
if truffile infer --list-models --quiet >/dev/null 2>&1; then
  echo "device is reachable"
fi
```

**Pattern: forward a long prompt safely**
```bash
truffile infer --quiet --prompt-file ./prompt.txt --max-tokens 1024
```

## Gotchas

- **Inside a Truffle app container,** `truffile infer` auto-detects the host
  device via the runtime's env vars (`APP_ID`, `APP_SESSION_TOKEN`,
  `GRPC_ADDRESS`) and routes the IF2 chat-completions endpoint at the host
  firmware directly. No pairing, no onboarding. `--list-models`, `--call`,
  `--mcp`, image attachments, and `--json` all work the same way they do on
  a LAN client. See the `truffile-cli` skill's "Running inside a Truffle
  app container" section for the full contract.
- **No device connected (LAN) → exit 1.** Run `truffile list devices` to
  verify a Truffle is connected before invoking infer in scripts.
- **`--mcp` URLs must start with `http://` or `https://`.** Streamable HTTP only.
- **`--tool-args` must be a JSON object** (not an array, not a bare value).
- **Default behavior is non-streaming in one-shot mode.** Pass `--stream` if
  you want token-by-token output (rarely useful for capture).
- **`--quiet` suppresses error explanations on stderr too.** Drop it during
  development if you want to see what's going wrong.
- **Reasoning is on by default.** This costs latency and tokens. Pass
  `--reasoning off` for short factual queries.
