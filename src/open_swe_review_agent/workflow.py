"""Minimal local review workflow with model and sandbox dependency injection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import validate_review


@dataclass(frozen=True)
class TestExecution:
    command: str
    returncode: int


@dataclass(frozen=True)
class ReviewRequest:
    repository: str
    base_commit: str
    candidate_commit: str
    test_commands: tuple[str, ...]
    pull_number: int | None = None
    pull_title: str = ""
    pull_body: str = ""


class ReviewModel(Protocol):
    def review(self, *, request: ReviewRequest, diff_text: str) -> dict[str, Any]: ...


class ReviewSandbox(Protocol):
    def read_diff(self, *, base_commit: str, candidate_commit: str) -> str: ...

    def run_tests(self, commands: tuple[str, ...]) -> list[TestExecution]: ...


class ReviewWorkflow:
    """Materialize a diff, ask one reviewer model, run checks, and validate output."""

    def __init__(self, *, model: ReviewModel, sandbox: ReviewSandbox) -> None:
        self._model = model
        self._sandbox = sandbox

    def run(self, request: ReviewRequest) -> dict[str, Any]:
        diff_text = self._sandbox.read_diff(
            base_commit=request.base_commit,
            candidate_commit=request.candidate_commit,
        )
        candidate = self._model.review(request=request, diff_text=diff_text)
        tests = self._sandbox.run_tests(request.test_commands)

        result = dict(candidate)
        result["commit_sha"] = request.candidate_commit
        result["tests"] = {
            "commands": [item.command for item in tests],
            "passed": bool(tests) and all(item.returncode == 0 for item in tests),
        }
        validate_review(result, diff_text)
        return result
