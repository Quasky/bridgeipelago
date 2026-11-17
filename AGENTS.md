# Repository guidelines

- Keep `main` identical to Quasky's upstream `main`. Make Awepeeps changes on
  `awepeeps-patches`. Permanently preserve `awepeeps-patches` on
  `awepeeps/awepeeps-bridgeipelago`; do not delete it after a merge or PR.
- The [README](README.md) and [setup guide](docs/setup.md) explain bot behavior
  and configuration. The adjacent awepeeps-archipelago repository's
  [bot guide](../awepeeps-archipelago/docs/discord-bot.md) and
  [session workflow](../awepeeps-archipelago/docs/session-workflow.md) govern community runtime
  operations and session management. Source and offline tests define behavior;
  update relevant docs when changing it.
- Keep credentials and private state out of source, test fixtures, tool output,
  and CI artifacts. Do not read live `config.json`, environment secrets, logs,
  registration data, item queues, or runtime state unless explicitly needed and
  authorized. Use temporary files and synthetic values in tests. Never print
  Discord tokens, room passwords, or private session data.
- The WSL runtime service must remain stopped and disabled during changes.
  Do not start/restart/enable it, deploy, connect to a live room, or send Discord
  messages without explicit deployment authorization. Unit tests must stay offline.
- Run from this repository root with Python 3.12 or newer:
  `python -m pip install -r requirements.txt`, then
  `python -m unittest discover -v` and `git diff --check`.
  These commands are portable; activate the intended virtual environment first.
  Do not import `bridgeipelago.py` in tests: its initialization touches runtime
  configuration. Existing tests extract definitions with AST instead.
- Preserve unrelated changes. Do not change Git identity, rewrite history, or
  remediate historical personal email metadata without explicit authorization.
- CI fetches full history and runs Gitleaks on `origin/main..HEAD` with complete
  redaction: every fork deviation from the unchanged Quasky mirror is in scope.
  Feature pushes and pull requests are scanned; mirror `main` pushes are excluded,
  and manual secret scans on `main` explicitly skip. Keep scans fail-closed, with
  no unredacted reports or uploaded scan artifacts. Do not add blanket allowlists.
- A full inherited-history scan on 2026-10-26 found 31 `generic-api-key` findings
  across 208 scanned commits. All 31 belong to inherited upstream commit
  `20e158cb96eeedc4413654220f9e108a90f82544` (under historical `Arch/worlds/`
  files); none belong to fork commits. This metadata-only classification does
  not establish whether each finding is a credential. Inherited-history triage
  is deferred; scoped CI passing does not mean the complete history is clean.
  Do not alter historical values or metadata to resolve these without approval.
