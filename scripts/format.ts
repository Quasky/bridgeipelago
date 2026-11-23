#!/usr/bin/env bun
// Dependency-free text formatter: LF line endings, exactly one final newline,
// and no trailing whitespace outside Markdown (where two spaces can be a break).
import { spawnSync } from "node:child_process";
import { existsSync, lstatSync, readFileSync, writeFileSync } from "node:fs";

const check = process.argv.includes("--check");
// `just fmt <files>` passes the staged files; with none, the whole repository.
const requested = process.argv
  .slice(2)
  .filter((argument) => !argument.startsWith("-"));
const skipped = /(^|\/)(\.git|node_modules|build|target|dist|out|\.gradle|\.local|output|coverage)(\/|$)/;
const binary = /\.(png|jpe?g|gif|ico|webp|jar|zip|gz|xz|bz2|7z|pdf|class|bin|woff2?|ttf|otf|mp3|mp4|ogg|wav)$/i;
const lockfile = /(^|\/)(bun\.lockb?|package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$/;
const ignore = (existsSync(".formatignore")
  ? readFileSync(".formatignore", "utf8")
      .split("\n")
      .map((line) => line.trim().replace(/\/+$/, ""))
      .filter((line) => line.length > 0 && !line.startsWith("#"))
  : []);
const ignored = (file: string) => ignore.some((path) => file === path || file.startsWith(`${path}/`));

const listing = spawnSync("git", ["ls-files", "-z"], { encoding: "buffer" });
if (listing.status !== 0) {
  console.error("format: git ls-files failed");
  process.exit(1);
}

const files =
  requested.length > 0
    ? requested
    : listing.stdout.toString("utf8").split("\0").filter(Boolean);
// .gitattributes can require CRLF (for example Windows batch files); those files
// are checked out with CRLF and must not be rewritten to LF.
const eol = spawnSync("git", ["check-attr", "--stdin", "-z", "eol"], {
  input: files.join("\0"),
});
const crlf = new Set<string>();
if (eol.status === 0) {
  const parts = eol.stdout.toString("utf8").split("\0");
  for (let index = 0; index + 2 < parts.length; index += 3) {
    if (parts[index + 2] === "crlf") crlf.add(parts[index] as string);
  }
}

let problems = 0;
for (const file of files) {
  if (skipped.test(file) || binary.test(file) || lockfile.test(file) || ignored(file)) continue;
  if (crlf.has(file)) continue;
  if (!existsSync(file)) continue;
  if (!lstatSync(file).isFile()) continue;
  const raw = readFileSync(file);
  if (raw.includes(0)) continue;
  const original = raw.toString("utf8");
  let text = original.replace(/\r\n?/g, "\n");
  if (!file.endsWith(".md")) text = text.replace(/[ \t]+$/gm, "");
  text = text.replace(/\n*$/, "\n");
  if (text === original) continue;
  if (check) {
    console.error(`format: needs formatting: ${file}`);
    problems += 1;
  } else {
    writeFileSync(file, text);
  }
}

if (problems > 0) {
  console.error(`format: ${problems} file(s) need formatting; run \`just fmt\``);
  process.exit(1);
}
