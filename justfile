set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

# List the recipes.
default:
    @just --list

# Install the pinned tools and test dependencies.
install:
    mise install
    python3 -m pip install --disable-pip-version-check -r requirements.txt

# Lefthook re-stages the fixes (`stage_fixed`).
# Format the given files, or the whole repository when none are given.
fmt *files:
    #!/usr/bin/env bash
    set -euo pipefail
    if (( $# )); then
        bun scripts/format.ts -- "$@"
    else
        bun scripts/format.ts
    fi

# Fail when a file needs formatting.
fmt-check:
    bun scripts/format.ts --check

# There is no JavaScript or TypeScript linter here; `core-shell` covers a
# staged script.
# Lint the given files, or the whole repository when none are given.
lint *files:
    #!/usr/bin/env bash
    set -euo pipefail
    if (( $# )); then
        exit 0
    fi
    actionlint
    zizmor .github/workflows

# Run the offline unit suite; no network, Discord or live room.
test:
    python3 -m unittest discover -v

# Everything CI requires.
check: fmt-check lint test

# Redacted gitleaks scan of every fork deviation from the upstream mirror.
secrets:
    git rev-parse --verify 'refs/remotes/origin/main^{commit}'
    GITLEAKS_LOG_OPTS="${GITLEAKS_LOG_OPTS:-origin/main..HEAD}" bun scripts/secrets.ts

# Staged secret scan; gitleaks never prints a finding value.
[private]
secrets-staged:
    gitleaks git --staged --redact --no-banner

# Reject env files, private keys, kubeconfigs and files over 5 MB.
forbidden-files *files:
    #!/usr/bin/env bash
    set -euo pipefail
    bun scripts/forbidden-files.ts "$@"

# actionlint and zizmor over the given workflows, or every workflow.
workflows *files:
    #!/usr/bin/env bash
    set -euo pipefail
    if (( $# )); then
        actionlint -- "$@"
        zizmor --quiet "$@"
    else
        actionlint
        zizmor --quiet .github/workflows
    fi

# shellcheck over the given scripts; nothing to do when none are given.
shellcheck *files:
    #!/usr/bin/env bash
    set -euo pipefail
    if (( $# )); then
        shellcheck --severity=warning --external-sources -- "$@"
    fi

# Advisory Conventional Commit check (C2.4); never fails the commit.
commit-msg file:
    bun scripts/commit-msg.ts {{ quote(file) }}

# Refuse a push to a protected branch and scan the exact pushed range (C7.10).
[private]
hook-pre-push:
    bun scripts/hook.ts pre-push

# Fast subset for pre-push (C7.10), under 30 seconds.
pre-push-check: fmt-check lint

# Refresh locked dependencies when a manifest changed (post-checkout, post-merge).
deps-refresh:
    bun scripts/deps-refresh.ts mise.toml requirements.txt

# Owner job `owner-public-data`: this is a public repository, so the scan runs.
public-data-staged:
    bun scripts/public-data.ts --staged

# Refuses a global or foreign core.hooksPath; migrates only `.githooks`.
# Enable the shared Lefthook hooks without changing global Git settings.
hooks:
    #!/usr/bin/env bash
    set -euo pipefail

    command -v lefthook >/dev/null || {
        printf 'lefthook is not installed; run `mise install` first.\n' >&2
        exit 1
    }

    global=$(git config --global --get core.hooksPath || true)
    if [[ -n "$global" ]]; then
        printf 'A global core.hooksPath is set (%s); lefthook install refuses it.\n' "$global" >&2
        printf 'Remove it yourself, or use `lefthook install --force` only if you really mean it.\n' >&2
        exit 1
    fi

    existing=$(git config --get core.hooksPath || true)
    case "$existing" in
        ""|.githooks) ;;
        *)
            printf 'core.hooksPath is %s; integrate it manually.\n' "$existing" >&2
            exit 1
            ;;
    esac

    if [[ "$existing" == ".githooks" ]]; then
        git config --unset-all --local core.hooksPath
    fi

    lefthook install
    # A failed remote sync only warns in 2.2.2 and still exits 0, so assert the
    # shared jobs loaded before declaring success.
    dump=$(lefthook dump)
    if ! grep -q 'name: core-' <<<"$dump" || ! grep -q 'name: owner-' <<<"$dump"; then
        printf 'The shared hook config did not load; check access to the awepeeps/.github repository.\n' >&2
        exit 1
    fi
    hookdir=$(git rev-parse --path-format=absolute --git-path hooks)
    if [[ ! -x "$hookdir/pre-commit" || ! -x "$hookdir/pre-push" ]]; then
        printf 'Lefthook did not write the pre-commit and pre-push shims.\n' >&2
        exit 1
    fi
    printf 'Shared Lefthook hooks installed; no global settings changed.\n'

# Fail when .agents/skills and .claude/skills disagree.
agent-files:
    bun scripts/agent-files.ts
