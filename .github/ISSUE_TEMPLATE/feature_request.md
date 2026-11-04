---
name: Claim-pattern or feature request
about: A completion-claim phrasing the table misses, or an evidence rule that should exist
title: ""
labels: enhancement
assignees: ""
---

**The gap**
What does the agent's text look like that
done-claim-auditor currently misses or misjudges? Quote
the exact phrasing (from a fixture, or with real session
content redacted — never paste private transcript text).

**The evidence rule**
If the claim were extracted, what recorded tool call
would prove it, and what in that call's recorded result
would show failure? Verdicts derive from the session's
own record by explicit rules — a request must name the
rule, not a heuristic ("the agent sounded confident" is
not evidence and never will be).

**Suggested verdict behaviour**
If you have one: which verdict should the phrasing get
in which situation. Both directions matter — what must
be flagged, and what must *not* be flagged (a plan —
"I will push once tests pass" — is not a claim, and
flagging plans as lies would be its own falsehood).

**Out of scope, so it is said once**
Requests to verify the world instead of the record
(run the tests, open the files, call an API), to add a
second transcript format without its own parser,
fixtures and detection rule, or to soften a verdict
because the claim "was probably true" will not be
taken — judging the transcript, and only the
transcript, is the entire design.
