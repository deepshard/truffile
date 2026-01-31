# Building TruffleOS Apps
tell ralph i said hi

this is without cli
sketch for what docs will be structured like and u can just feed this to whatever model with example app code to make u an app or ven an exisiting mcp and have it port it

TruffleOS apps come in two flavors: **Focus** and **Background**.

## App Types

| Type | When it runs | What it does |
|------|--------------|--------------|
| **Focus** | Always on, waiting | Exposes tools the AI can call on demand |
| **Background** | On a schedule | Runs periodically, posts to user's feed |

---

## Focus Apps

Focus apps are MCP servers that expose tools to the device AI. When the user asks a question, the AI can call your tools.

### Example: Finance App

```python
from mcp.server.fastmcp import FastMCP

HOST = "0.0.0.0"
PORT = 8000

mcp = FastMCP("finance", stateless_http=True, host=HOST, port=PORT)

@mcp.tool("get_stock_price", description="Get current price for a stock ticker")
async def get_stock_price(symbol: str) -> str:
    # fetch from API...
    return f"{symbol}: $256.44"

@mcp.tool("search_ticker", description="Search for stock ticker symbols")
async def search_ticker(keywords: str) -> str:
    # search API...
    return "AAPL - Apple Inc."

def main():
    print(f"Starting MCP server on {HOST}:{PORT}")
    mcp.run(transport="streamable-http")

if __name__ == "__main__":
    main()
```

### How Tool Calls Work

1. User asks: "What's Apple stock at?"
2. Truffle sees your `get_stock_price` tool
3. calls `get_stock_price("AAPL")`
4. Your app returns the result
5. Truffle responds to you with the data

### Focus App Requirements

- Must run an MCP server on `0.0.0.0:8000`
- Use `transport="streamable-http"`
- Tools are defined with `@mcp.tool()` decorator
- Each tool needs a `description` for the AI to understand when to use it

---

## Local Development (Focus Apps)

You can run your MCP server locally on your machine instead of deploying to the device as well. This is great for fast iteration during development.

### 1. Run the server locally

```bash
cd your-app-directory
python app.py
```

You should see:
```
Starting MCP server on 0.0.0.0:8000
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 2. Get your machine's IP

```bash
# macOS
ipconfig getifaddr en0

# Linux
hostname -I | awk '{print $1}'
```

### 3. Add MCP in TruffleOS Settings

Go to Settings → Add New MCP and enter:

| Field | Value |
|-------|-------|
| **Name** | Your App Name |
| **Server URL** | `192.168.X.X` (your IP from step 2) |
| **Port** | `8000` |
| **Path** | `mcp` |

Now you can use your tools immediately without deploying. Changes to your code take effect as soon as you restart `python app.py`.

---
 
## Background Apps

Background apps run on a schedule and post content to the user's feed.

### Example: Hedge App

```python
import os
from datetime import datetime
from gourmet.ambient import run_ambient, AmbientContext

TICKERS = os.getenv("HEDGE_TICKERS", "AAPL,MSFT").split(",")

def hedge_ambient(ctx: AmbientContext):
    for symbol in TICKERS:
        # fetch stock data...
        price = 256.44
        
        ctx.bg.post_to_feed(
            title=f"📈 {symbol}: ${price}",
            body=f"{symbol} is currently trading at ${price}",
            src_uri=f"https://finance.yahoo.com/quote/{symbol}",
            media_uris=["https://example.com/chart.png"],  # optional
            content_timestamp=datetime.now()
        )

if __name__ == "__main__":
    run_ambient(hedge_ambient)
```

### post_to_feed() Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | str | yes | Card title shown in feed |
| `body` | str | yes | Main content text |
| `src_uri` | str | no | Link to original source |
| `media_uris` | list[str] | no | List of image URLs to display |
| `content_timestamp` | datetime | no | When the content was created |

### Background App Requirements

- Import `run_ambient` and `AmbientContext` from `gourmet.ambient`
- Define a function that takes `ctx: AmbientContext`
- Call `run_ambient(your_function)` in main
- Use `ctx.bg.post_to_feed()` to post content

---

## truffile.yaml

The `truffile.yaml` defines your app's metadata and installation steps.

### Focus App Example

```yaml
metadata:
  name: Finance
  type: foreground
  description: |
    Financial data tools for your Truffle.
  process:
    cmd:
      - python
      - app.py
    working_directory: /
    environment:
      PYTHONUNBUFFERED: "1"
  icon_file: ./icon.png

