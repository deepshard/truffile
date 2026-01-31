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
  type: background  # or foreground
  icon_file: ./icon.png
  process:
    cmd: [python, app.py]
    working_directory: /
    environment:
      MY_VAR: value
  # schedule for background apps only:
  default_schedule:
    type: interval  # interval | times
    interval:
      duration: "1h"  # 15m, 2h, 1d, etc.
      schedule:
        daily_window: "09:00-17:30"  # optional
        allowed_days: [mon, tue, wed, thu, fri]  # optional

files:
  - source: ./app.py
    destination: ./app.py

run: |
  pip install requests
```

### schedule types

**interval** - run every N minutes/hours:
```yaml
default_schedule:
  type: interval
  interval:
    duration: "30m"
    schedule:
      daily_window: "06:00-22:00"
      allowed_days: [mon, tue, wed, thu, fri]
```

**times** - run at specific times:
```yaml
default_schedule:
  type: times
  times:
    run_times: ["08:00", "12:00", "18:00"]
    allowed_days: [mon, tue, wed, thu, fri]
```

## example apps

see `example-apps/` for working examples:
- `example-apps/ambient/hedge` - background app
- `example-apps/focus/finance` - foreground app
