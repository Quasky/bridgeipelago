set shell := ["bash", "-euo", "pipefail", "-c"]

# List the recipes.
default:
    @just --list

# Install the pinned tools and test dependencies.
install:
    mise install
    python3 -m pip install --disable-pip-version-check -r requirements.txt

# Format the repository.
fmt:
    bun scripts/format.ts

# Fail when a file needs formatting.
fmt-check:
    bun scripts/format.ts --check

# Lint the workflows.
lint:
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

# Install the committed git hooks.
hooks:
    git config --local core.hooksPath .githooks

# Fail when .agents/skills and .claude/skills disagree.
agent-files:
    bun scripts/agent-files.ts
