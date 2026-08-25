#!/usr/bin/env python3
"""Run the single fixed-diff MiMo Phase 1 review after explicit approval."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from open_swe_review_agent.contracts import validate_review
from open_swe_review_agent.local_git_sandbox import LocalGitSandbox
from open_swe_review_agent.mimo import MIMO_MODEL, create_mimo_model
from open_swe_review_agent.open_swe_adapter import OpenSWECompatibleReviewModel
from open_swe_review_agent.render import render_markdown
from open_swe_review_agent.workflow import ReviewRequest, ReviewWorkflow

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures" / "phase1_logic_error" / "fixture.json"
TRACKED_DIFF = ROOT / "fixtures" / "phase1_logic_error" / "diff.patch"
REPOSITORY = ROOT / ".fixtures" / "phase1_repo"
PREFLIGHT = ROOT / "artifacts" / "mimo_preflight.json"
OUTPUT_DIR = ROOT / "artifacts" / "phase1"
ACK = "OPEN_SWE_PHASE1_FIXED_DIFF_REVIEW"
UPSTREAM_COMMIT = "daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc"


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, object]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    actual_hash = hashlib.sha256(TRACKED_DIFF.read_bytes()).hexdigest()
    if actual_hash != fixture["diff_sha256"]:
        raise RuntimeError("FIXTURE_DIFF_HASH_MISMATCH")
    return fixture


def run(*args: str, cwd: Path = ROOT) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def ensure_clean_committed_contract() -> str:
    if run("git", "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("WORKTREE_NOT_CLEAN")
    required = (
        "scripts/run_phase1_mimo_review.py",
        "src/open_swe_review_agent/open_swe_adapter.py",
        "src/open_swe_review_agent/local_git_sandbox.py",
        "schemas/review.schema.json",
        "fixtures/phase1_logic_error/fixture.json",
        "fixtures/phase1_logic_error/diff.patch",
    )
    run("git", "ls-files", "--error-unmatch", "--", *required)
    return run("git", "rev-parse", "HEAD")


def load_preflight() -> dict[str, object]:
    if not PREFLIGHT.is_file():
        raise RuntimeError("PREFLIGHT_REQUIRED")
    evidence = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if evidence.get("status") != "PASS" or evidence.get("configured_model") != MIMO_MODEL:
        raise RuntimeError("PREFLIGHT_INVALID")
    if evidence.get("model") != MIMO_MODEL or evidence.get("response_model") != MIMO_MODEL:
        raise RuntimeError("PREFLIGHT_INVALID")
    if evidence.get("finish_reason") != "tool_calls":
        raise RuntimeError("PREFLIGHT_INVALID")
    if evidence.get("transport") != "OPENAI_CHAT_COMPLETIONS" or evidence.get("tool_calls") != 1:
        raise RuntimeError("PREFLIGHT_INVALID")
    return evidence


def materialize_fixture() -> None:
    run(str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "materialize_phase1_fixture.py"))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def execute(acknowledgement: str, fixture_path: Path) -> None:
    if acknowledgement != ACK:
        raise RuntimeError("ACKNOWLEDGEMENT_REQUIRED")
    if os.environ.get("OPEN_SWE_MIMO_ALLOW_NETWORK") != "YES_ONCE":
        raise RuntimeError("NETWORK_GATE_REQUIRED")
    if os.environ.get("MIMO_ACCOUNT_TYPE") != "PAY_AS_YOU_GO":
        raise RuntimeError("ACCOUNT_TYPE_MISMATCH")
    if OUTPUT_DIR.exists():
        raise RuntimeError("PHASE1_OUTPUT_ALREADY_EXISTS")

    contract_commit = ensure_clean_committed_contract()
    load_preflight()
    fixture = load_fixture(fixture_path)
    api_key = os.environ.get("MIMO_API_KEY", "")
    materialize_fixture()

    sandbox = LocalGitSandbox(
        repository=REPOSITORY,
        allowed_test_commands=frozenset(fixture["test_commands"]),
    )
    request = ReviewRequest(
        repository=str(fixture["repository"]),
        base_commit=str(fixture["base_commit"]),
        candidate_commit=str(fixture["candidate_commit"]),
        test_commands=tuple(fixture["test_commands"]),
    )
    actual_diff = sandbox.read_diff(
        base_commit=request.base_commit,
        candidate_commit=request.candidate_commit,
    )
    if actual_diff != TRACKED_DIFF.read_text(encoding="utf-8"):
        raise RuntimeError("MATERIALIZED_FIXTURE_DIFF_MISMATCH")
    model = OpenSWECompatibleReviewModel(create_mimo_model(api_key))

    started = time.monotonic()
    review = ReviewWorkflow(model=model, sandbox=sandbox).run(request)
    elapsed = time.monotonic() - started
    test_returncode = sandbox.executions[0].returncode if sandbox.executions else None
    summary: dict[str, object] = {
        "status": "PASS",
        "adapter_kind": "OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE",
        "contract_commit": contract_commit,
        "upstream_commit": UPSTREAM_COMMIT,
        "model": MIMO_MODEL,
        "response_model": model.response_model,
        "finish_reason": model.finish_reason,
        "model_calls": model.calls,
        **model.usage,
        "elapsed_seconds": round(elapsed, 3),
        "test_returncode": test_returncode,
        "schema_valid": True,
        "github_api_called": False,
        "github_write_performed": False,
    }

    atomic_json(OUTPUT_DIR / "review.json", review)
    atomic_text(OUTPUT_DIR / "review.md", render_markdown(review))
    atomic_json(OUTPUT_DIR / "run_summary.json", summary)


def check() -> None:
    fixture = load_fixture()
    if fixture["candidate_commit"] != "746e90b56d3150d96acbff4a0f02308ab151669c":
        raise RuntimeError("FIXTURE_IDENTITY_MISMATCH")
    preflight = "NOT_RUN"
    if PREFLIGHT.exists():
        load_preflight()
        preflight = "PASS"
    review = "NOT_RUN"
    review_path = OUTPUT_DIR / "review.json"
    if review_path.exists():
        payload = json.loads(review_path.read_text(encoding="utf-8"))
        validate_review(payload, TRACKED_DIFF.read_text(encoding="utf-8"))
        expected_markdown = render_markdown(payload)
        if (OUTPUT_DIR / "review.md").read_text(encoding="utf-8") != expected_markdown:
            raise RuntimeError("REVIEW_MARKDOWN_MISMATCH")
        summary = json.loads((OUTPUT_DIR / "run_summary.json").read_text(encoding="utf-8"))
        if summary.get("status") != "PASS" or summary.get("model") != MIMO_MODEL:
            raise RuntimeError("RUN_SUMMARY_INVALID")
        if summary.get("response_model") != MIMO_MODEL or summary.get("finish_reason") != "tool_calls":
            raise RuntimeError("RUN_SUMMARY_INVALID")
        review = "PASS"
    print(f"VALID phase1-review model={MIMO_MODEL} preflight={preflight} review={review}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute-once", action="store_true")
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    parser.add_argument("--acknowledgement", default="")
    args = parser.parse_args()
    if args.check == args.execute_once:
        parser.error("choose exactly one of --check or --execute-once")
    if args.check:
        check()
        return 0
    fixture_path = args.fixture.resolve()
    if fixture_path != FIXTURE_PATH.resolve():
        raise RuntimeError("ONLY_FROZEN_PHASE1_FIXTURE_ALLOWED")
    execute(args.acknowledgement, fixture_path)
    print(f"PASS phase1-review output={OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
