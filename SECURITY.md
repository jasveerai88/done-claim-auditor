# Security

## done-claim-auditor's own posture

done-claim-auditor is an audit tool, and its own attack
surface is deliberately minimal:

- **It executes nothing it reads.** A transcript is
  untrusted data — sessions work on hostile code, and a
  transcript can contain anything the session touched.
  The auditor parses the file as JSON text and pattern-
  matches strings; it never evaluates transcript content,
  never runs a command a transcript mentions, and never
  opens a file a transcript mentions. The one file it
  reads is the one named on the command line.
- **No network code.** The tool makes no network calls,
  has no telemetry, and sends nothing anywhere. There
  is no supply chain beyond Python itself: standard
  library only, zero dependencies.
- **Output is data, not instructions.** Claim and result
  excerpts are printed as truncated text (120
  characters). A crafted transcript can put words in an
  excerpt, but excerpts are never executed, rendered as
  markup by the tool, or fed anywhere — they exist so a
  human can check the verdict in seconds. When an audit
  result leaves the machine, `--no-excerpts` removes
  every transcript-derived string; only claim types,
  targets, line numbers, verdicts and the tool's own
  generated reasons travel.
- **It writes nothing.** Auditing a transcript does not
  modify it — the transcript is the evidence, and the
  tool treats it as read-only.

## Reporting a problem

If you find a way to make done-claim-auditor execute
content from a transcript, read a file other than the
one named on the command line, or make a network call,
please report it privately through GitHub's "Report a
vulnerability" flow on this repository (Security →
Advisories), rather than a public issue. A minimal
fixture transcript that reproduces the problem is the
most helpful thing you can include.

If done-claim-auditor *misjudges* a transcript — a
claim marked EVIDENCED whose matching call's result
actually shows failure, or a CONTRADICTED verdict whose
recorded result is clean — that is a correctness bug,
and the dangerous direction matters most (a false
EVIDENCED is worse than a false flag): open a regular
issue with the fixture and the verdict you expected.
A claim that was never extracted at all is a known
limit of pattern-based extraction — see "Known limits"
in the README — but reports of common phrasings the
table misses are welcome as feature requests.

## Supported versions

Only the latest release is supported. Fixes land in a
new release, never as silent edits to an existing one.
