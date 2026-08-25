#!/usr/bin/env python3
"""Materialize the two new deterministic Git fixtures used by Phase 2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class FixtureDefinition:
    fixture_id: str
    target_name: str
    source_name: str
    test_name: str
    base_source: str
    candidate_source: str
    test_source: str
    base_time: str
    candidate_time: str


DEFINITIONS = (
    FixtureDefinition(
        fixture_id="phase2_boundary_error_v1",
        target_name="phase2_boundary_repo",
        source_name="tags.py",
        test_name="test_tags.py",
        base_source=(
            "def primary_tag(tags: list[str] | None) -> str | None:\n"
            "    if not tags:\n"
            "        return None\n"
            "    return tags[0].strip().lower()\n"
        ),
        candidate_source=(
            "def primary_tag(tags: list[str] | None) -> str | None:\n"
            "    if tags is None:\n"
            "        return None\n"
            "    return tags[0].strip().lower()\n"
        ),
        test_source=(
            "import unittest\n\n"
            "from tags import primary_tag\n\n\n"
            "class PrimaryTagTests(unittest.TestCase):\n"
            "    def test_empty_list_has_no_primary_tag(self):\n"
            "        self.assertIsNone(primary_tag([]))\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    unittest.main()\n"
        ),
        base_time="2026-01-02T00:00:00+00:00",
        candidate_time="2026-01-02T00:01:00+00:00",
    ),
    FixtureDefinition(
        fixture_id="phase2_permission_error_v1",
        target_name="phase2_permission_repo",
        source_name="permissions.py",
        test_name="test_permissions.py",
        base_source=(
            "def can_delete_project(role: str) -> bool:\n"
            "    return role == \"admin\"\n"
        ),
        candidate_source=(
            "def can_delete_project(role: str) -> bool:\n"
            "    return role in {\"admin\", \"viewer\"}\n"
        ),
        test_source=(
            "import unittest\n\n"
            "from permissions import can_delete_project\n\n\n"
            "class DeletePermissionTests(unittest.TestCase):\n"
            "    def test_viewer_cannot_delete_project(self):\n"
            "        self.assertFalse(can_delete_project(\"viewer\"))\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    unittest.main()\n"
        ),
        base_time="2026-01-03T00:00:00+00:00",
        candidate_time="2026-01-03T00:01:00+00:00",
    ),
)


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


def run(target: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=target,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def materialize(definition: FixtureDefinition) -> dict[str, str]:
    target = ROOT / ".fixtures" / definition.target_name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    run(target, "git", "init", "-b", "main")
    (target / definition.source_name).write_text(definition.base_source, encoding="utf-8")
    (target / definition.test_name).write_text(definition.test_source, encoding="utf-8")
    run(target, "git", "add", definition.source_name, definition.test_name)
    run(
        target,
        "git",
        "commit",
        "-m",
        "base fixture",
        env=commit_env(definition.base_time),
    )
    base_commit = run(target, "git", "rev-parse", "HEAD")
    (target / definition.source_name).write_text(definition.candidate_source, encoding="utf-8")
    run(target, "git", "add", definition.source_name)
    run(
        target,
        "git",
        "commit",
        "-m",
        f"introduce {definition.fixture_id} regression",
        env=commit_env(definition.candidate_time),
    )
    candidate_commit = run(target, "git", "rev-parse", "HEAD")
    diff_text = run(target, "git", "diff", "--no-ext-diff", base_commit, candidate_commit) + "\n"
    return {
        "base_commit": base_commit,
        "candidate_commit": candidate_commit,
        "diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
        "diff_text": diff_text,
    }


def validate_frozen(definition: FixtureDefinition, actual: dict[str, str]) -> None:
    fixture_dir = ROOT / "fixtures" / definition.fixture_id.removesuffix("_v1")
    fixture = json.loads((fixture_dir / "fixture.json").read_text(encoding="utf-8"))
    tracked_diff = (fixture_dir / "diff.patch").read_text(encoding="utf-8")
    for key in ("base_commit", "candidate_commit", "diff_sha256"):
        if fixture.get(key) != actual[key]:
            raise RuntimeError(f"{definition.fixture_id}:{key}: identity mismatch")
    if tracked_diff != actual["diff_text"]:
        raise RuntimeError(f"{definition.fixture_id}: tracked diff mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for definition in DEFINITIONS:
        actual = materialize(definition)
        if args.check:
            validate_frozen(definition, actual)
        print(
            f"fixture_id={definition.fixture_id} "
            f"base={actual['base_commit']} candidate={actual['candidate_commit']} "
            f"diff_sha256={actual['diff_sha256']}"
        )
        if not args.check:
            print(actual["diff_text"], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
