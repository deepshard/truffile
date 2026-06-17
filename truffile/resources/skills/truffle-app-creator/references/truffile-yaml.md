# truffile.yaml Reference

## Full Structure

```yaml
metadata:
  name: <string>                    # display name
  bundle_id: <string>               # org.deepshard.<app-name>
  description: <string>             # what the app does
  icon_file: <path>                 # relative path to icon.png

  foreground:                       # optional
    process:
      cmd: [<string>, ...]          # e.g. [python, my_foreground.py]
      working_directory: /
      environment:
        PYTHONUNBUFFERED: "1"

  background:                       # optional
    process:
      cmd: [<string>, ...]          # e.g. [python, my_background.py]
      working_directory: /
      environment:
        PYTHONUNBUFFERED: "1"
    default_schedule:
      type: interval | times | always
      interval:
        duration: <duration>        # dev interval e.g. "2m"
        prod_duration: <duration>   # production interval e.g. "60m"
        daily_window: <range>       # e.g. "00:00-23:59"

steps:
  - name: Install dependencies
    type: bash
    run: pip install --no-cache-dir httpx>=0.27.0

  - name: Copy app files
    type: files
    files:
      - source: ./my_foreground.py
        destination: ./my_foreground.py
      - source: ./my_background.py
        destination: ./my_background.py
      - source: ./client.py
        destination: ./client.py

  - name: Configure
    type: text
    update_policy: run_on_update
    fields:
      - name: api_key
        label: API Key
        type: password
        env: MY_API_KEY
    validator:
      type: bash
      run: python ./my_background.py --verify
      timeout: 120

  - name: Connect with OAuth
    type: oauth
    update_policy: run_on_update
    update_check: python ./my_foreground.py --verify
    provider: Example
    redirect_uri: https://truffle.net/api/oauth/callback
    auth_endpoint: https://example.com/oauth/authorize
    token_endpoint: https://example.com/oauth/token
    scopes: []
    token_output_file: /root/.example/oauth.json
    token_file_env_name: EXAMPLE_TOKEN_FILE

  - name: Continue
    type: welcome
    update_policy: run_on_update
    content: |
      This app does not need sign-in. Continue to finish installing.
```

## Rules

- at least one of foreground or background must be defined
- bundle_id must be globally unique: org.deepshard.<app-name>
- foreground cmd must start a process that listens on port 8000
- every source file must be listed in a files step
- use --no-cache-dir for pip installs
- PYTHONUNBUFFERED=1 should be set in all process environments
- supported install step types include bash, files, text, oauth, and welcome
- browser/VNC apps are not supported through CLI store install yet

## Files Step

Every python file your app needs must be listed. Directories are supported:
```yaml
- source: ./common/
  destination: ./common/
```

## Schedule Types

- interval: runs every N minutes/hours within optional daily window
- times: runs at specific times of day
- always: runs continuously with 8s restart delay between cycles
