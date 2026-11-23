#!/usr/bin/env bun
/**
 * Warn when a commit subject is not a Conventional Commit (core.md C2.4).
 * The `commit-msg` recipe is advisory by contract (C7.9): it always exits 0 and
 * never blocks a commit. The subject is content; nothing else is read.
 */

import { readFileSync } from "node:fs";

const TYPES = "feat|fix|docs|chore|refactor|perf|test|build|ci|revert";

/** `type(scope)?!?: lowercase imperative summary`; the period rule is separate. */
const SUBJECT = new RegExp(
  `^(?:${TYPES})(?:\\([a-z0-9][a-z0-9._/-]*\\))?!?: [a-z0-9][^\\n]*$`,
  "u",
);

/** The first content line: blanks and comment lines are skipped. */
export function subjectOf(message: string): string | null {
  for (const line of message.split("\n")) {
    const value = line.trim();
    if (value.length === 0) continue;
    if (value.startsWith("#")) continue;
    return value;
  }
  return null;
}

export function isConventional(subject: string): boolean {
  return SUBJECT.test(subject) && !subject.endsWith(".");
}

function main(argv: readonly string[]): number {
  const file = argv[0];
  if (file === undefined) {
    console.error("usage: commit-msg.ts <message-file>");
    return 0;
  }
  let subject: string | null;
  try {
    subject = subjectOf(readFileSync(file, "utf8"));
  } catch {
    console.error(
      `commit-msg: could not read ${file}; skipping the advisory check.`,
    );
    return 0;
  }
  if (subject === null) return 0;
  if (!isConventional(subject)) {
    console.error(
      `commit-msg: "${subject}" is not a Conventional Commit (C2.4).`,
    );
    console.error(
      "commit-msg: expected `type(scope)?: lowercase imperative summary`, no trailing period.",
    );
    console.error("commit-msg: advisory only; the commit continues.");
  }
  return 0;
}

if (import.meta.main) {
  process.exit(main(process.argv.slice(2)));
}
