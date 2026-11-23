#!/usr/bin/env bun
// Verify the agent-file layout: .agents/skills/<name>/SKILL.md is canonical,
// .claude/skills/<name> is a relative symlink to it, frontmatter is present,
// and every `just <recipe>` a skill names exists in the justfile.
import { existsSync, lstatSync, readFileSync, readdirSync, readlinkSync, statSync } from "node:fs";
import { join } from "node:path";

const canonical = join(process.cwd(), ".agents", "skills");
const claude = join(process.cwd(), ".claude", "skills");
const isDir = (path: string) => existsSync(path) && statSync(path).isDirectory();
const entries = (path: string) => (isDir(path) ? readdirSync(path).sort() : []);

const recipes = new Set<string>();
if (existsSync("justfile")) {
  for (const line of readFileSync("justfile", "utf8").split("\n")) {
    if (line.startsWith("export ") || line.startsWith("set ") || line.startsWith("#")) continue;
    const match = /^@?([a-z][a-z0-9-]*)(?:\s+[^:]*)?:/.exec(line);
    if (match) recipes.add(match[1] as string);
  }
}

let failed = false;
const skills = entries(canonical).filter((name) => isDir(join(canonical, name)));

for (const name of skills) {
  const skillFile = join(canonical, name, "SKILL.md");
  if (!existsSync(skillFile)) {
    console.error(`agent-files: missing ${skillFile}`);
    failed = true;
    continue;
  }
  const text = readFileSync(skillFile, "utf8");
  const frontmatter = /^---\n([\s\S]*?)\n---/.exec(text)?.[1] ?? "";
  if (!/^name:\s*\S/m.test(frontmatter) || !/^description:\s*\S/m.test(frontmatter)) {
    console.error(`agent-files: ${skillFile} needs name and description frontmatter`);
    failed = true;
  }
  for (const [, recipe] of text.matchAll(/`just ([a-z][a-z0-9-]*)/g)) {
    if (!recipes.has(recipe as string)) {
      console.error(`agent-files: ${skillFile} names missing recipe ${recipe}`);
      failed = true;
    }
  }

  const link = join(claude, name);
  if (!existsSync(link)) {
    console.error(`agent-files: missing .claude/skills/${name} symlink`);
    failed = true;
  } else if (!lstatSync(link).isSymbolicLink()) {
    console.error(`agent-files: .claude/skills/${name} is not a symlink`);
    failed = true;
  } else if (readlinkSync(link) !== `../../.agents/skills/${name}`) {
    console.error(`agent-files: .claude/skills/${name} points at ${readlinkSync(link)}`);
    failed = true;
  }
}

for (const name of entries(claude)) {
  if (!skills.includes(name)) {
    console.error(`agent-files: .claude/skills/${name} has no canonical skill`);
    failed = true;
  }
}

if (failed) process.exit(1);
console.log(`agent-files: ${skills.length} skill(s) linked`);
