#!/usr/bin/env python3
"""Create the ignored two-commit local repository used by the Phase 1 fixture."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".fixtures" / "phase1_repo"
BASE_SOURCE = """def ratio(numerator: int, denominator: int) -> float:\n    if denominator == 0:\n        return 0.0\n    return numerator / denominator\n"""
CANDIDATE_SOURCE = """def ratio(numerator: int, denominator: int) -> float:\n    if numerator == 0:\n        return 0.0\n    return numerator / denominator\n"""
TEST_SOURCE = """import unittest\n\nfrom calculator import ratio\n\n\nclass RatioTests(unittest.TestCase):\n    def test_zero_denominator(self):\n        self.assertEqual(ratio(5, 0), 0.0)\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n"""


def run(*args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=TARGET,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def commit_env(timestamp: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "Open SWE Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Open SWE Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_DATE": timestamp,
        }
    )
    return env


def main() -> int:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    run("git", "init", "-b", "main")
    (TARGET / "calculator.py").write_text(BASE_SOURCE, encoding="utf-8")
    (TARGET / "test_calculator.py").write_text(TEST_SOURCE, encoding="utf-8")
    run("git", "add", "calculator.py", "test_calculator.py")
    run("git", "commit", "-m", "base fixture", env=commit_env("2026-01-01T00:00:00+00:00"))
    base = run("git", "rev-parse", "HEAD")

    (TARGET / "calculator.py").write_text(CANDIDATE_SOURCE, encoding="utf-8")
    run("git", "add", "calculator.py")
    run("git", "commit", "-m", "introduce denominator guard bug", env=commit_env("2026-01-01T00:01:00+00:00"))
    candidate = run("git", "rev-parse", "HEAD")
    diff_text = run("git", "diff", "--no-ext-diff", base, candidate) + "\n"

    print(f"base_commit={base}")
    print(f"candidate_commit={candidate}")
    print(diff_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
