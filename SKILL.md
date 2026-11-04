---
name: done-claim-auditor
description: Audit one Claude Code session transcript (JSONL) by mechanically matching the assistant's completion claims — "tests pass", "created FILE", "updated FILE", "committed", "pushed", "build succeeds" — against the tool calls recorded in the same transcript before each claim, verdicting each claim EVIDENCED, UNEVIDENCED or CONTRADICTED with exact transcript line numbers. Use when reviewing agent work, spot-checking a session, or gating a handoff on evidence instead of the agent's summary. It reads one local file, runs nothing, and judges the transcript only — never the world. Exit 1 means a claim is unbacked or contradicted — it is a finding, not a failure.
---

# done-claim-auditor — agent skill

## Purpose

Agents claim work they did not do: tests "passing" that
never ran, files "created" that no Write touched, pushes
that exist only in the summary. This tool is the mechanical
first pass over the record that already exists — the session
transcript. It extracts the assistant's completion claims
and matches each one against the tool calls recorded in the
same transcript **before** the claim, then reads the most
recent matching call's recorded result. Pure Python standard
library; local only; the transcript file named on the command
line is the only thing it reads, and it executes nothing it
finds there.

**The honesty core of this tool:** a verdict is a statement
about *the transcript*, never about the world. EVIDENCED
means "the session's own record backs the claim" — the file
may still not exist, the tests may still fail when a human
runs them. Never relay a verdict as proof the work is real,
and never edit a transcript to make it pass: that destroys
the record the tool exists to check.

## When to use / not use

Use when:
- Reviewing an agent session or a subagent handoff and you
  want the claims checked before you read the prose.
- Gating a workflow: `audit` exit 1 = at least one claim
  needs a human look; exit 0 = every extracted claim is
  backed by the record.
- Sharing an audit result in a thread — with `--no-excerpts`,
  so no transcript content leaks.

Do NOT use when:
- You need ground truth about the work itself. Run the
  tests, read the files, check the remote — the auditor is
  the triage, not the verification.
- The transcript is not Claude Code JSONL. v1.0.0 supports
  exactly that one format; anything else is a clean error,
  not a partial audit.
- You want live interception of tool calls as they happen.
  That is a hosted/wrapper product; this is an offline audit.

## Commands

```bash
# Audit one transcript (text view)
done-claim-auditor audit TRANSCRIPT.jsonl

# One JSON object, same verdicts and exit codes
done-claim-auditor audit TRANSCRIPT.jsonl --json

# Types, line numbers and verdicts only — no transcript text
done-claim-auditor audit TRANSCRIPT.jsonl --no-excerpts
done-claim-auditor audit TRANSCRIPT.jsonl --json --no-excerpts
```

Installed with `pipx install git+https://github.com/jasveerai88/done-claim-auditor` (or
`pip install git+https://github.com/jasveerai88/done-claim-auditor`). From a source
checkout, `python3 src/done_claim_auditor.py audit …`
is the same command with the same output.

Transcripts live at `~/.claude/projects/<project>/<session>.jsonl`.
There are no other commands and no configuration file.

## The claim-pattern table (complete)

Claims are extracted from **assistant text blocks only** —
never from tool inputs, tool results or user messages. A
phrase preceded in its sentence by a plan marker (`will`,
`shall`, `going to`, `plan(s|ning) to`, `about to`, or an
`'ll` contraction) is a plan, not a claim, and is skipped.
Patterns are case-insensitive.

| # | Type (`type`) | Label | Matched phrasing |
|---|---|---|---|
| 1 | `tests_pass` | tests pass | "tests pass / passing / passed / are green", "all N tests pass…", "test suite passes / is green", "every test passes" |
| 2 | `file_created` | created file | "created / wrote [the / a / new] [file] PATH", "new file PATH" |
| 3 | `file_updated` | updated file | "updated / edited / modified / patched [the] [file] PATH" |
| 4 | `committed` | committed | the word "committed" |
| 5 | `pushed` | pushed | the word "pushed" |
| 6 | `build_succeeds` | build succeeds | "build succeeds / succeeded / passes / passed / is green / successful", "compiles cleanly / successfully", "compilation succeeds" |

PATH is a file path containing a dot-extension
(`src/greet.py`, `docs/guide.md`). A path with no extension
("created Makefile") is **not** extracted. The claim's
`target` is the path as written, with surrounding punctuation
stripped.

## The evidence rules (complete)

For each claim, only calls recorded **before** the claim's
line are candidates, and the **most recent** candidate
decides the verdict.

