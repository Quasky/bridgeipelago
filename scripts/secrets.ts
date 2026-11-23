#!/usr/bin/env bun
// Redacted gitleaks scan. GITLEAKS_LOG_OPTS selects a commit range (pull
// request diff); unset scans the complete history (main and the weekly run).
const range = process.env.GITLEAKS_LOG_OPTS?.trim();
const args = ["git", "--redact", "--no-banner", ...(range ? ["--log-opts", range] : []), "."];
const result = Bun.spawnSync(["gitleaks", ...args], { stdout: "inherit", stderr: "inherit" });
process.exit(result.exitCode ?? 1);
