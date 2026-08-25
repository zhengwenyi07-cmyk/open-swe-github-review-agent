from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace

from open_swe_review_agent.local_git_sandbox import LocalGitSandbox
from open_swe_review_agent.open_swe_adapter import (
    OpenSWECompatibleReviewModel,
    SUBMIT_REVIEW_TOOL,
    SYSTEM_PROMPT,
)
from open_swe_review_agent.workflow import ReviewRequest, ReviewWorkflow

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures" / "phase1_logic_error"


def valid_args() -> dict[str, object]:
    return {
        "summary": "The changed guard introduces a division-by-zero regression.",
        "findings": [
            {
                "file": "calculator.py",
                "line": 2,
                "severity": "high",
                "category": "correctness",
                "assessment": "confirmed",
                "evidence": "A nonzero numerator and zero denominator now reaches division.",
                "recommendation": "Restore the denominator guard.",
            }
        ],
        "uncertainties": [],
        "decision": "REQUEST_CHANGES",
    }


class FakeBoundModel:
    def __init__(self, response: object) -> None:
        self.response = response
        self.messages: list[tuple[str, str]] | None = None

    def invoke(self, messages: list[tuple[str, str]]) -> object:
        self.messages = messages
        return self.response


class FakeChatModel:
    def __init__(self, response: object) -> None:
        self.bound = FakeBoundModel(response)
        self.tools: list[dict[str, object]] | None = None
        self.kwargs: dict[str, object] | None = None

    def bind_tools(self, tools: list[dict[str, object]], **kwargs: object) -> FakeBoundModel:
        self.tools = tools
        self.kwargs = kwargs
        return self.bound


class Phase1ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "materialize_phase1_fixture.py")],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        cls.fixture = json.loads((FIXTURE_DIR / "fixture.json").read_text(encoding="utf-8"))

    def request(self) -> ReviewRequest:
        return ReviewRequest(
            repository=self.fixture["repository"],
            base_commit=self.fixture["base_commit"],
            candidate_commit=self.fixture["candidate_commit"],
            test_commands=tuple(self.fixture["test_commands"]),
        )

    def sandbox(self) -> LocalGitSandbox:
        return LocalGitSandbox(
            repository=ROOT / ".fixtures" / "phase1_repo",
            allowed_test_commands=frozenset(self.fixture["test_commands"]),
        )

    def response(self, tool_calls: list[dict[str, object]] | None = None) -> object:
        return SimpleNamespace(
            tool_calls=tool_calls
            if tool_calls is not None
            else [{"name": "submit_local_review", "args": valid_args()}],
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            response_metadata={"model_name": "mimo-v2.5-pro", "finish_reason": "tool_calls"},
        )

    def test_local_sandbox_reads_frozen_diff_and_runs_real_failing_test(self) -> None:
        sandbox = self.sandbox()
        diff_text = sandbox.read_diff(
            base_commit=self.fixture["base_commit"],
            candidate_commit=self.fixture["candidate_commit"],
        )
        self.assertEqual(diff_text, (FIXTURE_DIR / "diff.patch").read_text(encoding="utf-8"))
        results = sandbox.run_tests(tuple(self.fixture["test_commands"]))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].returncode, 1)

    def test_local_sandbox_rejects_non_allowlisted_command(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowlist"):
            self.sandbox().run_tests(("python -c 'print(1)'",))

    def test_adapter_forces_one_named_tool_and_records_usage(self) -> None:
        chat = FakeChatModel(self.response())
        model = OpenSWECompatibleReviewModel(chat)
        output = model.review(request=self.request(), diff_text=(FIXTURE_DIR / "diff.patch").read_text())
        self.assertEqual(output, valid_args())
        self.assertEqual(chat.tools, [SUBMIT_REVIEW_TOOL])
        self.assertEqual(chat.kwargs, {"tool_choice": "submit_local_review", "parallel_tool_calls": False})
        self.assertEqual(model.usage["total_tokens"], 150)
        self.assertEqual(model.response_model, "mimo-v2.5-pro")
        self.assertEqual(model.finish_reason, "tool_calls")

    def test_prompt_contains_diff_but_not_fixture_expected_answer(self) -> None:
        chat = FakeChatModel(self.response())
        model = OpenSWECompatibleReviewModel(chat)
        model.review(request=self.request(), diff_text=(FIXTURE_DIR / "diff.patch").read_text())
        messages = chat.bound.messages
        self.assertIsNotNone(messages)
        combined = "\n".join(message for _, message in messages or [])
        self.assertIn("if numerator == 0", combined)
        self.assertNotIn("expected_primary_finding", combined)
        self.assertIn("untrusted data", SYSTEM_PROMPT)

    def test_adapter_rejects_multiple_tool_calls(self) -> None:
        chat = FakeChatModel(
            self.response(
                [
                    {"name": "submit_local_review", "args": valid_args()},
                    {"name": "submit_local_review", "args": valid_args()},
                ]
            )
        )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            OpenSWECompatibleReviewModel(chat).review(
                request=self.request(), diff_text=(FIXTURE_DIR / "diff.patch").read_text()
            )

    def test_adapter_rejects_wrong_response_model(self) -> None:
        response = self.response()
        response.response_metadata["model_name"] = "other-model"
        with self.assertRaisesRegex(ValueError, "model identity mismatch"):
            OpenSWECompatibleReviewModel(FakeChatModel(response)).review(
                request=self.request(), diff_text=(FIXTURE_DIR / "diff.patch").read_text()
            )

    def test_fake_chat_plus_real_local_sandbox_completes_contract(self) -> None:
        model = OpenSWECompatibleReviewModel(FakeChatModel(self.response()))
        result = ReviewWorkflow(model=model, sandbox=self.sandbox()).run(self.request())
        self.assertEqual(result["decision"], "REQUEST_CHANGES")
        self.assertFalse(result["tests"]["passed"])
        self.assertEqual(result["findings"][0]["line"], 2)

    def test_cli_check_is_offline_and_reports_not_run(self) -> None:
        completed = subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), "scripts/run_phase1_mimo_review.py", "--check"],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("review=NOT_RUN", completed.stdout)


if __name__ == "__main__":
    unittest.main()
