---
name: Bug report
about: A crash, a wrong verdict, or a claim that was judged against the wrong evidence
title: ""
labels: bug
assignees: ""
---

**What happened**
A clear description of the bug — the command you ran and
what done-claim-auditor reported.

**What you expected**
The verdict you expected instead, and the transcript facts
that support it (the claim's line, the matching call's line,
and what its recorded result actually says).

**The fixture**
A minimal transcript that reproduces it. The bundled
examples (examples/honest-session.jsonl,
examples/liar-session.jsonl) show the shape — a few lines of
JSONL are usually enough. Redact anything private; the
verdict must still reproduce. If the report involves real
session content, run the audit with --no-excerpts and paste
that output instead of transcript text.

**Environment**
Python version and how you run the tool (installed command
or `python3 src/done_claim_auditor.py`).
