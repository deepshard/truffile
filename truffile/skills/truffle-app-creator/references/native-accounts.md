# Native account setup

Normal CLI deployment uploads the manifest unchanged to firmware's native
installer. It uses builders internally. Connection steps execute for the first
account, an added account, or a reconnection; install steps prepare shared code.

This is the shape used by the synthetic text/API-key acceptance fixture:

```yaml
truffile_version: 4
connections: multi
alias_from: [identity.email]
metadata:
  name: Example Service
  bundle_id: org.example.service
  description: Example account-scoped integration.
  icon_file: icon.png
  foreground:
    process:
      cmd: [python, /service.py]
      working_directory: /
steps:
  - name: Copy code
    type: files
    scope: install
    files:
      - source: service.py
        destination: ./service.py
  - name: Connect account
    type: text
    scope: connection
    fields:
      - name: email
        label: Account email
        type: text
        env: SERVICE_EMAIL
      - name: api_key
        label: API key
        type: password
        env: SERVICE_API_KEY
```

Firmware supplies these values to the selected account's runtime. Do not put
the user's secret in shared app variables, source files or the manifest. Add a
provider validation step using the current native provider recipe before
claiming the connection is authenticated; the fixture only exercises form
submission and account isolation.

Expose account identity for the connection label without exposing the key:

```python
import json
import os
from truffile.app_runtime import ForegroundApp, ToolSpec

app = ForegroundApp("Example Service")

@app.resource("truffle://user-info", mime_type="application/json")
def user_info():
    email = os.environ["SERVICE_EMAIL"]
    return json.dumps({"status": "connected", "identity": {
        "email": email, "provider_subject": email,
    }})

@app.tool(ToolSpec(name="connection_check", description="Check account configuration.",
                   icon="check", annotations={"readOnlyHint": True, "destructiveHint": False}))
async def connection_check() -> dict:
    return {"configured": bool(os.environ.get("SERVICE_API_KEY"))}

if __name__ == "__main__":
    app.run()
```

Keep `app.run()` behind the main guard: firmware imports the module while
probing its entrypoint. An unconditional server start can hang that probe.
Tool annotations describe behavior; the user controls account permissions.

```bash
truffile validate ./service
truffile deploy ./service
truffile connections add "Example Service"
truffile connections reconnect "Example Service"
truffile connections permissions "Example Service" read-only
truffile deploy ./service --update
truffile deploy ./service --replace
```

Test with two accounts. Reconnecting one must leave the other intact; updating
code must preserve both identities and their settings. Replacement deliberately
runs fresh setup and resets accounts. Upload update/replace requires the matching
PyFW capability, while fresh install/add/reconnect use existing native RPCs.

For OAuth, use the current firmware provider recipe and credential helpers.
The CLI displays firmware's authorization URL and sends its callback/code back
to that same pending operation. Legacy token-file examples in `auth-patterns.md`
describe the explicit legacy builder path; do not use them as a multi-account
credential design. Browser/device-code recipes likewise depend on the native
installer version and require provider-specific acceptance testing.
