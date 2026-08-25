from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from open_swe_review_agent.local_git_sandbox import LocalGitSandbox
from scripts.run_phase2_mimo_smoke import (
    OUTPUT_DIR,
    TASKS,
    execute,
    load_fixture,
    load_scoring_rubric,
    materialize_all,
    model_response_failure_reason,
    score_reviews,
)

ROOT = Path(__file__).resolve().parents[1]


def primary_review(fixture: dict[str, object], *, severity: str | None = None) -> dict[str, object]:
    expected = dict(fixture["expected_primary_finding"])
    evidence_by_fixture = {
        "phase1_logic_error_v1": "A zero denominator now reaches division and raises ZeroDivisionError.",
        "phase2_boundary_error_v1": "Empty tags reach tags[0], causing IndexError for an empty list.",
        "phase2_permission_error_v1": "A viewer is now authorized to delete despite lacking permission.",
    }
    return {
        "summary": "The candidate introduces the frozen primary regression.",
        "findings": [
            {
                "file": expected["file"],
                "line": expected["line"],
                "severity": severity or expected["severity"],
                "category": expected["category"],
                "assessment": "confirmed",
                "evidence": evidence_by_fixture[str(fixture["fixture_id"])],
                "recommendation": "Restore the previous guard.",
            }
        ],
        "uncertainties": [],
        "decision": "REQUEST_CHANGES" if (severity or expected["severity"]) in {"high", "critical"} else "COMMENT",
    }


