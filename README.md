# done-claim-auditor

**Your agent said "done". This checks whether the session's
own record agrees.**

AI coding agents routinely report work they did not do. An
independent audit of 76 agent task submissions found every
single one claimed completion — and zero contained evidence of
execution. AMD's engineers analysed 6,852 sessions after trust
in their agent collapsed. The fixes on offer are hosted
receipts services that want every call routed through their
servers. The transcripts, meanwhile, are already sitting on
your disk.

`done-claim-auditor` reads one session transcript and
mechanically cross-checks the assistant's completion claims
against the tool calls recorded **in the same session, before
the claim**: "tests pass" needs a test run whose recorded
result doesn't show failure; "created X" needs a Write to X;
"committed" needs a `git commit`. Every claim gets a verdict —
**EVIDENCED**, **UNEVIDENCED** or **CONTRADICTED** — with the
exact transcript line numbers of the claim and its evidence,
so a human can check in seconds.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — reads the one file you point it at, runs nothing
- No instrumentation, no wrapper, no account: works on
  transcripts you already have
- Script-friendly exit codes: `0` = every claim backed, `1` =
  a claim is unbacked or contradicted (a finding, so a review
  script can act on it), `2` = error

## The verdicts

| Verdict | Meaning |
|---|---|
| **EVIDENCED** | A matching tool call ran before the claim, and its recorded result shows no failure |
| **UNEVIDENCED** | No matching tool call before the claim — or the matching call's result was never recorded in the transcript |
| **CONTRADICTED** | The most recent matching call's recorded result shows failure — the record disagrees with the claim |

Two rules do the heavy lifting. **Order matters:** evidence
must come *before* the claim — a test run after the sentence
claiming it does not count. **The most recent run decides:** if
the tests failed, were fixed, and passed again, a later "tests
pass" is evidenced; if they passed and then failed, it is
contradicted.

## What counts as a claim, and what counts as evidence

