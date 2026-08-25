"""Deterministic fake components for Phase 1 offline contract tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .workflow import ReviewRequest, TestExecution


@dataclass
class FakeSandbox:
    diff_text: str
    expected_base: str
    expected_candidate: str
    test_returncodes: dict[str, int]

    def read_diff(self, *, base_commit: str, candidate_commit: str) -> str:
        if base_commit != self.expected_base or candidate_commit != self.expected_candidate:
            raise ValueError("fixture commit identity mismatch")
        return self.diff_text

    def run_tests(self, commands: tuple[str, ...]) -> list[TestExecution]:
        return [TestExecution(command, self.test_returncodes[command]) for command in commands]


@dataclass
class FakeModel:
    output: dict[str, Any]
    calls: int = 0

    def review(self, *, request: ReviewRequest, diff_text: str) -> dict[str, Any]:
        if not diff_text.strip():
            raise ValueError("empty diff")
        self.calls += 1
        return self.output
