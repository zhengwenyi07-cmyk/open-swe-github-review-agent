#!/usr/bin/env python3
"""Fetch one approved GitHub PR read-only and produce one local MiMo review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from open_swe_review_agent.contracts import ReviewContractError, validate_review
from open_swe_review_agent.github_readonly import (
    GitHubReadOnlyClient,
    GitHubReadOnlyError,
    GitHubReadOnlyTransport,
    PullRequestSnapshot,
    SHA_RE,
    canonical_json,
    diff_file_blocks,
    read_pull_request_snapshot,
    safe_metadata_evidence,
)
from open_swe_review_agent.diff_parser import changed_lines
from open_swe_review_agent.mimo import MIMO_MODEL, create_mimo_model
from open_swe_review_agent.open_swe_adapter import OpenSWECompatibleReviewModel
from open_swe_review_agent.render import render_markdown
from open_swe_review_agent.workflow import ReviewRequest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "phase3"
PREFLIGHT = ROOT / "artifacts" / "mimo_preflight.json"
TARGET_CONTRACT = ROOT / "configs" / "phase3_github_readonly_target.json"
ACK = "OPEN_SWE_PHASE3_GITHUB_READ_ONLY_REVIEW"
UPSTREAM_COMMIT = "daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc"
ADAPTER_KIND = "OPEN_SWE_REVIEWER_COMPATIBLE_GITHUB_READ_ONLY_SLICE"
REQUIRED_CONTRACT_FILES = (
    "scripts/run_phase3_github_readonly.py",
    "src/open_swe_review_agent/github_readonly.py",
    "src/open_swe_review_agent/open_swe_adapter.py",
    "src/open_swe_review_agent/contracts.py",
    "src/open_swe_review_agent/diff_parser.py",
    "src/open_swe_review_agent/render.py",
    "src/open_swe_review_agent/workflow.py",
    "schemas/review.schema.json",
    "configs/phase3_github_readonly_target.json",
    "tests/test_phase3_github_readonly.py",
    "docs/phases/phase-03-github-read-only/PLAN.md",
    "docs/phases/phase-03-github-read-only/CONCEPTS.md",
    "docs/phases/phase-03-github-read-only/RESULTS.md",
)


def run(*args: str) -> str:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load_preflight() -> None:
    if not PREFLIGHT.is_file():
        raise RuntimeError("PREFLIGHT_REQUIRED")
    evidence = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    required = {
        "status": "PASS",
        "configured_model": MIMO_MODEL,
        "model": MIMO_MODEL,
        "response_model": MIMO_MODEL,
        "finish_reason": "tool_calls",
        "transport": "OPENAI_CHAT_COMPLETIONS",
        "tool_calls": 1,
    }
    if any(evidence.get(key) != value for key, value in required.items()):
        raise RuntimeError("PREFLIGHT_INVALID")


def load_target_contract() -> dict[str, Any]:
    payload = json.loads(TARGET_CONTRACT.read_text(encoding="utf-8"))
    if set(payload) != {
        "version",
        "approval_status",
        "repository",
        "pull_number",
        "authentication_mode",
        "github_write_allowed",
        "review_publish_allowed",
    }:
        raise RuntimeError("TARGET_CONTRACT_INVALID")
    if (
        payload["version"] != "phase3_github_readonly_target_v1"
        or payload["github_write_allowed"] is not False
        or payload["review_publish_allowed"] is not False
    ):
        raise RuntimeError("TARGET_CONTRACT_INVALID")
    if payload["approval_status"] == "NOT_APPROVED":
        if any(payload[key] is not None for key in ("repository", "pull_number", "authentication_mode")):
            raise RuntimeError("TARGET_CONTRACT_INVALID")
        return payload
    if payload["approval_status"] != "APPROVED":
        raise RuntimeError("TARGET_CONTRACT_INVALID")
    GitHubReadOnlyClient.validate_identity(payload["repository"], payload["pull_number"])
    if payload["authentication_mode"] not in {"PUBLIC", "TOKEN"}:
        raise RuntimeError("TARGET_CONTRACT_INVALID")
    return payload


def ensure_clean_committed_contract() -> str:
    if run("git", "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("WORKTREE_NOT_CLEAN")
    run("git", "ls-files", "--error-unmatch", "--", *REQUIRED_CONTRACT_FILES)
    return run("git", "rev-parse", "HEAD")


def reserve_output_directory() -> None:
    expected = ROOT / "artifacts" / "phase3"
    if OUTPUT_DIR != expected or ROOT.is_symlink():
        raise RuntimeError("OUTPUT_PATH_INVALID")
    artifacts = ROOT / "artifacts"
    if artifacts.is_symlink():
        raise RuntimeError("OUTPUT_PATH_INVALID")
    artifacts.mkdir(exist_ok=True)
    if artifacts.resolve() != (ROOT.resolve() / "artifacts"):
        raise RuntimeError("OUTPUT_PATH_INVALID")
    try:
        OUTPUT_DIR.mkdir()
    except FileExistsError:
        raise RuntimeError("PHASE3_OUTPUT_ALREADY_EXISTS") from None


def snapshot_json(snapshot: PullRequestSnapshot) -> dict[str, Any]:
    payload = snapshot.safe_metadata()
    payload["files"] = snapshot.safe_files()
    payload["candidate_changed_lines"] = len(snapshot.anchors)
    payload["raw_diff_bytes"] = len(snapshot.diff_text.encode("utf-8"))
    return payload


def changed_lines_json(snapshot: PullRequestSnapshot) -> list[dict[str, Any]]:
    return [{"file": path, "line": line} for path, line in snapshot.anchors]


def _write_failure(stage: str, reason: str, repository: str, pull_number: int) -> None:
    if OUTPUT_DIR.exists():
        for name in ("review.json", "review.md", "run_summary.json"):
            path = OUTPUT_DIR / name
            if path.exists():
                path.unlink()
    atomic_json(
        OUTPUT_DIR / "failure.json",
        {
            "status": "FAILED",
            "failure_stage": stage,
            "failure_reason": reason,
            "repository": repository,
            "pull_number": pull_number,
            "github_write_performed": False,
            "review_publish_allowed": False,
            "automatic_retries": 0,
        },
    )


def execute_formal_once(
    acknowledgement: str,
    repository: str,
    pull_number: int,
    auth_mode: str,
) -> None:
    if acknowledgement != ACK:
        raise RuntimeError("ACKNOWLEDGEMENT_REQUIRED")
    if os.environ.get("OPEN_SWE_PHASE3_ALLOW_NETWORK") != "YES_ONCE":
        raise RuntimeError("NETWORK_GATE_REQUIRED")
    if os.environ.get("MIMO_ACCOUNT_TYPE") != "PAY_AS_YOU_GO":
        raise RuntimeError("ACCOUNT_TYPE_MISMATCH")
    if auth_mode not in {"PUBLIC", "TOKEN"}:
        raise RuntimeError("AUTH_MODE_INVALID")
    GitHubReadOnlyClient.validate_identity(repository, pull_number)
    contract_commit = ensure_clean_committed_contract()
    target = load_target_contract()
    if target["approval_status"] != "APPROVED":
        raise RuntimeError("TARGET_PR_NOT_APPROVED")
    if (
        target["repository"] != repository
        or target["pull_number"] != pull_number
        or target["authentication_mode"] != auth_mode
    ):
        raise RuntimeError("TARGET_PR_CONTRACT_MISMATCH")
    load_preflight()
    github_token = None
    if auth_mode == "TOKEN":
        github_token = os.environ.get("GITHUB_TOKEN")
        if not github_token:
            raise RuntimeError("GITHUB_TOKEN_REQUIRED")
    mimo_key = os.environ.get("MIMO_API_KEY", "")
    if not mimo_key or mimo_key.strip() != mimo_key:
        raise RuntimeError("MIMO_API_KEY_REQUIRED")
    reserve_output_directory()

    snapshot: PullRequestSnapshot | None = None
    model: OpenSWECompatibleReviewModel | None = None
    execution_stage = "CLIENT_CONSTRUCTION"
    try:
        transport = GitHubReadOnlyTransport(token=github_token)
        client = GitHubReadOnlyClient(transport=transport)
        execution_stage = "SNAPSHOT_READ"
        snapshot = read_pull_request_snapshot(client, repository, pull_number)
        execution_stage = "SNAPSHOT_WRITE"
        atomic_json(OUTPUT_DIR / "pr_snapshot.json", snapshot_json(snapshot))
        atomic_text(OUTPUT_DIR / "diff.patch", snapshot.diff_text)
        atomic_json(OUTPUT_DIR / "changed_lines.json", changed_lines_json(snapshot))

        execution_stage = "MODEL_CLIENT"
        model = OpenSWECompatibleReviewModel(create_mimo_model(mimo_key))
        request = ReviewRequest(
            repository=repository,
            base_commit=snapshot.base_sha,
            candidate_commit=snapshot.head_sha,
            test_commands=(),
            pull_number=pull_number,
            pull_title=snapshot.title,
            pull_body=snapshot.body,
        )
        started = time.monotonic()
        execution_stage = "MODEL_RESPONSE"
        candidate = model.review(request=request, diff_text=snapshot.diff_text)
        elapsed = time.monotonic() - started
        review = dict(candidate)
        review["commit_sha"] = snapshot.head_sha
        review["tests"] = {
            "status": "NOT_RUN_READ_ONLY",
            "commands": [],
            "passed": False,
        }
        execution_stage = "REVIEW_VALIDATION"
        validate_review(review, snapshot.diff_text)
        summary = {
            "status": "PASS",
            "adapter_kind": ADAPTER_KIND,
            "contract_commit": contract_commit,
            "upstream_commit": UPSTREAM_COMMIT,
            "repository": repository,
            "pull_number": pull_number,
            "base_sha": snapshot.base_sha,
            "head_sha": snapshot.head_sha,
            "authentication_mode": auth_mode,
            "model": MIMO_MODEL,
            "response_model": model.response_model,
            "finish_reason": model.finish_reason,
            "model_calls": model.calls,
            **model.usage,
            "elapsed_seconds": round(elapsed, 3),
            "github_get_requests": transport.stats.request_count,
            "github_response_bytes": transport.stats.response_bytes,
            "github_rate_limit_remaining": transport.stats.rate_limit_remaining,
            "github_write_requests": 0,
            "github_write_performed": False,
            "review_publish_allowed": False,
            "pr_code_executed": False,
            "tests_status": "NOT_RUN_READ_ONLY",
            "schema_valid": True,
            "automatic_retries": 0,
            "next_step": "HUMAN_REVIEW_REQUIRED",
        }
        execution_stage = "EVIDENCE_WRITE"
        atomic_json(OUTPUT_DIR / "review.json", review)
        atomic_text(OUTPUT_DIR / "review.md", render_markdown(review))
        atomic_json(OUTPUT_DIR / "run_summary.json", summary)
    except GitHubReadOnlyError as error:
        _write_failure(error.stage, error.reason, repository, pull_number)
        raise RuntimeError(f"{error.stage}:{error.reason}") from None
    except ReviewContractError:
        _write_failure("REVIEW_VALIDATION", "REVIEW_CONTRACT_FAILURE", repository, pull_number)
        raise RuntimeError("REVIEW_VALIDATION:REVIEW_CONTRACT_FAILURE") from None
    except BaseException:
        _write_failure(execution_stage, "SAFE_EXECUTION_FAILURE", repository, pull_number)
        raise RuntimeError(f"{execution_stage}:SAFE_EXECUTION_FAILURE") from None


def check() -> None:
    target = load_target_contract()
    target_status = target["approval_status"]
    if not OUTPUT_DIR.exists():
        print(
            "VALID phase3-github-readonly implementation=OFFLINE_CONTRACT "
            f"target={target_status} execution=NOT_STARTED github_read=false github_write=false"
        )
        return
    failure_path = OUTPUT_DIR / "failure.json"
    if target_status != "APPROVED":
        raise RuntimeError("TARGET_PR_NOT_APPROVED")
    if failure_path.exists():
        if any((OUTPUT_DIR / name).exists() for name in ("review.json", "review.md", "run_summary.json")):
            raise RuntimeError("SUCCESS_AND_FAILURE_EVIDENCE_CONFLICT")
        failure = json.loads(failure_path.read_text(encoding="utf-8"))
        if set(failure) != {
            "status",
            "failure_stage",
            "failure_reason",
            "repository",
            "pull_number",
            "github_write_performed",
            "review_publish_allowed",
            "automatic_retries",
        }:
            raise RuntimeError("FAILURE_EVIDENCE_INVALID")
        if (
            failure.get("status") != "FAILED"
            or failure.get("github_write_performed") is not False
            or failure.get("review_publish_allowed") is not False
            or failure.get("automatic_retries") != 0
        ):
            raise RuntimeError("FAILURE_EVIDENCE_INVALID")
        GitHubReadOnlyClient.validate_identity(failure["repository"], failure["pull_number"])
        if failure["repository"] != target["repository"] or failure["pull_number"] != target["pull_number"]:
            raise RuntimeError("TARGET_PR_CONTRACT_MISMATCH")
        print("VALID phase3-github-readonly execution=FAILED github_write=false")
        return
    required = {"pr_snapshot.json", "diff.patch", "changed_lines.json", "review.json", "review.md", "run_summary.json"}
    actual = {path.name for path in OUTPUT_DIR.iterdir() if path.is_file()}
    if actual != required:
        raise RuntimeError("PHASE3_EVIDENCE_SET_INVALID")
    snapshot = json.loads((OUTPUT_DIR / "pr_snapshot.json").read_text(encoding="utf-8"))
    diff_text = (OUTPUT_DIR / "diff.patch").read_text(encoding="utf-8")
    lines = json.loads((OUTPUT_DIR / "changed_lines.json").read_text(encoding="utf-8"))
    expected_snapshot_keys = {
        "repository",
        "pull_number",
        "base_sha",
        "head_sha",
        "state",
        "title",
        "body",
        "changed_files",
        "metadata_sha256",
        "files_sha256",
        "diff_sha256",
        "changed_lines_sha256",
        "files",
        "candidate_changed_lines",
        "raw_diff_bytes",
    }
    if set(snapshot) != expected_snapshot_keys:
        raise RuntimeError("SNAPSHOT_EVIDENCE_INVALID")
    GitHubReadOnlyClient.validate_identity(snapshot["repository"], snapshot["pull_number"])
    if not SHA_RE.fullmatch(snapshot["base_sha"]) or not SHA_RE.fullmatch(snapshot["head_sha"]):
        raise RuntimeError("SNAPSHOT_EVIDENCE_INVALID")
    if any(not isinstance(snapshot[key], str) or len(snapshot[key]) != 64 for key in (
        "metadata_sha256", "files_sha256", "diff_sha256", "changed_lines_sha256"
    )):
        raise RuntimeError("SNAPSHOT_EVIDENCE_INVALID")
    if snapshot["raw_diff_bytes"] != len(diff_text.encode("utf-8")):
        raise RuntimeError("SNAPSHOT_EVIDENCE_INVALID")
    if sha256_bytes(diff_text.encode("utf-8")) != snapshot["diff_sha256"]:
        raise RuntimeError("DIFF_HASH_MISMATCH")
    expected_lines_hash = sha256_bytes(
        json.dumps(lines, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    if expected_lines_hash != snapshot["changed_lines_sha256"]:
        raise RuntimeError("CHANGED_LINES_HASH_MISMATCH")
    actual_anchors = [{"file": path, "line": line} for path, line in sorted(changed_lines(diff_text))]
    if lines != actual_anchors or snapshot["candidate_changed_lines"] != len(actual_anchors):
        raise RuntimeError("CHANGED_LINES_EVIDENCE_INVALID")
    file_entries = snapshot["files"]
    if not isinstance(file_entries, list) or snapshot["changed_files"] != len(file_entries):
        raise RuntimeError("SNAPSHOT_EVIDENCE_INVALID")
    if {item.get("filename") for item in file_entries if isinstance(item, dict)} != set(diff_file_blocks(diff_text)):
        raise RuntimeError("SNAPSHOT_FILE_SET_MISMATCH")
    metadata_identity = (
        snapshot["repository"],
        snapshot["pull_number"],
        snapshot["base_sha"],
        snapshot["head_sha"],
        snapshot["state"],
        snapshot["title"],
        snapshot["body"],
        snapshot["changed_files"],
    )
    if sha256_bytes(canonical_json(safe_metadata_evidence(metadata_identity))) != snapshot["metadata_sha256"]:
        raise RuntimeError("METADATA_HASH_MISMATCH")
    if sha256_bytes(canonical_json(file_entries)) != snapshot["files_sha256"]:
        raise RuntimeError("FILES_HASH_MISMATCH")
    review = json.loads((OUTPUT_DIR / "review.json").read_text(encoding="utf-8"))
    validate_review(review, diff_text)
    if review.get("commit_sha") != snapshot["head_sha"]:
        raise RuntimeError("REVIEW_HEAD_MISMATCH")
    if review["tests"] != {"status": "NOT_RUN_READ_ONLY", "commands": [], "passed": False}:
        raise RuntimeError("READ_ONLY_TEST_STATUS_INVALID")
    if (OUTPUT_DIR / "review.md").read_text(encoding="utf-8") != render_markdown(review):
        raise RuntimeError("REVIEW_MARKDOWN_MISMATCH")
    summary = json.loads((OUTPUT_DIR / "run_summary.json").read_text(encoding="utf-8"))
    required_summary = {
        "status": "PASS",
        "github_write_requests": 0,
        "github_write_performed": False,
        "review_publish_allowed": False,
        "pr_code_executed": False,
        "tests_status": "NOT_RUN_READ_ONLY",
        "model": MIMO_MODEL,
        "response_model": MIMO_MODEL,
        "finish_reason": "tool_calls",
        "next_step": "HUMAN_REVIEW_REQUIRED",
    }
    if any(summary.get(key) != value for key, value in required_summary.items()):
        raise RuntimeError("RUN_SUMMARY_INVALID")
    if summary.get("base_sha") != snapshot["base_sha"] or summary.get("head_sha") != snapshot["head_sha"]:
        raise RuntimeError("RUN_SUMMARY_SNAPSHOT_MISMATCH")
    if (
        summary.get("repository") != snapshot["repository"]
        or summary.get("pull_number") != snapshot["pull_number"]
        or summary.get("github_get_requests") != 4
    ):
        raise RuntimeError("RUN_SUMMARY_SNAPSHOT_MISMATCH")
    if (
        snapshot["repository"] != target["repository"]
        or snapshot["pull_number"] != target["pull_number"]
        or summary.get("authentication_mode") != target["authentication_mode"]
    ):
        raise RuntimeError("TARGET_PR_CONTRACT_MISMATCH")
    print("VALID phase3-github-readonly execution=PASS github_write=false next=HUMAN_REVIEW_REQUIRED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute-once", action="store_true")
    parser.add_argument("--repository", default="")
    parser.add_argument("--pull-number", type=int, default=0)
    parser.add_argument("--auth-mode", choices=("PUBLIC", "TOKEN"), default="PUBLIC")
    parser.add_argument("--acknowledgement", default="")
    args = parser.parse_args()
    if args.check == args.execute_once:
        parser.error("choose exactly one of --check or --execute-once")
    if args.check:
        check()
        return 0
    execute_formal_once(args.acknowledgement, args.repository, args.pull_number, args.auth_mode)
    print(f"PASS phase3-github-readonly output={OUTPUT_DIR} next=HUMAN_REVIEW_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