steps:
  - name: Welcome
    type: welcome
    content: |
      This app provides financial data tools.

  - name: Copy files
    type: files
    files:
      - source: ./app.py
        destination: ./app.py

  - name: Install dependencies
    type: bash
    run: |
      pip install mcp requests
```

### Background App Example

```yaml
metadata:
  name: Hedge
  type: background
  description: |
    Track your stock portfolio.
  process:
    cmd:
      - python
      - app.py
    working_directory: /
    environment:
      PYTHONUNBUFFERED: "1"
      HEDGE_TICKERS: "AAPL,MSFT,GOOGL"
  icon_file: ./icon.png
  default_schedule:
    type: interval
    interval:
      duration: 5m
      schedule:
        daily_window: "06:00-22:00"
        allowed_days: [mon, tue, wed, thu, fri]

steps:
  - name: Copy files
    type: files
    files:
      - source: ./app.py
        destination: ./app.py

  - name: Install dependencies
    type: bash
    run: |
      pip install requests
      pip install gourmet
```

---

## Metadata Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | App name shown to user |
| `type` | yes | `foreground` or `background` |
| `description` | no | What the app does |
| `process.cmd` | yes | Command to run the app |
| `process.working_directory` | no | Working dir (default: `/`) |
| `process.environment` | no | Environment variables |
| `icon_file` | no | Path to PNG icon |
| `default_schedule` | background only | When the app runs |

---

## Schedule Types (Background Apps Only)

### 1. Interval

Run every X time period.

```yaml
default_schedule:
  type: interval
  interval:
    duration: 5m              # required: how often
    schedule:                 # optional: constraints
      daily_window: "09:00-17:00"
      allowed_days: [mon, tue, wed, thu, fri]
```

### 2. Times

Run at specific times each day.

```yaml
default_schedule:
  type: times
  times:
    run_times:                # required: list of times
      - "09:00"
      - "12:00"
      - "18:00"
    allowed_days: [mon, wed, fri]  # optional
```

---

## Duration Format

| Format | Example | Meaning |
|--------|---------|---------|
| `Xms` | `500ms` | 500 milliseconds |
| `Xs` | `30s` | 30 seconds |
| `Xm` | `5m` | 5 minutes |
| `Xh` | `2h` | 2 hours |
| `Xd` | `1d` | 1 day |

---

## Daily Window

Restrict when the app can run during the day.

```yaml
daily_window: "09:00-17:30"
```

Or verbose format:

```yaml
daily_window:
  start: "09:00"
  end: "17:30"
```

---

## Day Restrictions

Use ONE of these (not both):

**allowed_days** - only run on these days:
```yaml
allowed_days: [mon, tue, wed, thu, fri]
```

**forbidden_days** - don't run on these days:
```yaml
forbidden_days: [sat, sun]
```

Valid day values: `sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat`

---

## Installation Step Types

### files

Copy files from your app directory to the container.

```yaml
- name: Copy files
  type: files
  files:
    - source: ./app.py
      destination: ./app.py
    - source: ./config.yaml
      destination: ./config.yaml
      permissions: 600  # optional
```

### bash

Run shell commands.

```yaml
- name: Install dependencies
  type: bash
  run: |
    pip install requests
    apk add --no-cache curl
```

### welcome

Show a welcome message to the user.

```yaml
- name: Welcome
  type: welcome
  content: |
    Welcome to my app!
    It does cool things.
```

### text

Prompt user for text input (saved to env vars).

```yaml
- name: Configure API Key
  type: text
  content: |
    Enter your API key to continue.
  fields:
    - name: api_key
      label: API Key
      type: password
      env: MY_API_KEY
      placeholder: "sk-..."
```

Field types: `text`, `password`, `number`

### vnc

Open a VNC window for user interaction (login flows, etc).

```yaml
- name: Sign into Twitter
  type: vnc
  cmd:
    - python
    - onboard.py
  closes_on_complete: true
  description: |
    Sign into your account in the browser window.
```

---

## Environment Variables

Set in `process.environment`:

```yaml
process:
  environment:
    PYTHONUNBUFFERED: "1"    # always use this for Python apps
    MY_API_KEY: "secret"
    DEBUG: "true"
```

Or collected from user input via `text` steps (uses `env` field).

---

## Quick Reference

### Minimal Focus App

```
my-focus-app/
├── app.py         # MCP server with @mcp.tool() functions
├── truffile.yaml  # type: foreground
└── icon.png       # optional
```

### Minimal Background App

```
my-bg-app/
├── app.py         # Uses run_ambient() + post_to_feed()
├── truffile.yaml  # type: background + default_schedule
└── icon.png       # optional
```
