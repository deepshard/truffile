# Auth Patterns

## Decision Tree

```
Does the service already have an MCP server?
├── Yes → Proxy MCP app (see app-patterns.md)
└── No → Build tools directly
    │
    ├── API key available? → text install step
    │   User enters key. Promoted to env var.
    │   Validator script verifies before install completes.
    │
    └── No auth needed? → no auth step
        Public APIs. Just bash + files steps.
```

Note: OAuth and VNC auth are supported in the platform but not yet available through truffile deploy. Use the Truffle client app for OAuth and VNC-based apps.

## API Key (truffile.yaml)

```yaml
- name: Configure API access
  type: text
  fields:
    - name: api_key
      label: API Key
      type: password
      env: MY_API_KEY
    - name: preference
      label: Optional preference
      type: text
      default: ""
      env: USER_PREFERENCE
      env_default_if_empty: "default_value"
  validator:
    type: bash
    run: python ./verify.py
    timeout: 120
    error_message: Could not verify credentials.
```

At runtime, the app reads credentials from env vars: `os.environ["MY_API_KEY"]`.

## No Auth (public APIs)

No auth step needed. Just bash + files steps in truffile.yaml. The app accesses public endpoints directly.
