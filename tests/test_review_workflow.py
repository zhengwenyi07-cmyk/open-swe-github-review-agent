from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from open_swe_review_agent.contracts import ReviewContractError, validate_review
from open_swe_review_agent.diff_parser import changed_lines
from open_swe_review_agent.fakes import FakeModel, FakeSandbox
from open_swe_review_agent.render import render_markdown
from open_swe_review_agent.workflow import ReviewRequest, ReviewWorkflow

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures" / "phase1_logic_error"


def model_output() -> dict[str, object]:
    return {
        "summary": "The changed guard introduces a reachable division-by-zero failure.",
        "findings": [
            {
                "file": "calculator.py",
                "line": 2,
                "severity": "high",
                "category": "correctness",
                "assessment": "confirmed",
                "evidence": "The new guard checks numerator, so ratio(5, 0) reaches division by zero.",
                "recommendation": "Restore the denominator == 0 guard.",
            }
        ],
        "uncertainties": [],
        "decision": "REQUEST_CHANGES",
    }


class ReviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads((FIXTURE_DIR / "fixture.json").read_text(encoding="utf-8"))
        cls.diff_text = (FIXTURE_DIR / "diff.patch").read_text(encoding="utf-8")

    def request(self) -> ReviewRequest:
        return ReviewRequest(
            repository=self.fixture["repository"],
            base_commit=self.fixture["base_commit"],
            candidate_commit=self.fixture["candidate_commit"],
            test_commands=tuple(self.fixture["test_commands"]),
        )

    def sandbox(self) -> FakeSandbox:
        return FakeSandbox(
            diff_text=self.diff_text,
            expected_base=self.fixture["base_commit"],
            expected_candidate=self.fixture["candidate_commit"],
            test_returncodes={self.fixture["test_commands"][0]: 1},
        )

    def test_fixture_hash_and_changed_line_are_frozen(self) -> None:
        self.assertEqual(
            hashlib.sha256((FIXTURE_DIR / "diff.patch").read_bytes()).hexdigest(),
            self.fixture["diff_sha256"],
        )
        self.assertEqual(changed_lines(self.diff_text), {("calculator.py", 2)})

    def test_materialized_repository_has_frozen_commits_and_diff(self) -> None:
        subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "materialize_phase1_fixture.py")],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        repository = ROOT / ".fixtures" / "phase1_repo"
        candidate = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        self.assertEqual(candidate, self.fixture["candidate_commit"])
        actual_diff = subprocess.run(
            ["git", "diff", "--no-ext-diff", self.fixture["base_commit"], candidate],
            cwd=repository,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
        self.assertEqual(actual_diff, self.diff_text)

    def test_successful_fake_workflow_is_schema_valid_and_renderable(self) -> None:
        model = FakeModel(model_output())
        result = ReviewWorkflow(model=model, sandbox=self.sandbox()).run(self.request())
        self.assertEqual(model.calls, 1)
        self.assertEqual(result["commit_sha"], self.fixture["candidate_commit"])
        self.assertFalse(result["tests"]["passed"])
        self.assertEqual(result["decision"], "REQUEST_CHANGES")
        markdown = render_markdown(result)
        self.assertIn("`calculator.py:2`", markdown)
        self.assertIn("REQUEST_CHANGES", markdown)

    def test_finding_outside_changed_line_is_rejected(self) -> None:
        output = model_output()
        output["findings"][0]["line"] = 3
        with self.assertRaisesRegex(ReviewContractError, "outside the changed diff"):
            ReviewWorkflow(model=FakeModel(output), sandbox=self.sandbox()).run(self.request())

    def test_duplicate_finding_is_rejected(self) -> None:
        output = model_output()
        output["findings"].append(dict(output["findings"][0]))
        with self.assertRaisesRegex(ReviewContractError, "duplicate finding"):
            ReviewWorkflow(model=FakeModel(output), sandbox=self.sandbox()).run(self.request())

    def test_approve_with_findings_is_rejected(self) -> None:
        output = model_output()
        output["decision"] = "APPROVE"
        with self.assertRaisesRegex(ReviewContractError, "APPROVE cannot contain findings"):
            ReviewWorkflow(model=FakeModel(output), sandbox=self.sandbox()).run(self.request())

    def test_request_changes_requires_confirmed_high_finding(self) -> None:
        output = model_output()
        output["findings"][0]["assessment"] = "suggestion"
        with self.assertRaisesRegex(ReviewContractError, "requires a confirmed"):
            ReviewWorkflow(model=FakeModel(output), sandbox=self.sandbox()).run(self.request())

    def test_uncertainty_is_separate_from_findings(self) -> None:
        review = {
            "commit_sha": self.fixture["candidate_commit"],
            "summary": "No confirmed defect, but runtime behavior needs evidence.",
            "findings": [],
            "uncertainties": [
                {
                    "file": "calculator.py",
                    "line": 2,
                    "question": "Is zero denominator intentionally allowed?",
                    "evidence_needed": "A documented API contract.",
                }
            ],
            "tests": {"commands": ["python -m unittest"], "passed": True},
            "decision": "COMMENT",
        }
        validate_review(review, self.diff_text)

    def test_unknown_schema_field_is_rejected(self) -> None:
        review = {
            **model_output(),
            "commit_sha": self.fixture["candidate_commit"],
            "tests": {"commands": ["python -m unittest"], "passed": False},
            "raw_response": "must not be accepted",
        }
        with self.assertRaises(ReviewContractError):
            validate_review(review, self.diff_text)


if __name__ == "__main__":
    unittest.main()
