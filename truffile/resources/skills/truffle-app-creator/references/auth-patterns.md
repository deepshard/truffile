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

OAuth install steps are supported by the platform/store installer. Browser/VNC
apps are not supported through CLI store install yet; tell users to install
those in Symphony Settings.

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

## OAuth

Use an `oauth` step when the provider supports browser OAuth and the app has a
token file/env path. Keep update behavior explicit:

```yaml
- name: Service OAuth Sign-In
  type: oauth
  update_policy: run_on_update
  update_check: python ./foreground.py --verify
  provider: ServiceName
  redirect_uri: https://truffle.net/api/oauth/callback
  auth_endpoint: https://example.com/oauth/authorize
  token_endpoint: https://example.com/oauth/token
  scopes:
    - read:data
  client_id_env: SERVICE_CLIENT_ID
  client_secret_env: SERVICE_CLIENT_SECRET
  token_output_file: /root/.service/oauth.json
  token_file_env_name: SERVICE_TOKEN_FILE
  app_var_key: service_oauth
```