class Phase2SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        materialize_all()
        cls.fixtures = [load_fixture(spec) for spec in TASKS]

    def test_three_fixtures_have_distinct_frozen_identities(self) -> None:
        self.assertEqual(len(self.fixtures), 3)
        self.assertEqual(len({item["fixture_id"] for item in self.fixtures}), 3)
        self.assertEqual(len({item["candidate_commit"] for item in self.fixtures}), 3)

    def test_two_new_fixtures_materialize_byte_for_byte(self) -> None:
        completed = subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), "scripts/materialize_phase2_fixtures.py", "--check"],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("phase2_boundary_error_v1", completed.stdout)
        self.assertIn("phase2_permission_error_v1", completed.stdout)

    def test_each_candidate_runs_its_real_failing_test(self) -> None:
        for spec, fixture in zip(TASKS, self.fixtures, strict=True):
            sandbox = LocalGitSandbox(
                repository=spec.repository,
                allowed_test_commands=frozenset(fixture["test_commands"]),
            )
            results = sandbox.run_tests(tuple(fixture["test_commands"]))
            self.assertEqual(results[0].returncode, 1, fixture["fixture_id"])

    def test_perfect_reviews_score_full_recall_precision_and_calibration(self) -> None:
        records = [(fixture, primary_review(fixture)) for fixture in self.fixtures]
        score = score_reviews(records)
        self.assertEqual(score["semantic_rubric_recall"]["found"], 3)
        self.assertEqual(score["semantic_rubric_precision"]["rate"], 1.0)
        self.assertEqual(score["severity_calibration"]["exact_match_rate"], 1.0)
        self.assertEqual(score["severity_calibration"]["mean_absolute_error"], 0.0)

    def test_severity_overestimate_is_separate_from_recall(self) -> None:
        fixture = self.fixtures[0]
        score = score_reviews([(fixture, primary_review(fixture, severity="critical"))])
        self.assertEqual(score["semantic_rubric_recall"]["found"], 1)
        self.assertEqual(score["severity_calibration"]["overestimation_count"], 1)
        self.assertEqual(score["severity_calibration"]["mean_absolute_error"], 1.0)
        self.assertEqual(score["severity_calibration"]["mean_overestimation_magnitude"], 1.0)

    def test_severity_underestimate_records_direction_and_magnitude(self) -> None:
        fixture = self.fixtures[0]
        score = score_reviews([(fixture, primary_review(fixture, severity="low"))])
        self.assertEqual(score["semantic_rubric_recall"]["found"], 1)
        self.assertEqual(score["severity_calibration"]["underestimation_count"], 1)
        self.assertEqual(score["severity_calibration"]["mean_underestimation_magnitude"], 2.0)

    def test_structural_match_without_semantic_root_cause_is_not_recall(self) -> None:
        fixture = self.fixtures[0]
        review = primary_review(fixture)
        review["findings"][0]["evidence"] = "The changed condition may behave differently."
        review["findings"][0]["recommendation"] = "Review this line."
        score = score_reviews([(fixture, review)])
        self.assertEqual(score["semantic_rubric_recall"]["found"], 0)
        self.assertEqual(score["false_findings"], 1)

    def test_scoring_identity_must_match_fixture_expectation(self) -> None:
        source = json.loads((ROOT / "fixtures" / "phase2_scoring.json").read_text(encoding="utf-8"))
        source["tasks"][0]["severity"] = "critical"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scoring.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with patch("scripts.run_phase2_mimo_smoke.SCORING_PATH", path):
                with self.assertRaisesRegex(RuntimeError, "FIXTURE_IDENTITY_MISMATCH"):
                    load_scoring_rubric()

    def test_unmatched_finding_reduces_precision(self) -> None:
        fixture = self.fixtures[0]
        review = primary_review(fixture)
        review["findings"].append(
            {
                "file": fixture["expected_primary_finding"]["file"],
                "line": fixture["expected_primary_finding"]["line"],
                "severity": "low",
                "category": "maintainability",
                "assessment": "suggestion",
                "evidence": "Naming could be clearer.",
                "recommendation": "Rename the function.",
            }
        )
        score = score_reviews([(fixture, review)])
        self.assertEqual(score["false_findings"], 1)
        self.assertEqual(score["semantic_rubric_precision"]["rate"], 0.5)

    def test_duplicate_primary_finding_is_counted(self) -> None:
        fixture = self.fixtures[0]
        review = primary_review(fixture)
        review["findings"].append(dict(review["findings"][0]))
        score = score_reviews([(fixture, review)])
        self.assertEqual(score["duplicate_findings"], 1)

    def test_expected_answers_are_not_in_tracked_diffs(self) -> None:
        for spec, fixture in zip(TASKS, self.fixtures, strict=True):
            diff_text = (spec.fixture_dir / "diff.patch").read_text(encoding="utf-8")
            self.assertNotIn("expected_primary_finding", diff_text)
            self.assertNotIn("prohibited_false_findings", diff_text)
            self.assertNotIn(json.dumps(fixture["expected_primary_finding"]), diff_text)

    def test_paid_entry_refuses_contract_gate_before_model_creation(self) -> None:
        if OUTPUT_DIR.exists():
            self.skipTest("formal Phase 2 output already exists")
        environment = {
            **os.environ,
            "OPEN_SWE_PHASE2_ALLOW_NETWORK": "YES_ONCE",
            "MIMO_ACCOUNT_TYPE": "PAY_AS_YOU_GO",
            "MIMO_API_KEY": "test-only-placeholder",
        }
        with patch.dict(os.environ, environment, clear=True), patch(
            "scripts.run_phase2_mimo_smoke.ensure_clean_committed_contract",
            side_effect=RuntimeError("WORKTREE_NOT_CLEAN"),
        ), patch("scripts.run_phase2_mimo_smoke.create_mimo_model") as factory:
            with self.assertRaisesRegex(RuntimeError, "WORKTREE_NOT_CLEAN"):
                execute("OPEN_SWE_PHASE2_THREE_TASK_SMOKE")
            factory.assert_not_called()

    def test_one_task_failure_is_saved_and_later_tasks_continue(self) -> None:
        fixtures = self.fixtures

        class FakeSandbox:
            def __init__(self, diff_text: str, command: str) -> None:
                self.diff_text = diff_text
                self.executions = [SimpleNamespace(command=command, returncode=1)]

            def read_diff(self, **_: object) -> str:
                return self.diff_text

            def run_tests(self, _: object) -> list[object]:
                return self.executions

        sandboxes = [
            FakeSandbox(
                (spec.fixture_dir / "diff.patch").read_text(encoding="utf-8"),
                str(fixture["test_commands"][0]),
            )
            for spec, fixture in zip(TASKS, fixtures, strict=True)
        ]

        class FakeModel:
            def __init__(self, index: int) -> None:
                self.index = index
                self.calls = 0
                self.usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
                self.response_model = "mimo-v2.5-pro"
                self.finish_reason = "tool_calls"

            def review(self, **_: object) -> dict[str, object]:
                self.calls = 1
                if self.index == 0:
                    raise ValueError("SECRET_REMOTE_RESPONSE")
                return primary_review(fixtures[self.index])

        models = [FakeModel(index) for index in range(3)]

        environment = {
            **os.environ,
            "OPEN_SWE_PHASE2_ALLOW_NETWORK": "YES_ONCE",
            "MIMO_ACCOUNT_TYPE": "PAY_AS_YOU_GO",
            "MIMO_API_KEY": "test-only-placeholder",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, environment, clear=True), patch(
            "scripts.run_phase2_mimo_smoke.OUTPUT_DIR", Path(directory) / "phase2"
        ), patch(
            "scripts.run_phase2_mimo_smoke.ensure_clean_committed_contract",
            return_value="a" * 40,
        ), patch("scripts.run_phase2_mimo_smoke.load_preflight"), patch(
            "scripts.run_phase2_mimo_smoke.materialize_all"
        ), patch(
            "scripts.run_phase2_mimo_smoke.LocalGitSandbox", side_effect=sandboxes
        ), patch(
            "scripts.run_phase2_mimo_smoke.create_mimo_model", return_value=object()
        ), patch(
            "scripts.run_phase2_mimo_smoke.OpenSWECompatibleReviewModel", side_effect=models
        ):
            execute("OPEN_SWE_PHASE2_THREE_TASK_SMOKE")
            output = Path(directory) / "phase2"
            failure_text = (output / "logic_error" / "failure.json").read_text(encoding="utf-8")
            self.assertNotIn("SECRET_REMOTE_RESPONSE", failure_text)
            failure = json.loads(failure_text)
            self.assertEqual(failure["failure_stage"], "MODEL_RESPONSE")
            self.assertEqual(failure["failure_reason"], "MODEL_API_OR_RESPONSE_FAILURE")
            self.assertTrue((output / "boundary_error" / "review.json").is_file())
            self.assertTrue((output / "permission_error" / "review.json").is_file())
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "COMPLETED_WITH_FAILURES")
            self.assertEqual(summary["successful_reviews"], 2)
            self.assertEqual(summary["failed_reviews"], 1)
            self.assertEqual(summary["human_evaluation"]["status"], "PENDING_HUMAN_REVIEW")

    def test_model_response_failures_have_fixed_diagnostic_codes(self) -> None:
        cases = {
            "MiMo response model identity mismatch": "MODEL_IDENTITY_MISMATCH",
            "MiMo response finish reason mismatch": "FINISH_REASON_MISMATCH",
            "expected exactly one structured review tool call": "TOOL_CALL_COUNT_MISMATCH",
            "structured review tool call has invalid semantics": "TOOL_CALL_SEMANTICS_MISMATCH",
            "SECRET_REMOTE_RESPONSE": "MODEL_API_OR_RESPONSE_FAILURE",
        }
        for message, expected in cases.items():
            self.assertEqual(model_response_failure_reason(ValueError(message)), expected)

    def test_cli_check_is_offline_and_reports_a_valid_lifecycle_state(self) -> None:
        completed = subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), "scripts/run_phase2_mimo_smoke.py", "--check"],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("VALID phase2-smoke", completed.stdout)
        self.assertIn("github_write=false", completed.stdout)


if __name__ == "__main__":
    unittest.main()
