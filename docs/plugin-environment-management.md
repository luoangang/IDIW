# Plugin environment management

The platform accepts Python 3.9 through 3.14 manifests. This release still requires
the plugin's declared major/minor version to match the platform interpreter.
The five maintained packages now declare Python 3.14 and have new package versions.
Changing the runtime declaration must publish a new version, because installed
artifacts and historical execution snapshots are immutable.

Repeated import of the same artifact checks the interpreter, Python version,
SSL support, direct dependency versions and `python -m pip check`. A healthy
environment is reused. An unhealthy environment is rebuilt before import succeeds.
The requirements file should contain PEP 508 requirements, one per line;
blank lines and comments are accepted. Pip option lines and recursive requirement
includes are not supported by the health probe.

Environment builds use a backup sibling directory and a repair lock. Queued
or running executions block repair, and the queue rejects new executions while
repair is in progress. Builds use the final path because Windows console launchers
embed absolute paths. The new environment is checked before releasing the lock.
The previous directory is retained as a `.backup-<id>` sibling. Failed builds
restores that directory. If the platform is forcibly stopped during repair, inspect
the environment before manually removing a stale `.repair.lock` file.

The package list provides Check Environment and Rebuild Environment actions.
API endpoints:

- `GET /api/v1/packages/{key}/environment`
- `POST /api/v1/packages/{key}/environment/rebuild`

Rebuild repairs the active version's environment without changing package data
or collection settings. Different Python versions per plugin and container
execution remain future runtime-management work.
