# Bundled generated sources

Truffile ships two packages that are produced outside this repository:

- `truffle/`: generated Python protobuf and gRPC bindings for TruffleOS.
- `truffile/app_runtime/`: the shared application runtime bundled in Truffile releases.

Both directories are tracked so a source checkout and source distribution can
be installed, imported, and tested without an unpublished build step. Their
release provenance and checksum are recorded in `generated-sources.json`.

To refresh them from an audited Truffile wheel:

```bash
python scripts/sync_generated_from_wheel.py path/to/truffile-X.Y.Z-py3-none-any.whl \
  --expected-sha256 <sha256>
```

After refreshing, run the full test suite and build/install smoke tests before
updating the checked-in provenance manifest.
