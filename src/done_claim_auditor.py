#!/usr/bin/env python3
"""done-claim-auditor — check an AI agent's completion claims
against the session's own tool-call record.

Pure Python standard library. Local only: it reads the ONE
transcript file you point it at, runs nothing, opens nothing
else, and sends nothing anywhere.

AI coding agents routinely report work they did not do: tests
"passing" that never ran, files "created" that no Write ever
touched, commits that exist only in the summary. A hosted
receipts service will check this for you if you route every
call through it — this tool checks the transcripts you already
have, offline, after the fact. It is the mechanical version of
"no record, no credit."

WHAT IT READS (v0.1.0 — one format, stated plainly):
Claude Code session transcripts: JSON Lines files, one JSON
object per line, as written to
~/.claude/projects/<project>/<session>.jsonl — assistant
messages whose content blocks include `text` and `tool_use`,
user messages whose blocks include `tool_result`. The parser
is shaped so a second format can be added later; a file it
cannot recognise is a clean error naming what was expected,
never a guess and never silent partial credit.

WHAT IT CHECKS: completion claims found in the assistant's own
text, matched mechanically against tool calls recorded in the
SAME transcript, BEFORE the claim. The claim types and their
evidence rules are a small explicit table (see
CLAIM_PATTERNS and the evidence rules in SKILL.md):

  tests pass     an earlier test-runner command whose result
                 does not show failure
  created FILE   an earlier Write to FILE, or a shell command
                 that created it (redirect / tee / touch / cp)
  updated FILE   an earlier Edit or Write to FILE
  committed      an earlier `git commit` command
  pushed         an earlier `git push` command
  build succeeds an earlier build command whose result does
                 not show failure

VERDICTS: EVIDENCED (a matching call ran and its recorded
result shows no failure) · CONTRADICTED (the most recent
matching call's recorded result shows failure — the record
disagrees with the claim) · UNEVIDENCED (no matching call
before the claim, or the matching call's result was never
recorded). Evidence must come BEFORE the claim — a test run
after the sentence that claims it does not count.

THE LIMIT, stated plainly: the auditor judges the transcript,
not the world. It never runs the commands, never opens the
files the session mentions, and cannot know about work done
outside the recorded session. An EVIDENCED verdict means "the
session's own record backs the claim" — nothing more.

PRIVACY: excerpts from the transcript are printed truncated
(--no-excerpts prints only claim types, line numbers and
verdicts, so an audit result can be shared without leaking
transcript content).

Exit codes: 0 = every claim EVIDENCED (or no claims at all)
· 1 = at least one claim UNEVIDENCED or CONTRADICTED (a
finding, so a review script can act on it) · 2 = ERROR —
clean message, never a traceback; with --json the error is
{"error": ...}.
"""
import argparse
import json
import re
import sys
from pathlib import Path

__version__ = "0.1.0"
TOOL = "done-claim-auditor"
FORMAT_NAME = "claude-code-jsonl"
FORMAT_LABEL = "Claude Code session JSONL"

# Excerpts (claim sentences and result snippets) are truncated
# to this many characters, in text and JSON output alike.
EXCERPT_LIMIT = 120

EVIDENCED = "EVIDENCED"
UNEVIDENCED = "UNEVIDENCED"
CONTRADICTED = "CONTRADICTED"
VERDICTS = (EVIDENCED, UNEVIDENCED, CONTRADICTED)


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# claim patterns — the explicit table. Each pattern is matched
# against assistant text only (never tool inputs, never user
# text). `target` patterns capture a file path in group 1.
# --------------------------------------------------------------------------

_PATH = r"([A-Za-z0-9_./~-]*[A-Za-z0-9_-]+\.[A-Za-z][A-Za-z0-9]*)"

