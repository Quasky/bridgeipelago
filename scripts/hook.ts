#!/usr/bin/env bun
/**
 * Canonical pre-push policy for awepeeps repositories (standards/core.md
 * C7.10). Reads the ref lines Git writes to the pre-push hook on stdin,
 * refuses an update to a protected branch, and scans the exact pushed range
 * with gitleaks. Path-independent: the repository root comes from
 * `git rev-parse --show-toplevel`, so the same bytes work in every checkout.
 *
 * Usage: bun scripts/hook.ts pre-push
 *
 * Exit codes: 0 passed, 1 refused, 2 the check could not complete. Matched
 * secret values are never printed; gitleaks runs with `--redact`.
 */

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

/**
 * Branches that only change through a pull request (C2.1). A fork that keeps
 * upstream on `main` adds its patch branch here, because the default branch is
 * the one a direct push would skip the checks on.
 */
const PROTECTED = ["refs/heads/main", "refs/heads/awepeeps-patches"];

const ZERO = /^0+$/;

interface PushRef {
  localRef: string;
  localOid: string;
  remoteRef: string;
  remoteOid: string;
}

function git(root: string, args: string[]): string | null {
  const result = spawnSync("git", ["-C", root, ...args], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (result.status !== 0) return null;
  return result.stdout ?? "";
}

function repositoryRoot(): string | null {
  const result = spawnSync("git", ["rev-parse", "--show-toplevel"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (result.status !== 0) return null;
  const value = (result.stdout ?? "").trim();
  return value.length > 0 ? value : null;
}

function readStdin(): string {
  if (process.stdin.isTTY) return "";
  try {
    return readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

/** Parse pre-push stdin; malformed and blank lines are ignored. */
export function pushRefs(input: string): PushRef[] {
  const refs: PushRef[] = [];
  for (const line of input.split("\n")) {
    const fields = line.trim().split(/\s+/u);
    if (fields.length < 4) continue;
    const [localRef, localOid, remoteRef, remoteOid] = fields as [
      string,
      string,
      string,
      string,
    ];
    refs.push({ localRef, localOid, remoteRef, remoteOid });
  }
  return refs;
}

/**
 * The first ref that would update or delete a protected branch. A deletion of
 * a protected branch is refused too: it is never an intended outcome.
 */
export function blockedRef(refs: readonly PushRef[]): PushRef | null {
  for (const ref of refs) {
    if (PROTECTED.includes(ref.remoteRef)) return ref;
  }
  return null;
}

/** The remote's default branch, as `origin/<name>`, when it is known. */
function defaultRemoteBranch(root: string): string | null {
  const value = git(root, [
    "symbolic-ref",
    "--quiet",
    "--short",
    "refs/remotes/origin/HEAD",
  ]);
  const name = value?.trim() ?? "";
  return name.length > 0 ? name : null;
}

function mergeBase(root: string, oid: string, base: string): string | null {
  const value = git(root, ["merge-base", oid, base]);
  const name = value?.trim() ?? "";
  return name.length > 0 ? name : null;
}

/** The oldest root commit reachable from `oid`, for a branch with no merge base. */
function rootCommit(root: string, oid: string): string | null {
  const value = git(root, ["rev-list", "--max-parents=0", oid]);
  const lines = (value ?? "").trim().split("\n").filter(Boolean);
  return lines.length > 0 ? (lines[lines.length - 1] as string) : null;
}

function gitleaks(root: string, range: string): number {
  const version = spawnSync("gitleaks", ["version"], { stdio: "ignore" });
  if (version.status !== 0) {
    console.error(
      "hook-pre-push: gitleaks is not installed; run `mise install`.",
    );
    return 2;
  }
  console.log(`hook-pre-push: gitleaks scanning ${range}`);
  const result = spawnSync(
    "gitleaks",
    ["git", "--redact", "--no-banner", `--log-opts=${range}`, "."],
    { cwd: root, stdio: "inherit" },
  );
  if (result.error !== undefined) {
    console.error("hook-pre-push: gitleaks could not run; run `mise install`.");
    return 2;
  }
  return result.status ?? 1;
}

function prePush(root: string): number {
  const refs = pushRefs(readStdin());
  const blocked = blockedRef(refs);
  if (blocked !== null) {
    console.error(
      `BLOCKED: refusing to push ${blocked.localRef} to ${blocked.remoteRef}.`,
    );
    console.error(
      "A protected branch changes only through a branch and a pull request (C2.1).",
    );
    return 1;
  }

  const defaultBranch = defaultRemoteBranch(root);
  for (const ref of refs) {
    if (ZERO.test(ref.localOid)) continue;
    let base: string | null = null;
    if (!ZERO.test(ref.remoteOid)) {
      base = ref.remoteOid;
    } else if (defaultBranch !== null) {
      base = mergeBase(root, ref.localOid, defaultBranch);
    }
    if (base === null) base = rootCommit(root, ref.localOid);
    const range = base === null ? ref.localOid : `${base}..${ref.localOid}`;
    const status = gitleaks(root, range);
    if (status !== 0) return status;
  }
  return 0;
}

function main(argv: readonly string[]): number {
  const command = argv[0];
  if (command !== "pre-push") {
    console.error("usage: hook.ts pre-push < pushed-ref-lines");
    return 2;
  }
  const root = repositoryRoot();
  if (root === null) {
    console.error("hook.ts: not inside a Git worktree");
    return 2;
  }
  try {
    return prePush(root);
  } catch {
    console.error(
      "hook.ts: the pre-push check could not complete; push stopped.",
    );
    return 2;
  }
}

if (import.meta.main) {
  process.exit(main(process.argv.slice(2)));
}
