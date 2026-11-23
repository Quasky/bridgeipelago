#!/usr/bin/env bun
/**
 * Reject staged files that must never be committed (core.md C7.9): environment
 * files other than `*.example`, private keys, kubeconfigs, and files over 5 MB.
 * The `forbidden-files` recipe passes the staged file list; nothing is printed
 * but the path and the reason.
 */

import { spawnSync } from "node:child_process";

/** 5 MB is the contract limit; use MiB so the message is unambiguous. */
const MAX_BYTES = 5 * 1024 * 1024;

/** The public half of a key pair is not a secret. */
const PUBLIC_KEY = /\.pub$/u;

/** `id_rsa`, `id_ed25519`, and similar OpenSSH private key names. */
const PRIVATE_KEY_NAME = /^id_[A-Za-z0-9._-]+$/u;

/** Both separators, so the same bytes work on a Windows checkout. */
function baseName(path: string): string {
  const parts = path.split(/[\\/]/u);
  return parts[parts.length - 1] ?? path;
}

export function forbiddenReason(path: string): string | null {
  const name = baseName(path);
  if (name === ".env" || name.startsWith(".env.")) {
    return name.endsWith(".example") ? null : "environment file";
  }
  if (name.endsWith(".pem")) return "PEM file";
  if (name.endsWith(".key")) return "key file";
  if (name === "kubeconfig" || name.endsWith(".kubeconfig")) {
    return "kubeconfig";
  }
  if (PRIVATE_KEY_NAME.test(name) && !PUBLIC_KEY.test(name)) {
    return "private key";
  }
  return null;
}

interface CommandResult {
  status: number;
  stdout: string;
}

function git(root: string, args: string[]): CommandResult {
  const result = spawnSync("git", ["-C", root, ...args], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  return { status: result.status ?? 1, stdout: result.stdout ?? "" };
}

/** Size of the staged blob, so the check sees what the commit would contain. */
export function stagedSize(root: string, path: string): number | null {
  const result = git(root, ["cat-file", "-s", `:${path}`]);
  if (result.status !== 0) return null;
  const size = Number.parseInt(result.stdout.trim(), 10);
  return Number.isNaN(size) ? null : size;
}

export function check(
  paths: readonly string[],
  root: string,
  size: (path: string) => number | null,
): number {
  let failures = 0;
  for (const path of paths) {
    const reason = forbiddenReason(path);
    if (reason !== null) {
      console.error(`forbidden-files: ${path}: ${reason}`);
      failures += 1;
      continue;
    }
    const bytes = size(path);
    if (bytes !== null && bytes > MAX_BYTES) {
      const mib = (bytes / (1024 * 1024)).toFixed(1);
      console.error(
        `forbidden-files: ${path}: ${mib} MiB exceeds the 5 MB limit`,
      );
      failures += 1;
    }
  }
  if (failures > 0) {
    console.error(`forbidden-files: ${failures} forbidden file(s) staged`);
    return 1;
  }
  if (paths.length === 0) {
    console.log("forbidden-files: no files to check");
    return 0;
  }
  console.log(`forbidden-files: ${paths.length} file(s) checked`);
  return 0;
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

function main(argv: readonly string[]): number {
  const root = repositoryRoot();
  if (root === null) {
    console.error("forbidden-files: not inside a Git worktree");
    return 2;
  }
  return check(argv, root, (path) => stagedSize(root, path));
}

if (import.meta.main) {
  process.exit(main(process.argv.slice(2)));
}