CLAIM_PATTERNS = [
    {
        "type": "tests_pass",
        "label": "tests pass",
        "regex": re.compile(
            r"\b(?:all\s+)?(?:\d+\s+)?tests?\s+(?:are\s+)?"
            r"(?:pass(?:ing|ed|es)?|green)\b"
            r"|\btest\s+suite\s+(?:passes|passed|is\s+green)\b"
            r"|\bevery\s+test\s+passes\b",
            re.IGNORECASE),
        "target": False,
    },
    {
        "type": "file_created",
        "label": "created file",
        "regex": re.compile(
            r"\b(?:created|wrote)\s+(?:the\s+|a\s+|new\s+)*"
            r"(?:file\s+)?" + _PATH
            + r"|\bnew\s+file\s+" + _PATH,
            re.IGNORECASE),
        "target": True,
    },
    {
        "type": "file_updated",
        "label": "updated file",
        "regex": re.compile(
            r"\b(?:updated|edited|modified|patched)\s+"
            r"(?:the\s+|a\s+)?(?:file\s+)?" + _PATH,
            re.IGNORECASE),
        "target": True,
    },
    {
        "type": "committed",
        "label": "committed",
        "regex": re.compile(r"\bcommitted\b", re.IGNORECASE),
        "target": False,
    },
    {
        "type": "pushed",
        "label": "pushed",
        "regex": re.compile(r"\bpushed\b", re.IGNORECASE),
        "target": False,
    },
    {
        "type": "build_succeeds",
        "label": "build succeeds",
        "regex": re.compile(
            r"\bbuild\s+(?:succeeds|succeeded|passes|passed|"
            r"is\s+green|successful)\b"
            r"|\bcompiles\s+(?:cleanly|successfully)\b"
            r"|\bcompilation\s+succeeds\b",
            re.IGNORECASE),
        "target": False,
    },
]

# Words that make a sentence a PLAN, not a claim, when they
# appear before the matched phrase ("I will push once tests
# pass" asserts nothing about the past). A planned phrase is
# not extracted as a claim at all.
_PLAN_RE = re.compile(
    r"\b(?:will|shall|going\s+to|plan(?:s|ning)?\s+to|"
    r"about\s+to)\b|'ll\b",
    re.IGNORECASE)

# --------------------------------------------------------------------------
# evidence rules — what counts as a matching tool call, and
# what counts as a failed result.
# --------------------------------------------------------------------------

_TEST_COMMAND_RE = re.compile(
    r"\bpytest\b|\bpython3?\s+-m\s+(?:pytest|unittest)\b"
    r"|\bpython3?\s+\S*test\S*\.py\b"
    r"|\bnpm\s+(?:run\s+)?test\b|\byarn\s+test\b|\bpnpm\s+test\b"
    r"|\bgo\s+test\b|\bcargo\s+test\b|\bmvn\s+(?:test|verify)\b"
    r"|\bgradle\s+(?:test|check)\b|\bjest\b|\bvitest\b|\bmocha\b"
    r"|\brspec\b|\bphpunit\b|\bctest\b|\btox\b|\bnose2?\b"
    r"|\bunittest\b|\bdiscover\s+-s\s+tests?\b",
    re.IGNORECASE)

_BUILD_COMMAND_RE = re.compile(
    r"\bnpm\s+run\s+build\b|\byarn\s+build\b|\bpnpm\s+build\b"
    r"|\bmake\b|\bcargo\s+build\b|\bgo\s+build\b|\btsc\b"
    r"|\bmvn\s+(?:package|install|compile)\b|\bgradle\s+build\b"
    r"|\bcmake\s+--build\b|\bpython3?\s+-m\s+build\b"
    r"|\bmsbuild\b|\bdotnet\s+build\b",
    re.IGNORECASE)

_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_GIT_PUSH_RE = re.compile(r"\bgit\s+push\b")

# A recorded result "shows failure" when the tool marked it an
# error (is_error) or its text carries one of these markers.
# Counts are [1-9]-anchored so "0 failed" never reads as a
# failure.
_FAILURE_RES = [
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"\bFAILED\b"),
    re.compile(r"\bFAILURES\b"),
    re.compile(r"\b[1-9]\d*\s+failed\b", re.IGNORECASE),
    re.compile(r"\bfailures\s*=\s*[1-9]"),
    re.compile(r"\berrors?\s*=\s*[1-9]"),
    re.compile(r"AssertionError"),
    re.compile(r"BUILD FAILURE"),
    re.compile(r"\bfatal:", re.IGNORECASE),
    re.compile(r"\bexit\s+code:?\s*[1-9]", re.IGNORECASE),
    re.compile(r"\[rejected\]"),
    re.compile(r"\berror:", re.IGNORECASE),
]


