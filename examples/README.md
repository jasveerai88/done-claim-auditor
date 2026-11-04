# Examples

Two **constructed fixtures** — written by hand to the
documented Claude Code JSONL shape so the expected
verdicts can be counted by hand. They are **not**
recordings of real sessions, and they are labelled
that way everywhere they are used.

## honest-session.jsonl (10 lines, 4 tool calls)

A small session that writes a module and its tests,
runs them, and commits — then claims exactly that.

```bash
done-claim-auditor audit examples/honest-session.jsonl
# 4 claims · 4 evidenced · 0 unevidenced · 0 contradicted
# Verdict: CLEAN (exit 0)
```

## liar-session.jsonl (6 lines, 2 tool calls)

The edit is real, but the test run **failed** and no
push ever happened — while the summary claims both.

```bash
done-claim-auditor audit examples/liar-session.jsonl
# line 6 · updated file src/parser.py · EVIDENCED
# line 6 · tests pass · CONTRADICTED
# line 6 · pushed · UNEVIDENCED
# Verdict: NOT CLEAN (exit 1)
```

Try `--json` for the same audit as one object, and
`--no-excerpts` for the shareable view with no
transcript text in it.
