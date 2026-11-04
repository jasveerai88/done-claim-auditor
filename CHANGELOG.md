# Changelog

## v1.0.0 — 2026-11-04

The claim table, the evidence rules, and the verdicts
are unchanged from v0.1.0 — this release is about
being installable and readable as a product:

- **Packaged install.** `pyproject.toml` (setuptools,
  single-module layout) — `pip install
  done-claim-auditor` / `pipx install
  done-claim-auditor` now put a `done-claim-auditor`
  console command on PATH. `python3
  src/done_claim_auditor.py` from a checkout keeps
  working, unchanged, with byte-identical output.
- **README rebuilt as a landing page:** one-line hook,
  badge row, an animated demo (the liar session's
  claims contradicted and unevidenced by its own
  transcript, then the honest session's four claims
  all evidenced), a 20-second quickstart, the bundled
  fixtures judged in a table, and a comparison table
  against trusting the summary, hosted receipts
  services, and reading transcripts by eye. The full
  reference — verdict rules, the claim and evidence
  tables, verbatim runs, known limits — moved below
  the fold.
- **Demo + social assets** in `docs/`: `demo.gif`
  (rendered from real v1.0.0 output) and
  `social-preview.png` (1280×640).
- **Community files:** SECURITY.md and issue templates
  added; CONTRIBUTING and FUNDING unchanged.
- Version string is now 1.0.0 everywhere (tool header,
  `--json` output, package metadata). All 36 tests
  pass unmodified — the only source changes are the
  version strings.

## v0.1.0 — 2026-11-04

First release.

- **One command, `audit`** — reads a single Claude Code
  session transcript (JSON Lines: assistant messages with
  `text`/`tool_use` blocks, user messages with `tool_result`
  blocks, as written under `~/.claude/projects/`) and checks
  the assistant's completion claims against the tool calls
  recorded in the same session. That is the only format
  v0.1.0 supports, and the parser says so: a file it cannot
  recognise is a clean error naming what was expected, and a
  malformed line is a clean error naming the line — never a
  guess, never silent partial credit.
- **A small, explicit claim table** — six claim types
  extracted from assistant text only (never tool inputs,
  never user text): *tests pass*, *created FILE*, *updated
  FILE*, *committed*, *pushed*, *build succeeds*. A phrase
  preceded in its sentence by a plan marker (will / shall /
  going to / 'll …) is a plan, not a claim, and is skipped.
  File claims need a path with a dot-extension.
- **Mechanical evidence rules** — a claim is matched to the
  most recent candidate call recorded **before** it: a
  test-runner command for *tests pass*; a `Write` (or a
  redirect / `tee` / `touch` / `cp` shell creation) for
  *created*; an `Edit` or `Write` for *updated*; `git
  commit` / `git push` commands for *committed* / *pushed*;
  a build command for *build succeeds*. Relative and
  absolute spellings of the same path match.
- **Three verdicts** — **EVIDENCED** (a matching call ran
  and its recorded result shows no failure),
  **CONTRADICTED** (the most recent matching call's recorded
  result shows failure — the `is_error` flag or a failure
  marker such as `FAILED`, `2 failed`, `AssertionError`, a
  traceback; counts are anchored so `0 failed` is not a
  failure), **UNEVIDENCED** (no matching call before the
  claim, or its result was never recorded). Each claim is
  reported with the real transcript line numbers of the
  claim, the evidence call and its result.
- **The limit, in the output and the docs** — the auditor
  judges the transcript, not the world: it runs nothing,
  opens nothing else, and an EVIDENCED verdict means only
  that the session's own record backs the claim.
- **`--json` on the command** — one JSON object with the
  claims, their verdicts and evidence lines, a summary that
  recounts exactly against the claims list, and a `clean`
  flag; errors are `{"error": ...}` objects, argparse usage
  errors included.
- **`--no-excerpts`** — prints only claim types, targets,
  line numbers, verdicts and the tool's own reasons, in
  text and JSON alike, so an audit result can be shared
  without leaking transcript content. Default excerpts are
  truncated to 120 characters.
- **Exit codes for review scripts** — 0 when every claim is
  backed (or none were made), 1 when any claim is
  unevidenced or contradicted, 2 on error.
- **`SKILL.md`** at the repo root for AI coding agents: the
  full claim-pattern table, the evidence rules including
  the failure-marker list, the JSON schema, exit codes,
  and the honesty rules (verdicts are about the record;
  never edit a transcript to pass).
- Bundled constructed fixtures (`examples/`): an honest
  session whose 4 claims are all evidenced at hand-counted
  lines, and a "liar" session whose 3 claims split 1
  evidenced / 1 contradicted / 1 unevidenced — written by
  hand to the documented JSONL shape and labelled as
  fixtures, not real sessions.
- 36 stdlib-unittest tests: per-pattern extraction, every
  verdict class, hand-counted fixture line numbers, the
  order rule, the most-recent-run rule in both directions,
  `0 failed`, unrecorded results, shell-created files,
  malformed-line and unrecognised-format errors, the JSON
  recount, and `--no-excerpts` leak checks in both modes.
- Pure Python standard library; local only; reads one file
  and executes nothing in it; MIT licence.
