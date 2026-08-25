#!/usr/bin/env python3
"""Prepare, human-approve, and publish one controlled Phase 4 GitHub Review."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from open_swe_review_agent.contracts import ReviewContractError, validate_review
from open_swe_review_agent.diff_parser import changed_lines
from open_swe_review_agent.github_app_auth import GitHubAppAuthError, GitHubAppTokenProvider
from open_swe_review_agent.github_readonly import (
    GitHubReadOnlyClient,
    GitHubReadOnlyError,
    GitHubReadOnlyTransport,
    PullRequestSnapshot,
    ReadLimits,
    SHA_RE,
    canonical_json,
    diff_file_blocks,
    read_pull_request_snapshot,
    safe_metadata_evidence,
)
from open_swe_review_agent.github_review_publisher import (
    GitHubPublishError,
    GitHubReviewTransport,
    build_publish_payload,
    find_marker_reviews,
    marker_id,
    validate_publish_payload,
    validate_remote_review,
)
from open_swe_review_agent.mimo import MIMO_MODEL, create_mimo_model
from open_swe_review_agent.open_swe_adapter import OpenSWECompatibleReviewModel
from open_swe_review_agent.render import render_markdown
from open_swe_review_agent.workflow import ReviewRequest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "phase4"
LOCK_PATH = ROOT / "artifacts" / ".phase4_publish.lock"
PREFLIGHT = ROOT / "artifacts" / "mimo_preflight.json"
TARGET_CONTRACT = ROOT / "configs" / "phase4_target.json"
PUBLISH_APPROVAL = ROOT / "configs" / "phase4_publish_approval.json"
PREPARE_ACK = "OPEN_SWE_PHASE4_CONTROLLED_REVIEW_PREPARE"
PUBLISH_ACK = "OPEN_SWE_PHASE4_CONTROLLED_REVIEW_PUBLISH"
UPSTREAM_COMMIT = "daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc"
ADAPTER_KIND = "OPEN_SWE_REVIEWER_COMPATIBLE_CONTROLLED_PUBLISH_SLICE"
PAYLOAD_RELATIVE_PATH = "artifacts/phase4/publish_payload.json"
CONTROLLED_REPOSITORY = "zhengwenyi07-cmyk/open-swe-github-review-agent"
REQUIRED_CONTRACT_FILES = (
    "scripts/run_phase4_controlled_publish.py",
    "src/open_swe_review_agent/github_app_auth.py",
    "src/open_swe_review_agent/github_review_publisher.py",
    "src/open_swe_review_agent/github_readonly.py",
    "src/open_swe_review_agent/open_swe_adapter.py",
    "src/open_swe_review_agent/contracts.py",
    "src/open_swe_review_agent/diff_parser.py",
    "src/open_swe_review_agent/render.py",
    "src/open_swe_review_agent/workflow.py",
    "schemas/review.schema.json",
    "configs/phase4_target.json",
    "configs/phase4_publish_approval.json",
    "tests/test_phase4_controlled_publish.py",
    "docs/phases/phase-04-controlled-review-publish/PLAN.md",
    "docs/phases/phase-04-controlled-review-publish/CONCEPTS.md",
    "docs/phases/phase-04-controlled-review-publish/RESULTS.md",
)
IMMUTABLE_AFTER_PREPARE_FILES = tuple(
    path
    for path in REQUIRED_CONTRACT_FILES
    if path
    not in {
        "configs/phase4_publish_approval.json",
        "docs/phases/phase-04-controlled-review-publish/RESULTS.md",
    }
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


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load_json(path: Path, reason: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError(reason) from None


def load_preflight() -> None:
    evidence = load_json(PREFLIGHT, "PREFLIGHT_REQUIRED") if PREFLIGHT.is_file() else None
    required = {
        "status": "PASS",
        "configured_model": MIMO_MODEL,
        "model": MIMO_MODEL,
        "response_model": MIMO_MODEL,
        "finish_reason": "tool_calls",
        "transport": "OPENAI_CHAT_COMPLETIONS",
        "tool_calls": 1,
    }
    if not isinstance(evidence, dict) or any(evidence.get(key) != value for key, value in required.items()):
        raise RuntimeError("PREFLIGHT_INVALID")


def load_target_contract() -> dict[str, Any]:
    payload = load_json(TARGET_CONTRACT, "TARGET_CONTRACT_INVALID")
    expected = {
        "version",
        "approval_status",
        "repository",
        "pull_number",
        "authentication_mode",
        "base_sha",
        "head_sha",
        "prepare_github_write_allowed",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise RuntimeError("TARGET_CONTRACT_INVALID")
    if payload["version"] != "phase4_target_v1" or payload["prepare_github_write_allowed"] is not False:
        raise RuntimeError("TARGET_CONTRACT_INVALID")
    identity_fields = ("repository", "pull_number", "authentication_mode", "base_sha", "head_sha")
    if payload["approval_status"] == "NOT_APPROVED":
        if any(payload[key] is not None for key in identity_fields):
            raise RuntimeError("TARGET_CONTRACT_INVALID")
        return payload
    if payload["approval_status"] != "APPROVED":
        raise RuntimeError("TARGET_CONTRACT_INVALID")
    GitHubReadOnlyClient.validate_identity(payload["repository"], payload["pull_number"])
    if payload["repository"] != CONTROLLED_REPOSITORY:
        raise RuntimeError("TARGET_REPOSITORY_NOT_CONTROLLED")
    if payload["authentication_mode"] != "GITHUB_APP":
        raise RuntimeError("TARGET_CONTRACT_INVALID")
    if not SHA_RE.fullmatch(str(payload["base_sha"])) or not SHA_RE.fullmatch(str(payload["head_sha"])):
        raise RuntimeError("TARGET_CONTRACT_INVALID")
    return payload


def load_publish_approval() -> dict[str, Any]:
    payload = load_json(PUBLISH_APPROVAL, "PUBLISH_APPROVAL_INVALID")
    expected = {
        "version",
        "approval_status",
        "repository",
        "pull_number",
        "base_sha",
        "head_sha",
        "payload_path",
        "payload_sha256",
        "event",
        "max_write_requests",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise RuntimeError("PUBLISH_APPROVAL_INVALID")
    if (
        payload["version"] != "phase4_publish_approval_v1"
        or payload["payload_path"] != PAYLOAD_RELATIVE_PATH
        or payload["event"] != "COMMENT"
        or payload["max_write_requests"] != 1
    ):
        raise RuntimeError("PUBLISH_APPROVAL_INVALID")
    identity_fields = ("repository", "pull_number", "base_sha", "head_sha", "payload_sha256")
    if payload["approval_status"] == "NOT_APPROVED":
        if any(payload[key] is not None for key in identity_fields):
            raise RuntimeError("PUBLISH_APPROVAL_INVALID")
        return payload
    if payload["approval_status"] != "APPROVED":
        raise RuntimeError("PUBLISH_APPROVAL_INVALID")
    GitHubReadOnlyClient.validate_identity(payload["repository"], payload["pull_number"])
    if (
        not SHA_RE.fullmatch(str(payload["base_sha"]))
        or not SHA_RE.fullmatch(str(payload["head_sha"]))
        or not re.fullmatch(r"[0-9a-f]{64}", str(payload["payload_sha256"]))
    ):
        raise RuntimeError("PUBLISH_APPROVAL_INVALID")
    return payload


def ensure_clean_committed_contract() -> str:
    if run("git", "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("WORKTREE_NOT_CLEAN")
    run("git", "ls-files", "--error-unmatch", "--", *REQUIRED_CONTRACT_FILES)
    return run("git", "rev-parse", "HEAD")


def verify_prepare_contract_identity(prepare_commit: str) -> None:
    if not SHA_RE.fullmatch(prepare_commit):
        raise RuntimeError("PREPARE_CONTRACT_COMMIT_INVALID")
    try:
        run("git", "merge-base", "--is-ancestor", prepare_commit, "HEAD")
        for relative in IMMUTABLE_AFTER_PREPARE_FILES:
            historical = subprocess.run(
                ["git", "show", f"{prepare_commit}:{relative}"],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).stdout
            if historical != (ROOT / relative).read_bytes():
                raise RuntimeError("PREPARE_CONTRACT_IDENTITY_MISMATCH")
    except RuntimeError:
        raise
    except BaseException:
        raise RuntimeError("PREPARE_CONTRACT_IDENTITY_MISMATCH") from None


def _env_positive_int(name: str) -> int:
    value = os.environ.get(name, "")
    if not value.isdigit() or int(value) < 1:
        raise RuntimeError(f"{name}_INVALID")
    return int(value)


def create_token_provider(repository: str, pull_requests_permission: str) -> GitHubAppTokenProvider:
    if pull_requests_permission not in {"read", "write"}:
        raise RuntimeError("GITHUB_APP_PERMISSION_INVALID")
    key_text = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "")
    if not key_text:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY_PATH_REQUIRED")
    key_path = Path(key_text)
    try:
        if ROOT.resolve() == key_path.resolve() or ROOT.resolve() in key_path.resolve().parents:
            raise RuntimeError("GITHUB_APP_PRIVATE_KEY_MUST_BE_OUTSIDE_REPOSITORY")
    except OSError:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY_PATH_INVALID") from None
    return GitHubAppTokenProvider(
        app_id=_env_positive_int("GITHUB_APP_ID"),
        installation_id=_env_positive_int("GITHUB_APP_INSTALLATION_ID"),
        private_key_path=key_path,
        repository=repository,
        pull_requests_permission=pull_requests_permission,
    )


def reserve_output_directory() -> None:
    if OUTPUT_DIR != ROOT / "artifacts" / "phase4" or ROOT.is_symlink():
        raise RuntimeError("OUTPUT_PATH_INVALID")
    artifacts = ROOT / "artifacts"
    if artifacts.is_symlink():
        raise RuntimeError("OUTPUT_PATH_INVALID")
    artifacts.mkdir(exist_ok=True)
    if artifacts.resolve() != ROOT.resolve() / "artifacts":
        raise RuntimeError("OUTPUT_PATH_INVALID")
    try:
        OUTPUT_DIR.mkdir()
    except FileExistsError:
        raise RuntimeError("PHASE4_OUTPUT_ALREADY_EXISTS") from None


@contextmanager
def publish_lock() -> Iterator[None]:
    LOCK_PATH.parent.mkdir(exist_ok=True)
    with LOCK_PATH.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("PUBLISH_LOCK_BUSY") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _metadata_matches_target(metadata: dict[str, Any], target: dict[str, Any]) -> None:
    try:
        actual = {
            "repository": metadata["base"]["repo"]["full_name"],
            "pull_number": metadata["number"],
            "base_sha": metadata["base"]["sha"],
            "head_sha": metadata["head"]["sha"],
            "state": metadata["state"],
            "draft": metadata["draft"],
        }
    except (KeyError, TypeError):
        raise GitHubReadOnlyError("TARGET_RECHECK", "LIVE_PR_IDENTITY_INVALID") from None
    expected = {key: target[key] for key in ("repository", "pull_number", "base_sha", "head_sha")}
    if any(actual[key] != value for key, value in expected.items()) or actual["state"] != "open" or actual["draft"] is not False:
        raise GitHubReadOnlyError("TARGET_RECHECK", "LIVE_PR_IDENTITY_MISMATCH")


def snapshot_json(snapshot: PullRequestSnapshot) -> dict[str, Any]:
    payload = snapshot.safe_metadata()
    payload["files"] = snapshot.safe_files()
    payload["candidate_changed_lines"] = len(snapshot.anchors)
    payload["raw_diff_bytes"] = len(snapshot.diff_text.encode("utf-8"))
    return payload


def changed_lines_json(snapshot: PullRequestSnapshot) -> list[dict[str, Any]]:
    return [{"file": path, "line": line} for path, line in snapshot.anchors]


def _write_failure(
    stage: str,
    reason: str,
    *,
    write_requests: int = 0,
    ambiguous: bool = False,
    preserve_prepared: bool = True,
) -> None:
    if not OUTPUT_DIR.exists():
        return
    receipt_path = OUTPUT_DIR / "publish_receipt.json"
    receipt: dict[str, Any] | None = None
    if receipt_path.is_file():
        candidate = load_json(receipt_path, "PUBLISH_RECEIPT_INVALID")
        if isinstance(candidate, dict):
            receipt = candidate
    summary_path = OUTPUT_DIR / "run_summary.json"
    if summary_path.exists():
        summary_path.unlink()
    if not preserve_prepared:
        for name in (
            "pr_snapshot.json",
            "diff.patch",
            "changed_lines.json",
            "review.json",
            "review.md",
            "prepare_summary.json",
            "publish_payload.json",
        ):
            path = OUTPUT_DIR / name
            if path.exists():
                path.unlink()
    atomic_json(
        OUTPUT_DIR / "failure.json",
        {
            "status": "FAILED",
            "failure_stage": stage,
            "failure_reason": reason,
            "github_review_write_requests": write_requests,
            "ambiguous_write_state": ambiguous,
            "automatic_post_retries": 0,
            "remote_side_effect_confirmed": receipt is not None,
            "remote_review_id": receipt.get("review_id") if receipt else None,
            "remote_review_html_url": receipt.get("html_url") if receipt else None,
        },
    )


def prepare_once(acknowledgement: str, repository: str, pull_number: int) -> str:
    if acknowledgement != PREPARE_ACK:
        raise RuntimeError("ACKNOWLEDGEMENT_REQUIRED")
    if os.environ.get("OPEN_SWE_PHASE4_PREPARE_ALLOW_NETWORK") != "YES_ONCE":
        raise RuntimeError("NETWORK_GATE_REQUIRED")
    if os.environ.get("MIMO_ACCOUNT_TYPE") != "PAY_AS_YOU_GO":
        raise RuntimeError("ACCOUNT_TYPE_MISMATCH")
    GitHubReadOnlyClient.validate_identity(repository, pull_number)
    contract_commit = ensure_clean_committed_contract()
    target = load_target_contract()
    if target["approval_status"] != "APPROVED":
        raise RuntimeError("TARGET_PR_NOT_APPROVED")
    if target["repository"] != repository or target["pull_number"] != pull_number:
        raise RuntimeError("TARGET_PR_CONTRACT_MISMATCH")
    if load_publish_approval()["approval_status"] != "NOT_APPROVED":
        raise RuntimeError("PUBLISH_PREAPPROVED_BEFORE_PAYLOAD")
    load_preflight()
    mimo_key = os.environ.get("MIMO_API_KEY", "")
    if not mimo_key or mimo_key.strip() != mimo_key:
        raise RuntimeError("MIMO_API_KEY_REQUIRED")
    reserve_output_directory()

    stage = "APP_AUTH"
    try:
        provider = create_token_provider(repository, "read")
        token = provider.mint()
        transport = GitHubReadOnlyTransport(token=token.value)
        limits = ReadLimits(
            max_changed_files=3,
            max_raw_diff_bytes=16 * 1024,
            max_total_diff_lines=300,
            max_candidate_changed_lines=80,
        )
        client = GitHubReadOnlyClient(transport=transport, limits=limits)
        stage = "TARGET_RECHECK"
        _metadata_matches_target(client.metadata(repository, pull_number), target)
        stage = "SNAPSHOT_READ"
        snapshot = read_pull_request_snapshot(client, repository, pull_number)
        if snapshot.base_sha != target["base_sha"] or snapshot.head_sha != target["head_sha"]:
            raise RuntimeError("TARGET_PR_CONTRACT_MISMATCH")

        stage = "MODEL_RESPONSE"
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
        candidate = model.review(request=request, diff_text=snapshot.diff_text)
        elapsed = time.monotonic() - started
        review = dict(candidate)
        review["commit_sha"] = snapshot.head_sha
        review["tests"] = {"status": "NOT_RUN_READ_ONLY", "commands": [], "passed": False}
        stage = "REVIEW_VALIDATION"
        validate_review(review, snapshot.diff_text)

        stage = "EVIDENCE_WRITE"
        atomic_json(OUTPUT_DIR / "pr_snapshot.json", snapshot_json(snapshot))
        atomic_text(OUTPUT_DIR / "diff.patch", snapshot.diff_text)
        atomic_json(OUTPUT_DIR / "changed_lines.json", changed_lines_json(snapshot))
        atomic_json(OUTPUT_DIR / "review.json", review)
        atomic_text(OUTPUT_DIR / "review.md", render_markdown(review))
        review_file_hash = file_sha256(OUTPUT_DIR / "review.json")
        common_summary = {
            "adapter_kind": ADAPTER_KIND,
            "contract_commit": contract_commit,
            "upstream_commit": UPSTREAM_COMMIT,
            "repository": repository,
            "pull_number": pull_number,
            "base_sha": snapshot.base_sha,
            "head_sha": snapshot.head_sha,
            "authentication_mode": "GITHUB_APP",
            "model": MIMO_MODEL,
            "response_model": model.response_model,
            "finish_reason": model.finish_reason,
            "model_calls": model.calls,
            **model.usage,
            "elapsed_seconds": round(elapsed, 3),
                "github_auth_token_requests": provider.request_count,
                "github_token_pull_requests_permission": "read",
            "github_get_requests": transport.stats.request_count,
            "github_response_bytes": provider.response_bytes + transport.stats.response_bytes,
            "github_review_write_requests": 0,
            "github_write_performed": False,
            "review_file_sha256": review_file_hash,
            "pr_code_executed": False,
            "tests_status": "NOT_RUN_READ_ONLY",
            "automatic_retries": 0,
        }
        confirmed_count = sum(item["assessment"] == "confirmed" for item in review["findings"])
        if confirmed_count == 0:
            atomic_json(
                OUTPUT_DIR / "prepare_summary.json",
                {
                    **common_summary,
                    "status": "PREPARED_NOT_PUBLISHED",
                    "publish_payload_sha256": None,
                    "idempotency_marker": None,
                    "publishable_findings": 0,
                    "next_step": "HUMAN_REVIEW_REQUIRED",
                },
            )
            return "PREPARED_NOT_PUBLISHED"
        payload, marker = build_publish_payload(
            review,
            snapshot,
            evidence_commit=contract_commit,
            review_file_sha256=review_file_hash,
        )
        atomic_text(OUTPUT_DIR / "publish_payload.json", canonical_json(payload).decode("utf-8"))
        payload_hash = file_sha256(OUTPUT_DIR / "publish_payload.json")
        atomic_json(
            OUTPUT_DIR / "prepare_summary.json",
            {
                "status": "PREPARED_AWAITING_HUMAN_APPROVAL",
                **common_summary,
                "publish_payload_sha256": payload_hash,
                "idempotency_marker": marker,
                "publishable_findings": len(payload["comments"]),
                "next_step": "HUMAN_PAYLOAD_REVIEW_REQUIRED",
            },
        )
        return "PREPARED_AWAITING_HUMAN_APPROVAL"
    except GitHubAppAuthError as error:
        _write_failure("APP_AUTH", error.reason, preserve_prepared=False)
        raise RuntimeError(str(error)) from None
    except GitHubReadOnlyError as error:
        _write_failure(error.stage, error.reason, preserve_prepared=False)
        raise RuntimeError(str(error)) from None
    except (GitHubPublishError, ReviewContractError) as error:
        reason = getattr(error, "reason", "REVIEW_CONTRACT_FAILURE")
        _write_failure(stage, str(reason), preserve_prepared=False)
        raise RuntimeError(f"{stage}:{reason}") from None
    except BaseException:
        _write_failure(stage, "SAFE_EXECUTION_FAILURE", preserve_prepared=False)
        raise RuntimeError(f"{stage}:SAFE_EXECUTION_FAILURE") from None


def _snapshot_from_prepared() -> tuple[PullRequestSnapshot, dict[str, Any], dict[str, Any] | None, str | None]:
    required = {
        "pr_snapshot.json",
        "diff.patch",
        "changed_lines.json",
        "review.json",
        "review.md",
        "prepare_summary.json",
    }
    actual = {path.name for path in OUTPUT_DIR.iterdir() if path.is_file()}
    terminal = {"publish_payload.json", "publish_receipt.json", "run_summary.json", "failure.json"}
    if not required.issubset(actual) or actual - required - terminal:
        raise RuntimeError("PREPARED_EVIDENCE_SET_INVALID")
    snapshot_data = load_json(OUTPUT_DIR / "pr_snapshot.json", "SNAPSHOT_EVIDENCE_INVALID")
    diff_text = (OUTPUT_DIR / "diff.patch").read_text(encoding="utf-8")
    lines = load_json(OUTPUT_DIR / "changed_lines.json", "CHANGED_LINES_EVIDENCE_INVALID")
    review = load_json(OUTPUT_DIR / "review.json", "REVIEW_EVIDENCE_INVALID")
    payload_path = OUTPUT_DIR / "publish_payload.json"
    payload = load_json(payload_path, "PAYLOAD_EVIDENCE_INVALID") if payload_path.exists() else None
    summary = load_json(OUTPUT_DIR / "prepare_summary.json", "PREPARE_SUMMARY_INVALID")
    anchors = tuple(sorted(changed_lines(diff_text)))
    if lines != [{"file": path, "line": line} for path, line in anchors]:
        raise RuntimeError("CHANGED_LINES_EVIDENCE_INVALID")
    if snapshot_data.get("diff_sha256") != sha256_bytes(diff_text.encode("utf-8")):
        raise RuntimeError("DIFF_HASH_MISMATCH")
    if snapshot_data.get("raw_diff_bytes") != len(diff_text.encode("utf-8")):
        raise RuntimeError("SNAPSHOT_EVIDENCE_INVALID")
    lines_hash = sha256_bytes(canonical_json(lines))
    if snapshot_data.get("changed_lines_sha256") != lines_hash:
        raise RuntimeError("CHANGED_LINES_HASH_MISMATCH")
    if snapshot_data.get("candidate_changed_lines") != len(anchors):
        raise RuntimeError("CHANGED_LINES_EVIDENCE_INVALID")
    files = snapshot_data.get("files")
    if not isinstance(files, list) or snapshot_data.get("changed_files") != len(files):
        raise RuntimeError("SNAPSHOT_EVIDENCE_INVALID")
    if {item.get("filename") for item in files if isinstance(item, dict)} != set(diff_file_blocks(diff_text)):
        raise RuntimeError("SNAPSHOT_FILE_SET_MISMATCH")
    if snapshot_data.get("files_sha256") != sha256_bytes(canonical_json(files)):
        raise RuntimeError("FILES_HASH_MISMATCH")
    metadata_identity = (
        snapshot_data["repository"],
        snapshot_data["pull_number"],
        snapshot_data["base_sha"],
        snapshot_data["head_sha"],
        snapshot_data["state"],
        snapshot_data["title"],
        snapshot_data["body"],
        snapshot_data["changed_files"],
    )
    if snapshot_data.get("metadata_sha256") != sha256_bytes(canonical_json(safe_metadata_evidence(metadata_identity))):
        raise RuntimeError("METADATA_HASH_MISMATCH")
    if snapshot_data.get("head_sha") != review.get("commit_sha"):
        raise RuntimeError("REVIEW_HEAD_MISMATCH")
    validate_review(review, diff_text)
    if (OUTPUT_DIR / "review.md").read_text(encoding="utf-8") != render_markdown(review):
        raise RuntimeError("REVIEW_MARKDOWN_MISMATCH")
    snapshot = PullRequestSnapshot(
        repository=snapshot_data["repository"],
        pull_number=snapshot_data["pull_number"],
        base_sha=snapshot_data["base_sha"],
        head_sha=snapshot_data["head_sha"],
        title=snapshot_data["title"],
        body=snapshot_data["body"],
        state=snapshot_data["state"],
        files=(),
        diff_text=diff_text,
        anchors=anchors,
        metadata_sha256=snapshot_data["metadata_sha256"],
        files_sha256=snapshot_data["files_sha256"],
        diff_sha256=snapshot_data["diff_sha256"],
        changed_lines_sha256=snapshot_data["changed_lines_sha256"],
    )
    review_file_hash = file_sha256(OUTPUT_DIR / "review.json")
    fixed_summary = {
        "authentication_mode": "GITHUB_APP",
        "model": MIMO_MODEL,
        "response_model": MIMO_MODEL,
        "finish_reason": "tool_calls",
        "model_calls": 1,
        "github_token_pull_requests_permission": "read",
        "github_review_write_requests": 0,
        "github_write_performed": False,
        "pr_code_executed": False,
        "tests_status": "NOT_RUN_READ_ONLY",
        "automatic_retries": 0,
    }
    if (
        summary.get("review_file_sha256") != review_file_hash
        or any(summary.get(key) != value for key, value in fixed_summary.items())
        or any(summary.get(key) != getattr(snapshot, key) for key in ("repository", "pull_number", "base_sha", "head_sha"))
        or not SHA_RE.fullmatch(str(summary.get("contract_commit", "")))
    ):
        raise RuntimeError("PREPARE_SUMMARY_INVALID")
    if payload is None:
        if (
            summary.get("status") != "PREPARED_NOT_PUBLISHED"
            or summary.get("publish_payload_sha256") is not None
            or summary.get("idempotency_marker") is not None
            or summary.get("publishable_findings") != 0
            or any(item["assessment"] == "confirmed" for item in review["findings"])
        ):
            raise RuntimeError("PREPARE_SUMMARY_INVALID")
        return snapshot, review, None, None
    expected_marker = marker_id(snapshot.repository, snapshot.pull_number, snapshot.head_sha, review_file_hash)
    expected_payload, rebuilt_marker = build_publish_payload(
        review,
        snapshot,
        evidence_commit=summary["contract_commit"],
        review_file_sha256=review_file_hash,
    )
    if payload != expected_payload or rebuilt_marker != expected_marker:
        raise RuntimeError("PAYLOAD_REVIEW_DERIVATION_MISMATCH")
    validate_publish_payload(payload, snapshot, expected_marker=expected_marker)
    if (
        summary.get("status") != "PREPARED_AWAITING_HUMAN_APPROVAL"
        or summary.get("publish_payload_sha256") != file_sha256(payload_path)
        or summary.get("idempotency_marker") != expected_marker
        or summary.get("publishable_findings") != len(payload["comments"])
    ):
        raise RuntimeError("PREPARE_SUMMARY_INVALID")
    return snapshot, review, payload, expected_marker


def _validate_publish_bindings(
    target: dict[str, Any],
    approval: dict[str, Any],
    snapshot: PullRequestSnapshot,
    payload: dict[str, Any],
    marker: str,
) -> None:
    identity = ("repository", "pull_number", "base_sha", "head_sha")
    if target.get("approval_status") != "APPROVED" or approval.get("approval_status") != "APPROVED":
        raise RuntimeError("PUBLISH_NOT_APPROVED")
    if any(approval.get(key) != target.get(key) for key in identity):
        raise RuntimeError("PUBLISH_TARGET_MISMATCH")
    if any(target.get(key) != getattr(snapshot, key) for key in identity):
        raise RuntimeError("TARGET_PR_CONTRACT_MISMATCH")
    payload_path = OUTPUT_DIR / "publish_payload.json"
    if approval.get("payload_sha256") != file_sha256(payload_path):
        raise RuntimeError("APPROVED_PAYLOAD_HASH_MISMATCH")
    validate_publish_payload(payload, snapshot, expected_marker=marker)


def _validate_publish_receipt(
    receipt: Any,
    summary: Any,
    snapshot: PullRequestSnapshot,
    payload: dict[str, Any],
    marker: str,
    approval: dict[str, Any],
) -> None:
    receipt_fields = {
        "review_id",
        "html_url",
        "state",
        "commit_id",
        "submitted_at",
        "comments_verified",
        "status",
        "repository",
        "pull_number",
        "base_sha",
        "head_sha",
        "payload_sha256",
        "idempotency_marker",
        "reconciled_after_ambiguous_response",
        "remote_review_sha256",
        "remote_comments_sha256",
    }
    if not isinstance(receipt, dict) or set(receipt) != receipt_fields:
        raise RuntimeError("PUBLISH_RECEIPT_INVALID")
    review_id = receipt.get("review_id")
    expected_url = (
        f"https://github.com/{snapshot.repository}/pull/{snapshot.pull_number}"
        f"#pullrequestreview-{review_id}"
    )
    if (
        not isinstance(review_id, int)
        or isinstance(review_id, bool)
        or review_id < 1
        or receipt.get("html_url") != expected_url
        or receipt.get("state") != "COMMENTED"
        or receipt.get("commit_id") != snapshot.head_sha
        or not isinstance(receipt.get("submitted_at"), str)
        or not receipt["submitted_at"]
        or receipt.get("comments_verified") != len(payload["comments"])
        or receipt.get("status") != "PUBLISHED_AND_VERIFIED"
        or receipt.get("repository") != snapshot.repository
        or receipt.get("pull_number") != snapshot.pull_number
        or receipt.get("base_sha") != snapshot.base_sha
        or receipt.get("head_sha") != snapshot.head_sha
        or receipt.get("payload_sha256") != approval.get("payload_sha256")
        or receipt.get("idempotency_marker") != marker
        or not isinstance(receipt.get("reconciled_after_ambiguous_response"), bool)
        or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("remote_review_sha256", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("remote_comments_sha256", "")))
    ):
        raise RuntimeError("PUBLISH_RECEIPT_INVALID")
    if summary is None:
        return
    summary_fields = {
        "status",
        "next_step",
        "repository",
        "pull_number",
        "base_sha",
        "head_sha",
        "github_auth_token_requests",
        "github_token_pull_requests_permission",
        "github_get_requests",
        "github_response_bytes",
        "github_review_write_requests",
        "github_review_write_endpoint",
        "github_review_event",
        "github_write_performed",
        "issue_comment_created",
        "check_run_created",
        "merge_performed",
        "branch_or_contents_modified",
        "pr_code_executed",
        "automatic_post_retries",
        "ambiguous_write_state",
        "review_id",
        "review_html_url",
        "payload_sha256",
        "idempotency_marker",
        "comments_verified",
    }
    if not isinstance(summary, dict) or set(summary) != summary_fields:
        raise RuntimeError("RUN_SUMMARY_INVALID")
    if (
        summary.get("status") != "PASS"
        or summary.get("next_step") != "HUMAN_REVIEW_REQUIRED"
        or any(summary.get(key) != getattr(snapshot, key) for key in ("repository", "pull_number", "base_sha", "head_sha"))
        or summary.get("github_auth_token_requests") != 1
        or summary.get("github_token_pull_requests_permission") != "write"
        or not isinstance(summary.get("github_get_requests"), int)
        or summary["github_get_requests"] < 4
        or not isinstance(summary.get("github_response_bytes"), int)
        or summary["github_response_bytes"] < 0
        or summary.get("github_review_write_requests") != 1
        or summary.get("github_review_write_endpoint") != "CREATE_PULL_REQUEST_REVIEW"
        or summary.get("github_review_event") != "COMMENT"
        or summary.get("github_write_performed") is not True
        or any(summary.get(key) is not False for key in ("issue_comment_created", "check_run_created", "merge_performed", "branch_or_contents_modified", "pr_code_executed", "ambiguous_write_state"))
        or summary.get("automatic_post_retries") != 0
        or summary.get("review_id") != review_id
        or summary.get("review_html_url") != expected_url
        or summary.get("payload_sha256") != approval.get("payload_sha256")
        or summary.get("idempotency_marker") != marker
        or summary.get("comments_verified") != len(payload["comments"])
    ):
        raise RuntimeError("RUN_SUMMARY_INVALID")


def publish_once(acknowledgement: str) -> None:
    if acknowledgement != PUBLISH_ACK:
        raise RuntimeError("ACKNOWLEDGEMENT_REQUIRED")
    if os.environ.get("OPEN_SWE_PHASE4_PUBLISH_ALLOW_WRITE") != "YES_ONCE":
        raise RuntimeError("WRITE_GATE_REQUIRED")
    ensure_clean_committed_contract()
    target = load_target_contract()
    approval = load_publish_approval()
    if target["approval_status"] != "APPROVED" or approval["approval_status"] != "APPROVED":
        raise RuntimeError("PUBLISH_NOT_APPROVED")
    if any(approval[key] != target[key] for key in ("repository", "pull_number", "base_sha", "head_sha")):
        raise RuntimeError("PUBLISH_TARGET_MISMATCH")
    if not OUTPUT_DIR.is_dir():
        raise RuntimeError("PREPARED_EVIDENCE_REQUIRED")

    with publish_lock():
        if any((OUTPUT_DIR / name).exists() for name in ("publish_receipt.json", "run_summary.json", "failure.json")):
            raise RuntimeError("PUBLISH_TERMINAL_EVIDENCE_EXISTS")
        snapshot, _review, payload, marker = _snapshot_from_prepared()
        if payload is None or marker is None:
            raise RuntimeError("NO_PUBLISHABLE_FINDINGS")
        prepare_summary = load_json(OUTPUT_DIR / "prepare_summary.json", "PREPARE_SUMMARY_INVALID")
        verify_prepare_contract_identity(prepare_summary.get("contract_commit", ""))
        _validate_publish_bindings(target, approval, snapshot, payload, marker)

        write_requests = 0
        stage = "APP_AUTH"
        try:
            provider = create_token_provider(snapshot.repository, "write")
            token = provider.mint()
            read_transport = GitHubReadOnlyTransport(token=token.value)
            read_client = GitHubReadOnlyClient(transport=read_transport)
            stage = "TARGET_RECHECK"
            _metadata_matches_target(read_client.metadata(snapshot.repository, snapshot.pull_number), target)

            publisher_transport = GitHubReviewTransport(
                token=token.value,
                repository=snapshot.repository,
                pull_number=snapshot.pull_number,
            )
            existing = publisher_transport.get_json(
                publisher_transport.reviews_path,
                query={"page": 1, "per_page": 100},
            )
            if find_marker_reviews(existing, marker):
                raise GitHubPublishError("DUPLICATE_MARKER")

            stage = "CREATE_REVIEW"
            remote_review: dict[str, Any]
            reconciled = False
            try:
                remote_review = publisher_transport.post_review(payload)
            except GitHubPublishError as error:
                write_requests = publisher_transport.stats.write_requests
                if not error.ambiguous:
                    raise
                stage = "WRITE_RECONCILIATION"
                reviews = publisher_transport.get_json(
                    publisher_transport.reviews_path,
                    query={"page": 1, "per_page": 100},
                )
                matches = find_marker_reviews(reviews, marker)
                if len(matches) != 1:
                    raise GitHubPublishError("AMBIGUOUS_WRITE_STATE", ambiguous=True) from None
                remote_review = matches[0]
                reconciled = True

            write_requests = publisher_transport.stats.write_requests
            if write_requests != 1:
                raise GitHubPublishError("WRITE_COUNT_MISMATCH", ambiguous=write_requests > 0)
            review_id = remote_review.get("id")
            if not isinstance(review_id, int) or isinstance(review_id, bool) or review_id < 1:
                raise GitHubPublishError("REMOTE_REVIEW_MISMATCH", ambiguous=True)
            stage = "REMOTE_VERIFICATION"
            exact_review = publisher_transport.get_json(f"{publisher_transport.reviews_path}/{review_id}")
            comments = publisher_transport.get_json(
                f"{publisher_transport.reviews_path}/{review_id}/comments",
                query={"page": 1, "per_page": 100},
            )
            receipt = validate_remote_review(
                exact_review,
                comments,
                payload,
                expected_repository=snapshot.repository,
                expected_pull_number=snapshot.pull_number,
            )
            receipt.update(
                {
                    "status": "PUBLISHED_AND_VERIFIED",
                    "repository": snapshot.repository,
                    "pull_number": snapshot.pull_number,
                    "base_sha": snapshot.base_sha,
                    "head_sha": snapshot.head_sha,
                    "payload_sha256": approval["payload_sha256"],
                    "idempotency_marker": marker,
                    "reconciled_after_ambiguous_response": reconciled,
                    "remote_review_sha256": sha256_bytes(canonical_json(exact_review)),
                    "remote_comments_sha256": sha256_bytes(canonical_json(comments)),
                }
            )
            atomic_json(OUTPUT_DIR / "publish_receipt.json", receipt)
            atomic_json(
                OUTPUT_DIR / "run_summary.json",
                {
                    "status": "PASS",
                    "next_step": "HUMAN_REVIEW_REQUIRED",
                    "repository": snapshot.repository,
                    "pull_number": snapshot.pull_number,
                    "base_sha": snapshot.base_sha,
                    "head_sha": snapshot.head_sha,
                    "github_auth_token_requests": provider.request_count,
                    "github_token_pull_requests_permission": "write",
                    "github_get_requests": read_transport.stats.request_count + publisher_transport.stats.get_requests,
                    "github_response_bytes": provider.response_bytes + read_transport.stats.response_bytes + publisher_transport.stats.response_bytes,
                    "github_review_write_requests": write_requests,
                    "github_review_write_endpoint": "CREATE_PULL_REQUEST_REVIEW",
                    "github_review_event": "COMMENT",
                    "github_write_performed": True,
                    "issue_comment_created": False,
                    "check_run_created": False,
                    "merge_performed": False,
                    "branch_or_contents_modified": False,
                    "pr_code_executed": False,
                    "automatic_post_retries": 0,
                    "ambiguous_write_state": False,
                    "review_id": receipt["review_id"],
                    "review_html_url": receipt["html_url"],
                    "payload_sha256": approval["payload_sha256"],
                    "idempotency_marker": marker,
                    "comments_verified": receipt["comments_verified"],
                },
            )
        except GitHubAppAuthError as error:
            _write_failure("APP_AUTH", error.reason, write_requests=write_requests)
            raise RuntimeError(str(error)) from None
        except GitHubPublishError as error:
            write_requests = max(write_requests, locals().get("publisher_transport", None).stats.write_requests if "publisher_transport" in locals() else 0)
            _write_failure(stage, error.reason, write_requests=write_requests, ambiguous=error.ambiguous)
            raise RuntimeError(str(error)) from None
        except GitHubReadOnlyError as error:
            _write_failure(error.stage, error.reason, write_requests=write_requests)
            raise RuntimeError(str(error)) from None
        except BaseException:
            _write_failure(stage, "SAFE_EXECUTION_FAILURE", write_requests=write_requests)
            raise RuntimeError(f"{stage}:SAFE_EXECUTION_FAILURE") from None


def check() -> None:
    target = load_target_contract()
    approval = load_publish_approval()
    if not OUTPUT_DIR.exists():
        print(
            "VALID phase4-controlled-publish implementation=OFFLINE_CONTRACT "
            f"target={target['approval_status']} approval={approval['approval_status']} "
            "prepare=NOT_RUN publish=NOT_RUN github_write=false"
        )
        return
    failure_path = OUTPUT_DIR / "failure.json"
    receipt_path = OUTPUT_DIR / "publish_receipt.json"
    summary_path = OUTPUT_DIR / "run_summary.json"
    if failure_path.exists():
        if summary_path.exists():
            raise RuntimeError("SUCCESS_AND_FAILURE_EVIDENCE_CONFLICT")
        failure = load_json(failure_path, "FAILURE_EVIDENCE_INVALID")
        failure_fields = {
            "status",
            "failure_stage",
            "failure_reason",
            "github_review_write_requests",
            "ambiguous_write_state",
            "automatic_post_retries",
            "remote_side_effect_confirmed",
            "remote_review_id",
            "remote_review_html_url",
        }
        if (
            not isinstance(failure, dict)
            or set(failure) != failure_fields
            or failure.get("status") != "FAILED"
            or not isinstance(failure.get("failure_stage"), str)
            or not isinstance(failure.get("failure_reason"), str)
            or failure.get("automatic_post_retries") != 0
            or not isinstance(failure.get("github_review_write_requests"), int)
            or failure["github_review_write_requests"] not in {0, 1}
            or not isinstance(failure.get("ambiguous_write_state"), bool)
            or not isinstance(failure.get("remote_side_effect_confirmed"), bool)
        ):
            raise RuntimeError("FAILURE_EVIDENCE_INVALID")
        if receipt_path.exists():
            if (
                failure["remote_side_effect_confirmed"] is not True
                or failure["github_review_write_requests"] != 1
            ):
                raise RuntimeError("FAILURE_EVIDENCE_INVALID")
            snapshot, _review, prepared_payload, marker = _snapshot_from_prepared()
            if prepared_payload is None or marker is None:
                raise RuntimeError("PUBLISH_EVIDENCE_INVALID")
            _validate_publish_bindings(target, approval, snapshot, prepared_payload, marker)
            receipt = load_json(receipt_path, "PUBLISH_RECEIPT_INVALID")
            _validate_publish_receipt(receipt, None, snapshot, prepared_payload, marker, approval)
            if (
                failure["remote_review_id"] != receipt["review_id"]
                or failure["remote_review_html_url"] != receipt["html_url"]
            ):
                raise RuntimeError("FAILURE_EVIDENCE_INVALID")
            print(
                "VALID phase4-controlled-publish status=PUBLISHED_REMOTE_VERIFIED_LOCAL_SUMMARY_FAILED "
                "write_requests=1 next=HUMAN_REVIEW_REQUIRED"
            )
            return
        if (
            failure["remote_side_effect_confirmed"] is not False
            or failure["remote_review_id"] is not None
            or failure["remote_review_html_url"] is not None
        ):
            raise RuntimeError("FAILURE_EVIDENCE_INVALID")
        print(
            "VALID phase4-controlled-publish status=FAILED "
            f"write_requests={failure['github_review_write_requests']}"
        )
        return
    snapshot, _review, prepared_payload, marker = _snapshot_from_prepared()
    if target["approval_status"] != "APPROVED":
        raise RuntimeError("TARGET_PR_NOT_APPROVED")
    if any(snapshot.safe_metadata()[key] != target[key] for key in ("repository", "pull_number", "base_sha", "head_sha")):
        raise RuntimeError("TARGET_PR_CONTRACT_MISMATCH")
    if not receipt_path.exists() and not summary_path.exists():
        if prepared_payload is None:
            print(
                "VALID phase4-controlled-publish prepare=PASS publish=NOT_APPLICABLE "
                "github_write=false next=HUMAN_REVIEW_REQUIRED"
            )
            return
        if approval["approval_status"] == "APPROVED":
            assert marker is not None
            _validate_publish_bindings(target, approval, snapshot, prepared_payload, marker)
        print(
            "VALID phase4-controlled-publish prepare=PASS publish=NOT_RUN "
            f"approval={approval['approval_status']} github_write=false next=HUMAN_PAYLOAD_REVIEW_REQUIRED"
        )
        return
    if (
        not receipt_path.is_file()
        or not summary_path.is_file()
        or prepared_payload is None
        or marker is None
    ):
        raise RuntimeError("PUBLISH_EVIDENCE_INVALID")
    _validate_publish_bindings(target, approval, snapshot, prepared_payload, marker)
    receipt = load_json(receipt_path, "PUBLISH_RECEIPT_INVALID")
    summary = load_json(summary_path, "RUN_SUMMARY_INVALID")
    _validate_publish_receipt(receipt, summary, snapshot, prepared_payload, marker, approval)
    print(
        "VALID phase4-controlled-publish prepare=PASS publish=PASS "
        "write_requests=1 event=COMMENT next=HUMAN_REVIEW_REQUIRED"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--prepare-once", action="store_true")
    parser.add_argument("--publish-once", action="store_true")
    parser.add_argument("--repository", default="")
    parser.add_argument("--pull-number", type=int, default=0)
    parser.add_argument("--acknowledgement", default="")
    args = parser.parse_args()
    if sum((args.check, args.prepare_once, args.publish_once)) != 1:
        parser.error("choose exactly one action")
    if args.check:
        check()
    elif args.prepare_once:
        prepare_status = prepare_once(args.acknowledgement, args.repository, args.pull_number)
        next_step = (
            "HUMAN_REVIEW_REQUIRED"
            if prepare_status == "PREPARED_NOT_PUBLISHED"
            else "HUMAN_PAYLOAD_REVIEW_REQUIRED"
        )
        print(f"PASS phase4-prepare status={prepare_status} output={OUTPUT_DIR} next={next_step}")
    else:
        if args.repository or args.pull_number:
            parser.error("publish target is fixed by committed contracts")
        publish_once(args.acknowledgement)
        print(f"PASS phase4-publish output={OUTPUT_DIR} next=HUMAN_REVIEW_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
