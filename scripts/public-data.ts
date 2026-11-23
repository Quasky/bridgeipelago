#!/usr/bin/env bun
/**
 * Owner hook job `owner-public-data` (standards/owner.md `## Git hooks`).
 *
 * In a public repository, block a staged file that carries an instance value:
 * a personal host path, an IP address, a world seed, world coordinates, or a
 * server or instance id. Only the rule label and the path are printed; the
 * matched value never is. Private repositories allow instance values, so their
 * `public-data-staged` recipe exits 0 without running this scan.
 *
 * The scan is a conservative heuristic, not proof: `just check` and review
 * still apply. `--all` scans the committed tree, for a pre-publication look.
 *
 * Usage: bun scripts/public-data.ts [--staged|--all]
 */

import { spawnSync } from "node:child_process";

/** Text larger than this is not an instance value; `forbidden-files` covers size. */
const MAX_BYTES = 2 * 1024 * 1024;

/**
 * Deliberately public material, reviewed before it was committed:
 * - `.secrets/revealed/` holds the session artifacts `archipelago` publishes.
 * - `automation/seeds.txt` is the curated, replayable test-world seed list.
 */
const PUBLIC_PATHS = [".secrets/revealed/", "automation/seeds.txt"];

/** Coordinates only make sense in data and prose, not in source code. */
const TEXT_EXTENSIONS = new Set([
  "",
  ".cfg",
  ".conf",
  ".csv",
  ".env",
  ".example",
  ".ini",
  ".json",
  ".jsonc",
  ".markdown",
  ".md",
  ".properties",
  ".template",
  ".toml",
  ".tsv",
  ".txt",
  ".yaml",
  ".yml",
]);

const HOME_POSIX =
  /(?<![A-Za-z0-9._-])\/(?:home|Users)\/(?!<|\$|example\b|user\b|username\b|you\b|person\b|Public\b|Default\b|Shared\b|runner\b)[A-Za-z0-9._-]+/u;

const HOME_WINDOWS =
  /[A-Za-z]:\\+Users\\+(?!<|\$|example\b|user\b|username\b|you\b|person\b|Public\b|Default\b|Shared\b)[A-Za-z0-9._-]+/u;

const IPV4 = /(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9.])/gu;

const IPV6 =
  /(?<![0-9A-Za-z:])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f:]{0,20}(?:%[A-Za-z0-9._-]+)?(?![0-9A-Za-z:])/gu;

const SEED =
  /(?:^|[^A-Za-z0-9_-])(?:level[-_]?seed|seed[-_]?name|seed)[ \t]*[:=][ \t]*["']?([^\s"',;#]+)/giu;

const COORDINATES =
  /\bx[ \t]*[:=][ \t]*(-?\d{1,8})\b[^\n]{0,40}?\by[ \t]*[:=][ \t]*(-?\d{1,8})\b[^\n]{0,40}?\bz[ \t]*[:=][ \t]*(-?\d{1,8})\b/giu;

const UUID =
  /(?<![0-9A-Fa-f-])[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f-])/gu;

