#!/usr/bin/env python3
"""Tests for done-claim-auditor. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

The two bundled fixtures are CONSTRUCTED transcripts (built by
hand to the Claude Code JSONL shape) with hand-counted line
numbers — expectations below are worked out from the fixture
files, never from the tool's own output:

honest-session.jsonl (10 lines):
    line 2  Write src/greet.py        line 3  its result
    line 4  Write tests/test_greet.py line 5  its result
    line 6  Bash unittest             line 7  result "OK"
    line 8  Bash git commit           line 9  its result
    line 10 claims: created greet (EVIDENCED, evidence 2/3),
            created test_greet (EVIDENCED, 4/5),
            tests pass (EVIDENCED, 6/7), committed (EVIDENCED, 8/9)
    => 4 claims · 4 evidenced · exit 0

liar-session.jsonl (6 lines):
    line 2  Edit src/parser.py        line 3  its result
    line 4  Bash pytest               line 5  result FAILED,
                                            is_error, 2 failed
    line 6  claims: updated parser (EVIDENCED, 2/3),
            tests pass (CONTRADICTED, 4/5), pushed (UNEVIDENCED)
    => 3 claims · 1 evidenced · 1 unevidenced · 1 contradicted
       · exit 1

Both directions are covered: evidenced work exits 0, unbacked
claims exit 1, and every broken input exits 2 with a clean
message — in text AND in --json mode.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "done_claim_auditor.py"
EXAMPLES = PACK_ROOT / "examples"
sys.path.insert(0, str(PACK_ROOT / "src"))

import done_claim_auditor as dca  # noqa: E402

HONEST = EXAMPLES / "honest-session.jsonl"
LIAR = EXAMPLES / "liar-session.jsonl"


def run_cli(*args):
    proc = subprocess.run(
        [sys.executable, str(SRC), *args],
        capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def line_user_text(text):
    return {"type": "user",
            "message": {"role": "user", "content": text}}


def line_assistant(blocks):
    if isinstance(blocks, str):
        blocks = [{"type": "text", "text": blocks}]
    return {"type": "assistant",
            "message": {"role": "assistant", "content": blocks}}


def line_tool_result(tool_id, content, is_error=False):
    block = {"type": "tool_result", "tool_use_id": tool_id,
             "content": content}
    if is_error:
        block["is_error"] = True
    return {"type": "user",
            "message": {"role": "user", "content": [block]}}


def tool_use(tool_id, name, **inputs):
    return {"type": "tool_use", "id": tool_id, "name": name,
            "input": inputs}


def write_session(tmp, lines):
    path = Path(tmp) / "session.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n",
                    encoding="utf-8")
    return path


class TestExtraction(unittest.TestCase):
    """One test per claim pattern, plus the plan filter."""

    def types(self, text):
        return [c["type"] for c in dca.extract_claims(text, 1)]

    def test_tests_pass_variants(self):
        for text in ("All tests pass.",
                     "The tests are passing.",
                     "46 tests passed.",
                     "The test suite passes.",
                     "Every test passes."):
            self.assertEqual(self.types(text), ["tests_pass"], text)

    def test_file_created(self):
        claims = dca.extract_claims("I created src/new_mod.py.", 1)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["type"], "file_created")
        self.assertEqual(claims[0]["target"], "src/new_mod.py")
        claims = dca.extract_claims("Wrote the file docs/guide.md.", 1)
        self.assertEqual(claims[0]["target"], "docs/guide.md")

    def test_file_created_sentence_end_no_trailing_dot(self):
        claims = dca.extract_claims("Done — created src/greet.py.", 1)
        self.assertEqual(claims[0]["target"], "src/greet.py")

    def test_file_updated(self):
        claims = dca.extract_claims("I updated src/parser.py.", 1)
        self.assertEqual(claims[0]["type"], "file_updated")
        self.assertEqual(claims[0]["target"], "src/parser.py")
        claims = dca.extract_claims("Edited config/app.yaml.", 1)
        self.assertEqual(claims[0]["type"], "file_updated")

    def test_committed_and_pushed(self):
        self.assertEqual(
            self.types("I committed the change and pushed it."),
            ["committed", "pushed"])

    def test_build_succeeds(self):
        self.assertEqual(self.types("The build succeeds."),
                         ["build_succeeds"])
        self.assertEqual(self.types("It compiles cleanly now."),
                         ["build_succeeds"])

    def test_plans_are_not_claims(self):
        self.assertEqual(
            self.types("I will push the fix once tests pass."), [])
        self.assertEqual(
            self.types("Next I'll run the suite and confirm "
                       "all tests pass."), [])
        self.assertEqual(
            self.types("Going to create src/x.py shortly."), [])

    def test_no_claims_in_plain_progress_text(self):
        self.assertEqual(
            self.types("Let me look at the parser first."), [])
        self.assertEqual(
            self.types("I'll create the module first."), [])

    def test_tool_inputs_are_never_scanned(self):
        # a Bash command whose text mentions claims is a CALL,
        # not a claim: the transcript below has no assistant
        # text at all, so zero claims must be found.
        with tempfile.TemporaryDirectory() as tmp:
            path = write_session(tmp, [
                line_user_text("do it"),
                line_assistant([tool_use(
                    "t1", "Bash",
                    command="echo 'tests pass' && git commit -am x",
                    description="created src/fake.py")]),
                line_tool_result("t1", "ok"),
            ])
            audit = dca.audit_transcript(path)
        self.assertEqual(audit["summary"]["claims"], 0)


class TestFixtures(unittest.TestCase):
    """The two bundled fixtures, against hand-counted lines."""

    def test_honest_all_evidenced(self):
        audit = dca.audit_transcript(HONEST)
        s = audit["summary"]
        self.assertEqual((s["claims"], s["evidenced"],
                          s["unevidenced"], s["contradicted"]),
                         (4, 4, 0, 0))
        self.assertTrue(audit["clean"])

    def test_honest_line_numbers_are_the_real_ones(self):
        audit = dca.audit_transcript(HONEST)
        by_target = {c["target"]: c for c in audit["claims"]
                     if c["target"]}
        greet = by_target["src/greet.py"]
        self.assertEqual(greet["line"], 10)
        self.assertEqual(greet["evidence"]["line"], 2)
        self.assertEqual(greet["evidence"]["result_line"], 3)
        tests = next(c for c in audit["claims"]
                     if c["type"] == "tests_pass")
        self.assertEqual(tests["evidence"]["line"], 6)
        self.assertEqual(tests["evidence"]["result_line"], 7)
        commit = next(c for c in audit["claims"]
                      if c["type"] == "committed")
        self.assertEqual(commit["evidence"]["line"], 8)
        self.assertEqual(commit["evidence"]["result_line"], 9)

    def test_liar_verdicts(self):
        audit = dca.audit_transcript(LIAR)
        s = audit["summary"]
        self.assertEqual((s["claims"], s["evidenced"],
                          s["unevidenced"], s["contradicted"]),
                         (3, 1, 1, 1))
        self.assertFalse(audit["clean"])
        by_type = {c["type"]: c for c in audit["claims"]}
        self.assertEqual(by_type["file_updated"]["verdict"],
                         dca.EVIDENCED)
        self.assertEqual(by_type["tests_pass"]["verdict"],
                         dca.CONTRADICTED)
        self.assertEqual(by_type["tests_pass"]["evidence"]["line"],
                         4)
        self.assertEqual(
            by_type["tests_pass"]["evidence"]["result_line"], 5)
        self.assertEqual(by_type["pushed"]["verdict"],
                         dca.UNEVIDENCED)
        self.assertIsNone(by_type["pushed"]["evidence"])


class TestJudging(unittest.TestCase):
    """Verdict mechanics on inline sessions."""

    def audit(self, lines):
        with tempfile.TemporaryDirectory() as tmp:
            return dca.audit_transcript(write_session(tmp, lines))

    def test_call_after_the_claim_does_not_evidence_it(self):
        audit = self.audit([
            line_user_text("run the tests"),
            line_assistant("All tests pass."),               # line 2
            line_assistant([tool_use(
                "t1", "Bash", command="python3 -m pytest -q")]),
            line_tool_result("t1", "5 passed"),              # after!
        ])
        claim = audit["claims"][0]
        self.assertEqual(claim["verdict"], dca.UNEVIDENCED)

    def test_most_recent_run_decides_fail_then_pass(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash", command="python3 -m pytest -q")]),
            line_tool_result("t1", "1 failed, 4 passed",
                             is_error=True),
            line_assistant([tool_use(
                "t2", "Bash", command="python3 -m pytest -q")]),
            line_tool_result("t2", "5 passed in 0.2s"),
            line_assistant("All tests pass now."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.EVIDENCED)
        # line 3 is the second (passing) run; its result is line 4
        self.assertEqual(audit["claims"][0]["evidence"]["line"], 3)
        self.assertEqual(
            audit["claims"][0]["evidence"]["result_line"], 4)

    def test_most_recent_run_decides_pass_then_fail(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash", command="python3 -m pytest -q")]),
            line_tool_result("t1", "5 passed in 0.2s"),
            line_assistant([tool_use(
                "t2", "Bash", command="python3 -m pytest -q")]),
            line_tool_result("t2", "FAILED x - AssertionError\n"
                                   "2 failed, 3 passed"),
            line_assistant("All tests pass."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.CONTRADICTED)

    def test_failed_test_output_contradicts_without_is_error(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash",
                command="python3 -m unittest discover -s tests")]),
            line_tool_result("t1", "Ran 9 tests\n\n"
                                   "FAILED (failures=2)"),
            line_assistant("All tests pass."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.CONTRADICTED)

    def test_zero_failed_is_not_a_failure(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash", command="python3 -m pytest -q")]),
            line_tool_result("t1", "5 passed, 0 failed in 0.2s"),
            line_assistant("All tests pass."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.EVIDENCED)

    def test_call_with_no_recorded_result_is_unevidenced(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash", command="git push origin main")]),
            # session ends before the result is recorded
            line_assistant("I pushed the fix."),
        ])
        claim = audit["claims"][0]
        self.assertEqual(claim["verdict"], dca.UNEVIDENCED)
        self.assertIn("never recorded", claim["reason"])

    def test_write_error_contradicts_created_claim(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Write",
                file_path="/home/dev/project/src/new.py",
                content="x")]),
            line_tool_result("t1", "error: permission denied",
                             is_error=True),
            line_assistant("I created src/new.py."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.CONTRADICTED)

    def test_shell_redirect_evidences_creation(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash",
                command="cat > /home/dev/project/src/gen.py "
                        "<<'EOF'\nx = 1\nEOF")]),
            line_tool_result("t1", ""),
            line_assistant("I created src/gen.py."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.EVIDENCED)

    def test_shell_touch_evidences_creation(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash",
                command="touch /home/dev/project/src/marker.py")]),
            line_tool_result("t1", ""),
            line_assistant("I created src/marker.py."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.EVIDENCED)

    def test_build_claim_contradicted_by_failed_build(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash", command="npm run build")]),
            line_tool_result("t1", "error: cannot find module "
                                   "'./x'", is_error=True),
            line_assistant("The build succeeds."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.CONTRADICTED)

    def test_long_claim_sentence_excerpt_is_truncated(self):
        filler = "with a great many words of surrounding prose " * 6
        claims = dca.extract_claims(
            f"Summary: {filler}and all tests pass.", 1)
        self.assertEqual(len(claims), 1)
        self.assertLessEqual(len(claims[0]["excerpt"]),
                             dca.EXCERPT_LIMIT)
        self.assertTrue(claims[0]["excerpt"].endswith("…"))

    def test_created_claim_for_a_different_file_is_unevidenced(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Write",
                file_path="/home/dev/project/src/a.py",
                content="x")]),
            line_tool_result("t1", "File created successfully"),
            line_assistant("I created src/b.py."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.UNEVIDENCED)

    def test_build_claim_needs_a_build_command(self):
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash", command="ls -la")]),
            line_tool_result("t1", "total 0"),
            line_assistant("The build succeeds."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.UNEVIDENCED)
        audit = self.audit([
            line_assistant([tool_use(
                "t1", "Bash", command="npm run build")]),
            line_tool_result("t1", "built in 2s"),
            line_assistant("The build succeeds."),
        ])
        self.assertEqual(audit["claims"][0]["verdict"],
                         dca.EVIDENCED)


class TestInputErrors(unittest.TestCase):
    def test_malformed_line_names_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text(
                json.dumps(line_user_text("hi")) + "\n"
                + "{not json\n", encoding="utf-8")
            with self.assertRaises(dca.ToolError) as cm:
                dca.audit_transcript(path)
        self.assertIn("line 2", str(cm.exception))

    def test_unrecognized_format_names_what_was_expected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.jsonl"
            path.write_text('{"a": 1}\n{"b": 2}\n',
                            encoding="utf-8")
            with self.assertRaises(dca.ToolError) as cm:
                dca.audit_transcript(path)
        msg = str(cm.exception)
        self.assertIn("Claude Code", msg)
        self.assertIn("tool_result", msg)

    def test_json_array_file_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "arr.jsonl"
            path.write_text('[{"type": "user"}]\n',
                            encoding="utf-8")
            with self.assertRaises(dca.ToolError) as cm:
                dca.audit_transcript(path)
        self.assertIn("line 1", str(cm.exception))

    def test_empty_transcript_is_a_clean_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("", encoding="utf-8")
            audit = dca.audit_transcript(path)
        self.assertEqual(audit["summary"]["claims"], 0)
        self.assertTrue(audit["clean"])


class TestCli(unittest.TestCase):
    def test_exit_codes_on_fixtures(self):
        code, out, err = run_cli("audit", str(HONEST))
        self.assertEqual(code, 0, err)
        self.assertIn("Verdict: CLEAN", out)
        code, out, err = run_cli("audit", str(LIAR))
        self.assertEqual(code, 1, err)
        self.assertIn("Verdict: NOT CLEAN", out)

    def test_missing_file_exits_2_in_both_modes(self):
        code, out, _ = run_cli("audit", "/no/such/file.jsonl")
        self.assertEqual(code, 2)
        self.assertIn("ERROR:", out)
        code, out, _ = run_cli("audit", "/no/such/file.jsonl",
                               "--json")
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(out))

    def test_argparse_error_is_json_in_json_mode(self):
        code, out, _ = run_cli("audit", "--json")
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(out))

    def test_json_summary_recounts_exactly(self):
        for fixture in (HONEST, LIAR):
            code, out, _ = run_cli("audit", str(fixture), "--json")
            data = json.loads(out)
            claims = data["claims"]
            recount = {
                "claims": len(claims),
                "evidenced": sum(
                    1 for c in claims
                    if c["verdict"] == "EVIDENCED"),
                "unevidenced": sum(
                    1 for c in claims
                    if c["verdict"] == "UNEVIDENCED"),
                "contradicted": sum(
                    1 for c in claims
                    if c["verdict"] == "CONTRADICTED"),
            }
            self.assertEqual(data["summary"], recount)
            self.assertEqual(
                data["clean"],
                recount["unevidenced"] == 0
                and recount["contradicted"] == 0)

    def test_empty_transcript_cli_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("\n\n", encoding="utf-8")
            code, out, _ = run_cli("audit", str(path))
        self.assertEqual(code, 0)
        self.assertIn("No completion claims found", out)

    def test_no_excerpts_leaks_no_fixture_prose(self):
        distinctive = ("zanzibar", "AssertionError",
                       "All tests pass now", "quokka")
        for extra in (["--no-excerpts"],
                      ["--json", "--no-excerpts"]):
            code, out, _ = run_cli("audit", str(LIAR), *extra)
            self.assertEqual(code, 1)
            for needle in distinctive:
                self.assertNotIn(needle, out, (extra, needle))
            self.assertIn("CONTRADICTED", out)
            if "--json" in extra:
                self.assertIn('"line": 6', out)
            else:
                self.assertIn("line 6", out)
        # ...while the same strings ARE present with excerpts on
        _, out, _ = run_cli("audit", str(LIAR))
        self.assertIn("zanzibar-quokka", out)

    def test_no_network_code_in_source(self):
        source = SRC.read_text(encoding="utf-8")
        for banned in ("import socket", "import urllib",
                       "import requests", "http.client",
                       "import ftplib", "import smtplib"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