def result_shows_failure(result):
    """True when a recorded tool result shows failure: the
    transcript marked it an error, or its text carries a
    failure marker."""
    if result is None:
        return False
    if result["is_error"]:
        return True
    text = result["text"]
    return any(rx.search(text) for rx in _FAILURE_RES)


def _clean_path(value):
    """Normalise a path for comparison: strip quotes and any
    leading ./ — matching itself is by exact path or by
    absolute/relative suffix (see paths_match)."""
    value = value.strip().strip("\"'").rstrip(".,;:")
    while value.startswith("./"):
        value = value[2:]
    return value


def paths_match(claimed, actual):
    """Does the path in the claim refer to the path in the tool
    call? Yes when they are equal, or when one is the other
    with a leading directory prefix (relative claim vs
    absolute call, or the reverse)."""
    a = _clean_path(claimed)
    b = _clean_path(actual)
    if not a or not b:
        return False
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


# --------------------------------------------------------------------------
# transcript parsing — Claude Code session JSONL.
#
# Each non-blank line must be one JSON object. Message-bearing
# lines carry message.role / message.content: assistant content
# blocks of type `text` (claims live here) and `tool_use` (the
# calls), user content blocks of type `tool_result` (the
# recorded outcomes). Other line types Claude Code writes
# (summary, system, snapshots…) are counted and ignored.
# --------------------------------------------------------------------------

