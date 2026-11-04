# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** done-claim-auditor's promise is
  "clone and run". Pull requests that add a third-party dependency
  will not be merged.
- **Local only, and it executes nothing.** No network calls, no
  telemetry, no uploads. Above all: the tool must never run a
  command it found in a transcript, and never open a file a
  transcript mentions. A transcript is untrusted data — sessions
  work on hostile code — and the moment the auditor acts on its
  contents it stops being an auditor. A pull request that adds
  execution changes what this tool *is* and will not be merged.
- **One format, honestly.** v1.0.0 reads Claude Code JSONL.
  A new format arrives as a new parser beside the existing one,
  with its own fixtures and its own detection rule — never as a
  loosening of the current parser until it "sort of" reads other
  shapes. A file the tool cannot recognise must stay a clean
  error naming what was expected.
- **The evidence rules are the product.** The claim-pattern
  table and the candidate/failure rules in `SKILL.md` are the
  contract reviewers rely on. Widening a pattern, adding a
  candidate call type or changing a failure marker is a
  behaviour change that needs the README table, the SKILL.md
  schema, the changelog and the pinning tests updated together —
  and a fixture or inline session that shows the old rule
  getting it wrong.
- **Verdicts stay mechanical.** No heuristics that "weigh" a
  session, no scoring, no LLM judgement calls. A claim is
  evidenced, unevidenced or contradicted by the record, with
  line numbers a human can follow. If a case cannot be decided
  mechanically, the honest output is UNEVIDENCED plus the
  printed excerpt — not a guess dressed as a verdict.
- **Never make a verdict sound like ground truth.** Wording
  changes that blur "the record backs the claim" into "the
  work is verified" will not be merged. The limit — transcript,
  not world — is printed in the tool's output on purpose; do
  not strip it when relaying results.
- **Privacy is a feature.** Excerpts stay truncated to the
  stated limit, and `--no-excerpts` must keep removing every
  transcript-derived string (claim excerpts, evidence details,
  result snippets) from both output modes. Tests assert the
  absence of fixture prose — keep them passing, and extend the
  distinctive-string list when you add a fixture.
- **Both directions tested.** A behaviour change needs a test
  where an honest session passes and a lying (or broken) one
  fails cleanly — not just one side. Line-number expectations
  must be counted by hand from the fixture file, never copied
  from the tool's own output.
