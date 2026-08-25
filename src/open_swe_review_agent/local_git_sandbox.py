"""Small local-only Git sandbox for the frozen Phase 1 fixture."""

from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .workflow import TestExecution


@dataclass
class LocalGitSandbox:
    repository: Path
    allowed_test_commands: frozenset[str]
    timeout_seconds: int = 30
    executions: list[TestExecution] = field(default_factory=list, init=False)

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.repository,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout_seconds,
        )
        return completed.stdout

    def read_diff(self, *, base_commit: str, candidate_commit: str) -> str:
        actual_candidate = self._git("rev-parse", "HEAD").strip()
        if actual_candidate != candidate_commit:
            raise ValueError("local fixture is not at the frozen candidate commit")
        self._git("cat-file", "-e", f"{base_commit}^{{commit}}")
        return self._git("diff", "--no-ext-diff", base_commit, candidate_commit)

    def run_tests(self, commands: tuple[str, ...]) -> list[TestExecution]:
        results: list[TestExecution] = []
        for command in commands:
            if command not in self.allowed_test_commands:
                raise ValueError("test command is outside the fixture allowlist")
            argv = shlex.split(command)
            if not argv or argv[0] not in {"python", "python3"}:
                raise ValueError("only allowlisted Python test commands are supported")
            argv[0] = sys.executable
            completed = subprocess.run(
                argv,
                cwd=self.repository,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout_seconds,
            )
            results.append(TestExecution(command=command, returncode=completed.returncode))
        self.executions = results
        return results