def _flatten_result_content(content):
    """A tool_result's content is a string or a list of blocks;
    flatten it to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def parse_transcript(path):
    """Read + parse the transcript file.

    Returns {"lines": total physical lines,
             "calls": [call, ...] in file order,
             "results": {tool_use_id: result},
             "texts": [(line, text), ...] assistant text blocks}
    where a call is {"id", "name", "line", "input"} and a
    result is {"line", "text", "is_error"}.

    Raises ToolError — naming the line or the expected format —
    on anything the parser cannot stand behind.
    """
    if not path.is_file():
        raise ToolError(f"transcript not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"could not read transcript {path.name} "
                        f"({exc.__class__.__name__})")
    lines = raw.splitlines()
    calls = []
    results = {}
    texts = []
    saw_structure = False
    for no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError as exc:
            raise ToolError(
                f"line {no} is not valid JSON ({exc}) — expected "
                f"a {FORMAT_LABEL} file: one JSON object per "
                f"line")
        if not isinstance(obj, dict):
            raise ToolError(
                f"line {no} is a JSON {type(obj).__name__}, not "
                f"an object — expected a {FORMAT_LABEL} file: "
                f"one JSON object per line")
        message = obj.get("message")
        if isinstance(obj.get("type"), str) \
                or isinstance(message, dict):
            saw_structure = True
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, str):
            if role == "assistant" and content.strip():
                texts.append((no, content))
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if role == "assistant" and btype == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append((no, text))
            elif role == "assistant" and btype == "tool_use":
                calls.append({
                    "id": block.get("id"),
                    "name": block.get("name") or "",
                    "line": no,
                    "input": block.get("input")
                    if isinstance(block.get("input"), dict)
                    else {},
                })
            elif role == "user" and btype == "tool_result":
                tid = block.get("tool_use_id")
                if tid is not None:
                    results[tid] = {
                        "line": no,
                        "text": _flatten_result_content(
                            block.get("content")),
                        "is_error": bool(block.get("is_error")),
                    }
    nonblank = sum(1 for line in lines if line.strip())
    if nonblank and not saw_structure:
        raise ToolError(
            f"{path.name} does not look like a {FORMAT_LABEL} "
            f"file — no line carries a \"type\" or \"message\" "
            f"field. v0.1.0 reads Claude Code session "
            f"transcripts only (one JSON object per line, "
            f"assistant messages with text/tool_use blocks, "
            f"user messages with tool_result blocks)")
    return {"lines": len(lines), "calls": calls,
            "results": results, "texts": texts}


# --------------------------------------------------------------------------
# claim extraction — assistant text only, past-tense assertions
# only (a sentence planning the work is not a claim).
# --------------------------------------------------------------------------

def _sentence_span(text, start, end):
    """The sentence (or line) containing text[start:end],
    whitespace-collapsed — the excerpt shown for a claim."""
    lo = start
    while lo > 0 and text[lo - 1] not in ".!?\n":
        lo -= 1
    hi = end
    while hi < len(text) and text[hi] not in ".!?\n":
        hi += 1
    if hi < len(text):
        hi += 1  # keep the closing punctuation
    return " ".join(text[lo:hi].split())


def _truncate(text):
    if len(text) <= EXCERPT_LIMIT:
        return text
    return text[:EXCERPT_LIMIT - 1].rstrip() + "…"


def extract_claims(text, line):
    """All completion claims in one assistant text block.

    Returns claim dicts {"type", "label", "target", "line",
    "excerpt"} in the order the phrases appear. A phrase
    preceded in its sentence by a plan marker (will / shall /
    going to / 'll …) is a plan, not a claim, and is skipped.
    """
    found = []
    for pattern in CLAIM_PATTERNS:
        for m in pattern["regex"].finditer(text):
            sentence = _sentence_span(text, m.start(), m.end())
            before = text[:m.start()]
            cut = max(before.rfind("."), before.rfind("!"),
                      before.rfind("?"), before.rfind("\n"))
            if _PLAN_RE.search(before[cut + 1:]):
                continue
            target = None
            if pattern["target"]:
                target = next((g for g in m.groups()
                               if g is not None), None)
                if target is not None:
                    target = _clean_path(target)
            found.append({
                "type": pattern["type"],
                "label": pattern["label"],
                "target": target,
                "line": line,
                "excerpt": _truncate(sentence),
                "_pos": m.start(),
            })
    found.sort(key=lambda c: c["_pos"])
    for claim in found:
        del claim["_pos"]
    return found


# --------------------------------------------------------------------------
# judging — match each claim to the most recent matching call
# recorded BEFORE it, then read that call's recorded result.
# --------------------------------------------------------------------------

def _bash_command(call):
    command = call["input"].get("command")
    return command if isinstance(command, str) else ""


def _shell_creates(command, target):
    """Does this shell command create `target`? By the stated
    rule: a redirect (> or >>) into it, `tee` into it,
    `touch` on it, or `cp` with it as the destination."""
    tokens = [t.strip("\"'") for t in command.split()]
    for i, tok in enumerate(tokens):
        if tok in (">", ">>", "tee", "touch") \
                and i + 1 < len(tokens) \
                and paths_match(target, tokens[i + 1]):
            return True
        if tok.startswith(">") and len(tok) > 1 \
                and paths_match(target, tok.lstrip(">")):
            return True
        if tok == "cp" and i + 2 < len(tokens) \
                and paths_match(target, tokens[-1]):
            return True
    return False


def _candidate_calls(claim, calls):
    """The calls that could evidence this claim, in file
    order. Only the ones before the claim are considered by
    the caller."""
    ctype = claim["type"]
    target = claim["target"]
    out = []
    for call in calls:
        name = call["name"]
        if ctype == "tests_pass":
            if name == "Bash" and _TEST_COMMAND_RE.search(
                    _bash_command(call)):
                out.append(call)
        elif ctype == "build_succeeds":
            if name == "Bash" and _BUILD_COMMAND_RE.search(
                    _bash_command(call)):
                out.append(call)
        elif ctype == "committed":
            if name == "Bash" and _GIT_COMMIT_RE.search(
                    _bash_command(call)):
                out.append(call)
        elif ctype == "pushed":
            if name == "Bash" and _GIT_PUSH_RE.search(
                    _bash_command(call)):
                out.append(call)
        elif ctype == "file_created":
            if name == "Write" and paths_match(
                    target, call["input"].get("file_path", "")):
                out.append(call)
            elif name == "Bash" and _shell_creates(
                    _bash_command(call), target):
                out.append(call)
        elif ctype == "file_updated":
            if name in ("Edit", "Write") and paths_match(
                    target, call["input"].get("file_path", "")):
                out.append(call)
    return out


def _evidence_detail(call):
    """A short factual label for the evidence call."""
    if call["name"] == "Bash":
        return f"Bash: {_truncate(_bash_command(call))}"
    path = call["input"].get("file_path")
    if isinstance(path, str) and path:
        return f"{call['name']}: {path}"
    return call["name"]


def _result_excerpt(result):
    """The first non-empty line of a recorded result,
    truncated — the snippet shown as the evidence's voice."""
    if result is None:
        return None
    for line in result["text"].splitlines():
        if line.strip():
            return _truncate(" ".join(line.split()))
    return ""


def judge_claim(claim, calls, results):
    """Attach "verdict", "evidence" and "reason" to a claim.

    The most recent matching call BEFORE the claim decides:
    a failing recorded result CONTRADICTS the claim, a clean
    one EVIDENCES it. No matching call — or a matching call
    whose result the transcript never recorded — leaves the
    claim UNEVIDENCED.
    """
    before = [c for c in _candidate_calls(claim, calls)
              if c["line"] < claim["line"]]
    if not before:
        claim["verdict"] = UNEVIDENCED
        claim["evidence"] = None
        claim["reason"] = ("no matching tool call before the "
                           "claim in this transcript")
        return claim
    call = before[-1]
    result = results.get(call["id"])
    evidence = {
        "tool": call["name"],
        "line": call["line"],
        "result_line": result["line"] if result else None,
        "detail": _evidence_detail(call),
        "result_excerpt": _result_excerpt(result),
    }
    claim["evidence"] = evidence
    if result is None:
        claim["verdict"] = UNEVIDENCED
        claim["reason"] = ("a matching call exists (line "
                           f"{call['line']}) but its result was "
                           f"never recorded in the transcript")
    elif result_shows_failure(result):
        claim["verdict"] = CONTRADICTED
        claim["reason"] = ("the most recent matching call's "
                            "recorded result shows failure")
    else:
        claim["verdict"] = EVIDENCED
        claim["reason"] = ("a matching call ran before the "
                            "claim and its recorded result "
                            "shows no failure")
    return claim


def audit_transcript(path):
    """Parse + extract + judge. Returns the full audit dict
    (the JSON shape; the text view renders from it)."""
    parsed = parse_transcript(path)
    claims = []
    for line, text in parsed["texts"]:
        claims.extend(extract_claims(text, line))
    for claim in claims:
        judge_claim(claim, parsed["calls"], parsed["results"])
    summary = {
        "claims": len(claims),
        "evidenced": sum(1 for c in claims
                         if c["verdict"] == EVIDENCED),
        "unevidenced": sum(1 for c in claims
                           if c["verdict"] == UNEVIDENCED),
        "contradicted": sum(1 for c in claims
                            if c["verdict"] == CONTRADICTED),
    }
    return {
        "tool": TOOL, "version": __version__,
        "command": "audit",
        "transcript": path.name,
        "format": FORMAT_NAME,
        "lines": parsed["lines"],
        "tool_calls": len(parsed["calls"]),
        "claims": claims,
        "summary": summary,
        "clean": summary["unevidenced"] == 0
        and summary["contradicted"] == 0,
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

SCOPE_LINE = ("Reads the transcript only — it runs nothing "
              "and opens no other file. Verdicts judge the "
              "session's own record, not the world.")


def public_view(audit, excerpts):
    """The audit dict as printed. With excerpts off, every
    transcript-derived string is removed — claim excerpts,
    evidence details and result snippets — leaving claim
    types, targets, line numbers, verdicts and the tool's own
    generated reasons."""
    claims = []
    for c in audit["claims"]:
        entry = {
            "type": c["type"],
            "label": c["label"],
            "target": c["target"],
            "line": c["line"],
            "verdict": c["verdict"],
            "reason": c["reason"],
            "evidence": None,
        }
        if c["evidence"] is not None:
            ev = {
                "tool": c["evidence"]["tool"],
                "line": c["evidence"]["line"],
                "result_line": c["evidence"]["result_line"],
            }
            if excerpts:
                ev["detail"] = c["evidence"]["detail"]
                ev["result_excerpt"] = \
                    c["evidence"]["result_excerpt"]
            entry["evidence"] = ev
        if excerpts:
            entry["excerpt"] = c["excerpt"]
        claims.append(entry)
    return {
        "tool": audit["tool"], "version": audit["version"],
        "command": audit["command"],
        "transcript": audit["transcript"],
        "format": audit["format"],
        "lines": audit["lines"],
        "tool_calls": audit["tool_calls"],
        "excerpts": excerpts,
        "claims": claims,
        "summary": audit["summary"],
        "clean": audit["clean"],
    }


def render_text(audit, excerpts):
    lines = [
        f"done-claim-auditor v{__version__} — audit · "
        f"transcript {audit['transcript']}",
        f"Format: {FORMAT_LABEL} · {audit['lines']} lines · "
        f"{audit['tool_calls']} tool calls",
        SCOPE_LINE,
    ]
    if not excerpts:
        lines.append("Excerpts off (--no-excerpts): claim "
                     "types, line numbers and verdicts only.")
    lines.append("")
    claims = audit["claims"]
    if not claims:
        lines.append("No completion claims found in the "
                     "assistant's text.")
    else:
        lines.append(f"CLAIMS ({len(claims)}):")
        for c in claims:
            head = f"line {c['line']} · {c['label']}"
            if c["target"]:
                head += f" {c['target']}"
            head += f" · {c['verdict']}"
            lines.append(head)
            if excerpts:
                lines.append(f"  claim: \"{c['excerpt']}\"")
            ev = c["evidence"]
            if ev is None:
                lines.append(f"  evidence: none — {c['reason']}")
            else:
                where = (f"{ev['tool']}, line {ev['line']}")
                if ev["result_line"] is not None:
                    where += f" (result line {ev['result_line']})"
                if c["verdict"] == CONTRADICTED:
                    where += " — the recorded result shows failure"
                elif c["verdict"] == UNEVIDENCED:
                    where += f" — {c['reason']}"
                if excerpts and ev["result_excerpt"]:
                    where += f" — \"{ev['result_excerpt']}\""
                lines.append(f"  evidence: {where}")
        lines.append("")
    s = audit["summary"]
    lines.append(
        f"Summary: {s['claims']} claims · {s['evidenced']} "
        f"evidenced · {s['unevidenced']} unevidenced · "
        f"{s['contradicted']} contradicted")
    if not claims:
        lines.append("Verdict: CLEAN — nothing was claimed, so "
                     "nothing is unbacked.")
    elif audit["clean"]:
        lines.append("Verdict: CLEAN — every claim is backed "
                     "by the session's own record.")
    else:
        bits = []
        if s["unevidenced"]:
            bits.append(f"{s['unevidenced']} unevidenced")
        if s["contradicted"]:
            bits.append(f"{s['contradicted']} contradicted")
        lines.append(
            f"Verdict: NOT CLEAN — {' · '.join(bits)}. Do not "
            f"take this session's summary at its word; check "
            f"the claims above against the record.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in
    --json mode ({"error": ...} on stdout, same exit code 2) —
    an agent driving this tool with --json never gets plain
    text or a traceback. The flag lives on the class so
    subparsers share it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def cmd_audit(a):
    path = Path(a.transcript)
    audit = audit_transcript(path)
    if a.json:
        print(json.dumps(public_view(audit, not a.no_excerpts),
                         indent=2))
    else:
        print(render_text(audit, not a.no_excerpts))
    return 0 if audit["clean"] else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="Check an AI agent's completion claims "
                    "against its own session transcript: every "
                    "\"tests pass\", \"created X\", \"committed\" "
                    "matched mechanically to the tool calls "
                    "recorded before it (stdlib only, local "
                    "only, reads one file, runs nothing).")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_audit = sub.add_parser(
        "audit", help="audit one Claude Code session transcript "
                      "(JSONL): extract the assistant's "
                      "completion claims and match each to the "
                      "tool-call record before it; exit 1 when "
                      "any claim is unevidenced or contradicted")
    p_audit.add_argument("transcript",
                         help="the session transcript file "
                              "(Claude Code JSONL)")
    p_audit.add_argument("--json", action="store_true",
                         help="print one JSON object instead "
                              "of text")
    p_audit.add_argument("--no-excerpts", action="store_true",
                         help="print only claim types, targets, "
                              "line numbers and verdicts — no "
                              "transcript text at all, so the "
                              "result can be shared safely")
    p_audit.set_defaults(func=cmd_audit)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
