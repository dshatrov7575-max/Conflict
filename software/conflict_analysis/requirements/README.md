# Dependency lock boundary

These files are release inputs for the pinned **Linux amd64 / CPython 3.12**
container and GitHub Actions gates. They are not cross-platform development
requirements.

- `build-lock.txt`: exact build backend tools used with `--no-build-isolation`;
- `production-lock.txt`: runtime dependencies installed into the production image;
- `test-lock.txt`: complete Linux test surface for the required product gate.

Every non-comment entry is an exact version with an accepted wheel SHA-256.
Production and required CI use `--require-hashes --only-binary=:all:` and run
`pip check`; the production image performs its final installation offline from
the verified wheelhouse. A project wheel is built only after the build lock is
installed and build isolation is disabled.

To change a dependency, update the declared range in `pyproject.toml`, resolve
and review the complete transitive set in a clean CPython 3.12 environment,
record hashes for the accepted Linux amd64 wheels, and verify the result with:

```bash
python -m pip download --require-hashes --only-binary=:all: \
  --platform manylinux2014_x86_64 --implementation cp \
  --python-version 3.12 --abi cp312 \
  --requirement requirements/production-lock.txt --dest /tmp/prod-lock

python -m pip download --require-hashes --only-binary=:all: \
  --platform manylinux2014_x86_64 --implementation cp \
  --python-version 3.12 --abi cp312 \
  --requirement requirements/test-lock.txt --dest /tmp/test-lock
```

Never refresh hashes without reviewing the resolved names, versions, wheel tags
and upstream release notes. The locks establish dependency identity for the
technical build; they do not establish scientific validity.