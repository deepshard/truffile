# truffile

TruffleOS SDK - deploy apps to Truffle devices

## install

```bash
pip install truffile
```

or from source:
```bash
git clone <repo>
cd truffile
pip install -e .
```

## commands

```bash
# find truffle devices on your network
truffile scan

# connect to a device (first time requires approval on device)
truffile connect truffle-6272

# deploy an app from current directory
truffile deploy

# deploy an app from a specific path
truffile deploy ./my-app

# deploy with interactive shell (for debugging)
truffile deploy -i

# list installed apps on connected device
truffile list apps

# list connected devices
truffile list devices

# disconnect from a device
truffile disconnect truffle-6272

# disconnect from all devices
truffile disconnect all
```

## truffile.yaml

apps need a `truffile.yaml` in their directory:

```yaml
metadata:
  name: My App
  description: does cool stuff
  type: ambient  # or focus

files:
  - app.py
  - icon.png

run: |
  pip install requests
  pip install gourmet[ambient] --extra-index-url https://test.pypi.org/simple/

process:
  cmd: python
  args: [app.py]
  env:
    MY_VAR: value
```

## example apps

see `example-apps/` for working examples:
- `example-apps/ambient/hedge` - background app
- `example-apps/focus/finance` - foreground app