| Claim type | Candidate calls |
|---|---|
| `tests_pass` | `Bash` whose command matches a test runner: pytest, `python -m pytest/unittest`, a `test*.py` script run, `npm/yarn/pnpm test`, `go test`, `cargo test`, `mvn test/verify`, `gradle test/check`, jest, vitest, mocha, rspec, phpunit, ctest, tox, nose |
| `file_created` | `Write` to the target path; or `Bash` that creates it — a redirect (`>` or `>>`) into it, `tee` into it, `touch` on it, or `cp` with it as the destination |
| `file_updated` | `Edit` or `Write` to the target path |
| `committed` | `Bash` whose command contains `git commit` |
| `pushed` | `Bash` whose command contains `git push` |
| `build_succeeds` | `Bash` whose command matches a build: `npm/yarn/pnpm … build`, `make`, `cargo build`, `go build`, `tsc`, `mvn package/install/compile`, `gradle build`, `cmake --build`, `python -m build`, `msbuild`, `dotnet build` |

**Path matching:** a claim's path matches a call's path when
they are equal after stripping quotes and leading `./`, or
when one is the other with a leading directory prefix
(relative claim vs absolute call path, or the reverse).

**Failure:** the candidate's recorded result shows failure
when the transcript marked it `is_error`, or its text
contains any of: a Python traceback header, `FAILED`,
`FAILURES`, `N failed` for N ≥ 1, `failures=N` / `errors=N`
for N ≥ 1, `AssertionError`, `BUILD FAILURE`, `fatal:`,
`exit code N` for N ≥ 1, `[rejected]`, `error:`. Anchored
counts mean `0 failed` is **not** a failure.

**Verdicts:** candidate exists and its result shows no
failure → **EVIDENCED**. Candidate exists and its result
shows failure → **CONTRADICTED**. No candidate before the
claim → **UNEVIDENCED**. A candidate whose result was never
recorded (the transcript ends first) → **UNEVIDENCED**, with
the reason saying so.

## Output JSON schema (`--json`)

One object: `tool` (`"done-claim-auditor"`), `version`,
`command` (`"audit"`), `transcript` (file name only),
`format` (`"claude-code-jsonl"`), `lines` (physical lines in
the file), `tool_calls` (tool_use blocks found), `excerpts`
(bool — false under `--no-excerpts`), `claims`, `summary`,
`clean`.

Each claim: `type`, `label`, `target` (path or null),
`line` (the transcript line of the assistant message),
`verdict` (`EVIDENCED` / `UNEVIDENCED` / `CONTRADICTED`),
`reason` (a sentence generated by the tool), `evidence`
(null, or `{tool, line, result_line}` — the tool-call line
and the line of its recorded result, either possibly the
same session's real JSONL line numbers), and, only when
excerpts are on, `excerpt` (the claim's sentence, ≤ 120
chars) plus evidence `detail` (the call's command or path)
and `result_excerpt` (first non-empty line of the recorded
result, ≤ 120 chars).

`summary`: `{claims, evidenced, unevidenced, contradicted}`
— guaranteed to recount exactly against the `claims` list.
`clean` is true iff unevidenced and contradicted are both 0.

On error, stdout is a single object: `{"error": "<message>"}`
with exit code 2 — including argparse usage errors in
`--json` mode. Never plain text, never a traceback.

## Exit codes

- `0` — every extracted claim is EVIDENCED, or there were
  no claims.
- `1` — at least one claim is UNEVIDENCED or CONTRADICTED.
  This is the tool working — surface the flagged claims,
  with their line numbers, to the reviewer.
- `2` — ERROR: transcript missing or unreadable, a line that
  is not valid JSON (the message names the line), a line
  that is not a JSON object, or a file that does not look
  like a Claude Code transcript (the message names what was
  expected). No verdicts exist for a failed run; do not
  quote counts from one.

## Limits & honesty rules the agent must respect

- **Verdicts are about the record, not the world.** Report
  an EVIDENCED claim as "backed by the session's own
  record", never as "verified done". If the work matters,
  verify it for real: run the tests, read the files, fetch
  the remote state.
- **Never edit a transcript to change a verdict.** The
  transcript is evidence. If a claim is wrongly flagged,
  the fix is to say so in your review, next to the flag —
  or to improve the pattern table in the open, with tests.
- **Absence of claims is not absence of lying.** Extraction
  is pattern-based: a completion claim phrased outside the
  table (no file name, unusual wording) is not extracted,
  and a clean audit of a claim-free summary says nothing.
  Read the session's final message yourself when it matters.
- **Work outside the session is invisible.** A test the
  user ran by hand, a file edited in a GUI, a second
  session — none of it is in the record, so claims about it
  will read UNEVIDENCED. That is the tool being literal,
  not the agent being caught; say which when you relay it.
- **`--no-excerpts` for anything shared.** Transcripts can
  contain anything the session touched. When an audit result
  leaves the machine (a PR comment, a ticket), use
  `--no-excerpts` so only types, line numbers and verdicts
  travel.
- Local only, executes nothing: the tool reads only the
  file named on the command line. It never runs commands
  found in a transcript — a transcript is data, and hostile
  data at that if the session was working on untrusted code.