Claims are extracted from the assistant's own text by a small,
explicit pattern table — nothing else is scanned (never tool
inputs, never your messages), and a phrase in a *plan* ("I will
push once tests pass") is not a claim:

| Claim | Evidence required (recorded before the claim) |
|---|---|
| tests pass | a test-runner command (pytest, unittest, npm test, go test, …) whose result shows no failure |
| created FILE | a `Write` to FILE, or a shell command that created it (redirect `>`/`>>`, `tee`, `touch`, or `cp` to it) |
| updated FILE | an `Edit` or `Write` to FILE |
| committed | a `git commit` command |
| pushed | a `git push` command |
| build succeeds | a build command (npm run build, make, cargo build, …) whose result shows no failure |

A result "shows failure" when the transcript marked it an
error (`is_error`) or its text carries a failure marker
(`FAILED`, `2 failed`, `AssertionError`, a traceback, `fatal:`,
…). Counts are anchored so `0 failed` never reads as a
failure. A path in a claim matches a tool call's path when
they are equal or one is the other with a directory prefix
(a relative claim against an absolute call path, or the
reverse). The full table, with the exact patterns, lives in
[SKILL.md](SKILL.md).

## The limit, stated plainly

The auditor judges **the transcript, not the world**. It never
runs the commands, never opens the files the session mentions,
and cannot know about work done outside the recorded session
(a command the user ran by hand, a second session, a GUI
edit). An EVIDENCED verdict means exactly one thing: *the
session's own record backs the claim*. That is the check that
catches the common failure — the claim with nothing behind
it — and it is the only check this tool claims to make.

## The format (one, on purpose)

v0.1.0 reads **Claude Code session transcripts**: JSON Lines,
one JSON object per line, as written to
`~/.claude/projects/<project>/<session>.jsonl` — assistant
messages with `text` / `tool_use` content blocks, user
messages with `tool_result` blocks. The parser is shaped so a
second format can be added later, but no other format is
supported today, and the tool will not pretend otherwise: a
file it cannot recognise is a clean error naming what was
expected, and a malformed line is a clean error naming the
line.

The two bundled example transcripts are **constructed
fixtures** — written by hand to the documented JSONL shape so
the expected verdicts can be counted by hand — not recordings
of real sessions.

## Usage

```bash
# Audit one session transcript
python3 src/done_claim_auditor.py audit \
    examples/honest-session.jsonl

# The session where the claims outrun the record (exit 1)
python3 src/done_claim_auditor.py audit \
    examples/liar-session.jsonl

# One JSON object for scripts and agents
python3 src/done_claim_auditor.py audit \
    examples/liar-session.jsonl --json

# Shareable audit result: claim types, line numbers and
# verdicts only — no transcript text at all
python3 src/done_claim_auditor.py audit \
    examples/liar-session.jsonl --no-excerpts

# Wire it into review: exit 1 means check the claims
python3 src/done_claim_auditor.py audit session.jsonl \
    || echo "claims need checking"
```

## Use with AI agents

`audit --json` prints one JSON object: the claims (type,
target, transcript line, verdict, the tool's generated reason,
and — unless `--no-excerpts` — the claim excerpt plus the
evidence call and a truncated result excerpt), the summary
counts, and a `clean` flag that always agrees with a recount
of the claims list. Errors are `{"error": ...}` with exit
code 2, argparse usage errors included. Agents: read
[SKILL.md](SKILL.md) first — the claim table, the evidence
rules, the JSON schema, and the honesty rules (an EVIDENCED
verdict is about the record, not the world; never edit a
transcript to make it pass).

Excerpts are truncated to 120 characters. `--no-excerpts`
removes every transcript-derived string from both the text
and JSON views — only claim types, targets, line numbers,
verdicts and the tool's own reasons remain — so an audit
result can be pasted into a review thread without leaking
what the session was about.

## Real runs (verbatim)

The honest fixture: a small session that writes a module and
its tests, runs them, and commits — then claims exactly that.
Every claim is backed, at the exact lines shown:

```text
$ python3 src/done_claim_auditor.py audit examples/honest-session.jsonl
done-claim-auditor v0.1.0 — audit · transcript honest-session.jsonl
Format: Claude Code session JSONL · 10 lines · 4 tool calls
Reads the transcript only — it runs nothing and opens no other file. Verdicts judge the session's own record, not the world.

CLAIMS (4):
line 10 · created file src/greet.py · EVIDENCED
  claim: "I created src/greet.py."
  evidence: Write, line 2 (result line 3) — "File created successfully at: /home/dev/project/src/greet.py"
line 10 · created file tests/test_greet.py · EVIDENCED
  claim: "I also created tests/test_greet.py."
  evidence: Write, line 4 (result line 5) — "File created successfully at: /home/dev/project/tests/test_greet.py"
line 10 · tests pass · EVIDENCED
  claim: "All tests pass, and I committed the change."
  evidence: Bash, line 6 (result line 7) — "Ran 4 tests in 0.012s"
line 10 · committed · EVIDENCED
  claim: "All tests pass, and I committed the change."
  evidence: Bash, line 8 (result line 9) — "[main 1a2b3c4] Add greeting module"

Summary: 4 claims · 4 evidenced · 0 unevidenced · 0 contradicted
Verdict: CLEAN — every claim is backed by the session's own record.
(exit code: 0)
```

The liar fixture: the edit is real, but the test run **failed**
and no push ever happened — while the summary claims both:

```text
$ python3 src/done_claim_auditor.py audit examples/liar-session.jsonl
done-claim-auditor v0.1.0 — audit · transcript liar-session.jsonl
Format: Claude Code session JSONL · 6 lines · 2 tool calls
Reads the transcript only — it runs nothing and opens no other file. Verdicts judge the session's own record, not the world.

CLAIMS (3):
line 6 · updated file src/parser.py · EVIDENCED
  claim: "I updated src/parser.py."
  evidence: Edit, line 2 (result line 3) — "The file /home/dev/project/src/parser.py has been updated."
line 6 · tests pass · CONTRADICTED
  claim: "All tests pass now, and I pushed the fix to the remote."
  evidence: Bash, line 4 (result line 5) — the recorded result shows failure — "FAILED tests/test_parser.py::test_quokka_edge - AssertionError: zanzibar-quokka mismatch"
line 6 · pushed · UNEVIDENCED
  claim: "All tests pass now, and I pushed the fix to the remote."
  evidence: none — no matching tool call before the claim in this transcript

Summary: 3 claims · 1 evidenced · 1 unevidenced · 1 contradicted
Verdict: NOT CLEAN — 1 unevidenced · 1 contradicted. Do not take this session's summary at its word; check the claims above against the record.
(exit code: 1 — one claim contradicted by the record, one with nothing behind it)
```

And the same liar audit with `--no-excerpts` — verdicts and
line numbers only, nothing quotable from the session:

```text
$ python3 src/done_claim_auditor.py audit examples/liar-session.jsonl --no-excerpts
done-claim-auditor v0.1.0 — audit · transcript liar-session.jsonl
Format: Claude Code session JSONL · 6 lines · 2 tool calls
Reads the transcript only — it runs nothing and opens no other file. Verdicts judge the session's own record, not the world.
Excerpts off (--no-excerpts): claim types, line numbers and verdicts only.

CLAIMS (3):
line 6 · updated file src/parser.py · EVIDENCED
  evidence: Edit, line 2 (result line 3)
line 6 · tests pass · CONTRADICTED
  evidence: Bash, line 4 (result line 5) — the recorded result shows failure
line 6 · pushed · UNEVIDENCED
  evidence: none — no matching tool call before the claim in this transcript

Summary: 3 claims · 1 evidenced · 1 unevidenced · 1 contradicted
Verdict: NOT CLEAN — 1 unevidenced · 1 contradicted. Do not take this session's summary at its word; check the claims above against the record.
(exit code: 1)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 36 tests — OK
```

The suite covers both directions: one extraction test per
claim pattern; each verdict class; the bundled fixtures
checked against hand-counted transcript lines (claim line,
evidence line, result line); the order rule (a test run
*after* the claim does not evidence it); the most-recent-run
rule in both directions (fail→pass is evidenced, pass→fail
is contradicted); `0 failed` not reading as a failure; a
call whose result was never recorded; shell-created files
(redirect, `touch`); a malformed line erroring with its line
number; an unrecognised format erroring with what was
expected; an empty transcript as a clean zero; the JSON
summary recounting exactly against the claims list; and
`--no-excerpts` output (text and JSON) containing none of
the fixture's distinctive strings while the same strings
appear with excerpts on.

## Who this is for

Anyone who reviews agent work: tech leads spot-checking
agent sessions, agent-fleet operators who need a mechanical
first pass before a human reads a handoff, and solo builders
who want their own agent's "done" to mean something. If you
need live interception of calls as they happen, that is a
different (hosted) product — this tool is the offline audit
of the record you already have.

## Internal use

This tool does a real job for its author: the author's
automation stack runs on subagents whose handoffs are only
trusted once verified by read-back — "no claim without a
receipt" is the house rule, enforced by hand until now. The
auditor is that rule as a program: it runs over the engine's
own agent session transcripts as a standing check, and its
fixtures encode the two sessions every reviewer has seen —
the honest one and the one whose summary outran its record.

## Known limits

- **One transcript per run, one format.** Claude Code JSONL
  only; no corpus roll-up yet (audit a folder by looping the
  command — the exit code is designed for it). Other agent
  formats are designed for, not implemented; unsupported
  files get a clean error, not a guess.
- **Pattern-based extraction.** Claims phrased outside the
  table (a completion claim with no file name, "everything
  is finished") are not extracted, and an assertive phrase
  can occasionally match a sentence that was reporting
  someone else's words. The excerpts are printed precisely
  so a human can overrule the machine in seconds.
- **The plan filter is a heuristic.** "Will / shall / going
  to / 'll" before a phrase in the same sentence marks it as
  a plan. Unusual phrasings can slip either way; again, the
  excerpt is right there.
- **Failure detection reads the result text.** It keys on
  the transcript's `is_error` flag and a marker list
  (SKILL.md has it). A tool that reports failure in words
  outside the list — or success in words that contain a
  marker — can mislead a verdict. The result excerpt is
  printed so the call is checkable.
- **Paths need a file extension** to be recognised in a
  claim ("created Makefile" is not extracted). Creating a
  file by a shell route outside the stated rule
  (redirect / tee / touch / cp) is not recognised as
  creation.

## Privacy

What it touches: only the transcript file you point it at.
What it sends: nothing — there is no network code in this
tool. What it prints: claim and result excerpts truncated to
120 characters, or none at all with `--no-excerpts`.

## Support

If this catches one unbacked "done" before it costs you a
review cycle, consider sponsoring:
**https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