/** A documented placeholder, not an instance value. */
const PLACEHOLDER =
  /^(?:<|\$|\{|CHANGE[-_]?ME|example|sample|your|test|tbd|todo|none|null|unknown|placeholder|redacted|hidden|\.{3})/iu;

/** Loopback, unspecified and the RFC 5737 documentation ranges are placeholders. */
function ipv4IsPlaceholder(value: string): boolean {
  const parts = value.split(".").map(Number);
  if (parts.length !== 4) return true;
  if (parts.some((part) => !Number.isInteger(part) || part > 255)) return true;
  const [first, second, third] = parts as [number, number, number, number];
  if (first === 127) return true;
  if (value === "0.0.0.0" || value === "255.255.255.255") return true;
  if (first === 192 && second === 0 && third === 2) return true;
  if (first === 198 && second === 51 && third === 100) return true;
  if (first === 203 && second === 0 && third === 113) return true;
  return false;
}

/** Loopback, unspecified and the documentation prefix are placeholders. */
function ipv6IsPlaceholder(value: string): boolean {
  const address = (value.split("%")[0] ?? value).toLowerCase();
  if (address === "::" || address === "::1") return true;
  if (address === "2001:db8" || address.startsWith("2001:db8:")) return true;
  const halves = address.split("::");
  if (halves.length > 2) return true;
  const groups = [
    ...(halves[0] ?? "").split(":").filter(Boolean),
    ...(halves[1] ?? "").split(":").filter(Boolean),
  ];
  // Six two-digit groups without `::` are a hardware address, not an IP.
  if (
    halves.length === 1 &&
    groups.length === 6 &&
    groups.every((group) => group.length === 2)
  ) {
    return true;
  }
  if (halves.length === 1 && groups.length !== 8) return true;
  if (halves.length === 2 && groups.length > 7) return true;
  return !groups.every(
    (group) =>
      /^[0-9a-f]{1,4}$/u.test(group) ||
      /^(?:\d{1,3}\.){3}\d{1,3}$/u.test(group),
  );
}

function seedIsFinding(value: string): boolean {
  if (value.length === 0 || PLACEHOLDER.test(value)) return false;
  if (/^-?\d{3,}$/u.test(value)) return true;
  return /^[A-Za-z0-9_-]{12,}$/u.test(value);
}

function coordinateIsFinding(match: RegExpExecArray): boolean {
  const x = Number(match[1]);
  const y = Number(match[2]);
  const z = Number(match[3]);
  if (x === 0 && y === 0 && z === 0) return false;
  if (y < -64 || y > 320) return false;
  return Math.abs(x) <= 30_000_000 && Math.abs(z) <= 30_000_000;
}

/** Synthetic ids (`1111…`, all zeros) are placeholders. */
function uuidIsFinding(value: string): boolean {
  const hex = value.replace(/-/gu, "").toLowerCase();
  if (/^0+$/u.test(hex)) return false;
  const first = hex[0];
  return ![...hex].every((character) => character === first);
}

function extension(name: string): string {
  const base = name.slice(name.lastIndexOf("/") + 1);
  if (base.startsWith(".env")) return ".env";
  const dot = base.lastIndexOf(".");
  return dot <= 0 ? "" : base.slice(dot).toLowerCase();
}

function scanText(text: string, name: string): Set<string> {
  const labels = new Set<string>();
  if (HOME_POSIX.test(text) || HOME_WINDOWS.test(text)) {
    labels.add("personal host path");
  }
  IPV4.lastIndex = 0;
  for (const match of text.matchAll(IPV4)) {
    if (!ipv4IsPlaceholder(match[0])) {
      labels.add("IP address");
      break;
    }
  }
  IPV6.lastIndex = 0;
  for (const match of text.matchAll(IPV6)) {
    if (!ipv6IsPlaceholder(match[0])) {
      labels.add("IP address");
      break;
    }
  }
  SEED.lastIndex = 0;
  for (const match of text.matchAll(SEED)) {
    if (seedIsFinding(match[1] ?? "")) {
      labels.add("world seed");
      break;
    }
  }
  if (TEXT_EXTENSIONS.has(extension(name))) {
    COORDINATES.lastIndex = 0;
    for (const match of text.matchAll(COORDINATES)) {
      if (coordinateIsFinding(match)) {
        labels.add("world coordinates");
        break;
      }
    }
  }
  UUID.lastIndex = 0;
  for (const match of text.matchAll(UUID)) {
    if (uuidIsFinding(match[0])) {
      labels.add("server or instance id");
      break;
    }
  }
  return labels;
}

interface Entry {
  name: string;
  mode: string;
  object: string;
}

function git(root: string, args: string[]): Buffer | null {
  const result = spawnSync("git", ["-C", root, ...args], {
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (result.status !== 0) return null;
  return result.stdout;
}

function parseEntries(data: Buffer): Entry[] {
  const entries: Entry[] = [];
  for (const record of data.toString("utf8").split("\0")) {
    if (record.length === 0) continue;
    const tab = record.indexOf("\t");
    if (tab === -1) continue;
    const fields = record.slice(0, tab).split(" ");
    const [mode, second, third] = fields;
    if (mode === undefined || second === undefined) continue;
    // `ls-files --stage` prints mode, object, stage; `ls-tree` prints mode,
    // type, object. The middle field tells them apart.
    const object = /^[0-9a-f]{40,64}$/u.test(second) ? second : third;
    if (object === undefined) continue;
    entries.push({ mode, object, name: record.slice(tab + 1) });
  }
  return entries;
}

/** Only the blobs this commit would add or change, not the whole index. */
function stagedEntries(root: string): Entry[] | null {
  const names = git(root, [
    "diff",
    "--cached",
    "--name-only",
    "--diff-filter=ACMR",
    "-z",
  ]);
  if (names === null) return null;
  const changed = new Set(names.toString("utf8").split("\0").filter(Boolean));
  const data = git(root, ["ls-files", "--stage", "-z"]);
  if (data === null) return null;
  return parseEntries(data).filter((entry) => changed.has(entry.name));
}

function committedEntries(root: string): Entry[] | null {
  const data = git(root, ["ls-tree", "-rz", "--full-tree", "HEAD"]);
  return data === null ? null : parseEntries(data);
}

function isText(data: Buffer): boolean {
  if (data.length > MAX_BYTES) return false;
  if (data.includes(0)) return false;
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(data);
    return true;
  } catch {
    return false;
  }
}

function scan(entries: readonly Entry[], root: string): number {
  let failures = 0;
  for (const entry of entries) {
    if (entry.mode !== "100644" && entry.mode !== "100755") continue;
    if (PUBLIC_PATHS.some((path) => entry.name.includes(path))) continue;
    const blob = git(root, ["cat-file", "blob", entry.object]);
    if (blob === null || !isText(blob)) continue;
    const labels = scanText(blob.toString("utf8"), entry.name);
    if (labels.size === 0) continue;
    failures += 1;
    console.error(
      `public-data: ${entry.name}: ${[...labels].sort().join(", ")}`,
    );
  }
  if (failures > 0) {
    console.error(
      `public-data: ${failures} file(s) carry an instance value; replace it with a placeholder.`,
    );
    return 1;
  }
  console.log("public-data: no instance values in the scanned files");
  return 0;
}

function main(argv: readonly string[]): number {
  const all = argv.includes("--all");
  const rootResult = spawnSync("git", ["rev-parse", "--show-toplevel"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (rootResult.status !== 0) {
    console.error("public-data: not inside a Git worktree");
    return 2;
  }
  const root = (rootResult.stdout ?? "").trim();
  const entries = all ? committedEntries(root) : stagedEntries(root);
  if (entries === null) {
    console.error("public-data: could not list the files to scan");
    return 2;
  }
  return scan(entries, root);
}

if (import.meta.main) {
  process.exit(main(process.argv.slice(2)));
}
