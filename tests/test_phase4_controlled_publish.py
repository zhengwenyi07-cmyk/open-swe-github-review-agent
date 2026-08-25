from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
import stat
import tempfile
import traceback
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import URLError

from open_swe_review_agent.github_app_auth import (
    GitHubAppAuthError,
    GitHubAppTokenProvider,
    create_app_jwt,
)
from open_swe_review_agent.github_readonly import PullRequestSnapshot
from open_swe_review_agent.github_review_publisher import (
    GitHubPublishError,
    GitHubReviewTransport,
    build_publish_payload,
    find_marker_reviews,
    marker_id,
    validate_publish_payload,
    validate_remote_review,
)

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run_phase4_controlled_publish.py"
REPOSITORY = "example/review-fixture"
BASE = "1" * 40
HEAD = "2" * 40
DIFF = (
    "diff --git a/app.py b/app.py\n"
    "index 3367afd..3e75765 100644\n"
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1 +1 @@\n"
    "-old = 1\n"
    "+new = 2\n"
)


def load_runner() -> object:
    spec = importlib.util.spec_from_file_location("phase4_runner_test", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(
        self,
        payload: object,
        *,
        status: int = 200,
        link: str = "",
        raw: bytes | None = None,
    ) -> None:
        self.body = raw if raw is not None else json.dumps(payload).encode()
        self.offset = 0
        self.status = status
        self.headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(self.body)),
            "Content-Encoding": "identity",
            "Link": link,
        }

    def read(self, amount: int = -1) -> bytes:
        if self.offset >= len(self.body):
            return b""
        end = len(self.body) if amount < 0 else min(len(self.body), self.offset + amount)
        chunk = self.body[self.offset:end]
        self.offset = end
        return chunk

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeOpener:
    def __init__(self, responses: list[FakeResponse] | None = None, error: BaseException | None = None) -> None:
        self.responses = responses or []
        self.error = error
        self.requests: list[object] = []

    def open(self, request: object, timeout: int) -> FakeResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)


class FakeSigner:
    def sign(self, signing_input: bytes, private_key_path: Path) -> bytes:
        self.signing_input = signing_input
        self.private_key_path = private_key_path
        return b"signed"


def snapshot() -> PullRequestSnapshot:
    return PullRequestSnapshot(
        repository=REPOSITORY,
        pull_number=7,
        base_sha=BASE,
        head_sha=HEAD,
        title="Small fix",
        body="Review this",
        state="open",
        files=(),
        diff_text=DIFF,
        anchors=(("app.py", 1),),
        metadata_sha256="3" * 64,
        files_sha256="4" * 64,
        diff_sha256="5" * 64,
        changed_lines_sha256="6" * 64,
    )


def review(*, assessment: str = "confirmed") -> dict[str, object]:
    return {
        "commit_sha": HEAD,
        "summary": "The assignment changes behavior.",
        "findings": [
            {
                "file": "app.py",
                "line": 1,
                "severity": "medium",
                "category": "correctness",
                "assessment": assessment,
                "evidence": "The changed assignment returns the wrong value.",
                "recommendation": "Restore the expected value.",
            }
        ],
        "uncertainties": [],
        "tests": {"status": "NOT_RUN_READ_ONLY", "commands": [], "passed": False},
        "decision": "COMMENT",
    }


def target() -> dict[str, object]:
    return {
        "approval_status": "APPROVED",
        "repository": REPOSITORY,
        "pull_number": 7,
        "authentication_mode": "GITHUB_APP",
        "base_sha": BASE,
        "head_sha": HEAD,
    }


def remote_review(payload: dict[str, object], review_id: int = 91) -> dict[str, object]:
    return {
        "id": review_id,
        "html_url": f"https://github.com/{REPOSITORY}/pull/7#pullrequestreview-{review_id}",
        "body": payload["body"],
        "commit_id": HEAD,
        "state": "COMMENTED",
        "submitted_at": "2026-08-25T00:00:00Z",
    }


def write_publishable_prepared_evidence(runner: object, output: Path) -> tuple[dict[str, object], str, str]:
    file_item = {
        "filename": "app.py",
        "status": "modified",
        "additions": 1,
        "deletions": 1,
        "changes": 2,
        "patch": "@@ -1 +1 @@\n-old = 1\n+new = 2",
    }
    safe_files = [
        {
            "filename": "app.py",
            "status": "modified",
            "additions": 1,
            "deletions": 1,
            "changes": 2,
            "patch_sha256": hashlib.sha256(file_item["patch"].encode()).hexdigest(),
        }
    ]
    lines = [{"file": "app.py", "line": 1}]
    metadata = {
        "repository": REPOSITORY,
        "pull_number": 7,
        "base_sha": BASE,
        "head_sha": HEAD,
        "state": "open",
        "title": "Small fix",
        "body": "Review this",
        "changed_files": 1,
    }
    local_snapshot = PullRequestSnapshot(
        repository=REPOSITORY,
        pull_number=7,
        base_sha=BASE,
        head_sha=HEAD,
        title="Small fix",
        body="Review this",
        state="open",
        files=(file_item,),
        diff_text=DIFF,
        anchors=(("app.py", 1),),
        metadata_sha256=hashlib.sha256(runner.canonical_json(metadata)).hexdigest(),
        files_sha256=hashlib.sha256(runner.canonical_json(safe_files)).hexdigest(),
        diff_sha256=hashlib.sha256(DIFF.encode()).hexdigest(),
        changed_lines_sha256=hashlib.sha256(runner.canonical_json(lines)).hexdigest(),
    )
    local_review = review()
    runner.atomic_json(output / "pr_snapshot.json", runner.snapshot_json(local_snapshot))
    runner.atomic_text(output / "diff.patch", DIFF)
    runner.atomic_json(output / "changed_lines.json", lines)
    runner.atomic_json(output / "review.json", local_review)
    runner.atomic_text(output / "review.md", runner.render_markdown(local_review))
    review_hash = runner.file_sha256(output / "review.json")
    payload, marker = runner.build_publish_payload(
        local_review,
        local_snapshot,
        evidence_commit="a" * 40,
        review_file_sha256=review_hash,
    )
    runner.atomic_text(output / "publish_payload.json", runner.canonical_json(payload).decode())
    payload_hash = runner.file_sha256(output / "publish_payload.json")
    runner.atomic_json(
        output / "prepare_summary.json",
        {
            "status": "PREPARED_AWAITING_HUMAN_APPROVAL",
            "contract_commit": "a" * 40,
            "repository": REPOSITORY,
            "pull_number": 7,
            "base_sha": BASE,
            "head_sha": HEAD,
            "authentication_mode": "GITHUB_APP",
            "model": "mimo-v2.5-pro",
            "response_model": "mimo-v2.5-pro",
            "finish_reason": "tool_calls",
            "model_calls": 1,
            "github_token_pull_requests_permission": "read",
            "review_file_sha256": review_hash,
            "publish_payload_sha256": payload_hash,
            "idempotency_marker": marker,
            "publishable_findings": 1,
            "github_review_write_requests": 0,
            "github_write_performed": False,
            "pr_code_executed": False,
            "tests_status": "NOT_RUN_READ_ONLY",
            "automatic_retries": 0,
        },
    )
    return payload, marker, payload_hash


def write_publish_success_evidence(
    runner: object,
    output: Path,
    payload: dict[str, object],
    marker: str,
    payload_hash: str,
) -> None:
    remote = remote_review(payload)
    comments = [dict(payload["comments"][0])]
    receipt = runner.validate_remote_review(
        remote,
        comments,
        payload,
        expected_repository=REPOSITORY,
        expected_pull_number=7,
    )
    receipt.update(
        {
            "status": "PUBLISHED_AND_VERIFIED",
            "repository": REPOSITORY,
            "pull_number": 7,
            "base_sha": BASE,
            "head_sha": HEAD,
            "payload_sha256": payload_hash,
            "idempotency_marker": marker,
            "reconciled_after_ambiguous_response": False,
            "remote_review_sha256": hashlib.sha256(runner.canonical_json(remote)).hexdigest(),
            "remote_comments_sha256": hashlib.sha256(runner.canonical_json(comments)).hexdigest(),
        }
    )
    runner.atomic_json(output / "publish_receipt.json", receipt)
    runner.atomic_json(
        output / "run_summary.json",
        {
            "status": "PASS",
            "next_step": "HUMAN_REVIEW_REQUIRED",
            "repository": REPOSITORY,
            "pull_number": 7,
            "base_sha": BASE,
            "head_sha": HEAD,
            "github_auth_token_requests": 1,
            "github_token_pull_requests_permission": "write",
            "github_get_requests": 4,
            "github_response_bytes": 90,
            "github_review_write_requests": 1,
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
            "payload_sha256": payload_hash,
            "idempotency_marker": marker,
            "comments_verified": 1,
        },
    )


class Phase4ControlledPublishTests(unittest.TestCase):
    def test_jwt_is_rs256_and_does_not_contain_private_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "app.pem"
            key.write_text("SECRET_PRIVATE_KEY")
            key.chmod(stat.S_IRUSR | stat.S_IWUSR)
            signer = FakeSigner()
            token = create_app_jwt(123, key, signer=signer, now=1_700_000_000)
        self.assertEqual(len(token.split(".")), 3)
        self.assertNotIn("SECRET_PRIVATE_KEY", token)
        self.assertEqual(signer.private_key_path, key)

    def test_private_key_permissions_must_be_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "app.pem"
            key.write_text("secret")
            key.chmod(0o644)
            with self.assertRaisesRegex(GitHubAppAuthError, "PRIVATE_KEY_PERMISSIONS_TOO_OPEN"):
                create_app_jwt(1, key, signer=FakeSigner(), now=1_700_000_000)

    def test_installation_token_is_scoped_to_one_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "app.pem"
            key.write_text("secret")
            key.chmod(0o600)
            opener = FakeOpener(
                [
                    FakeResponse(
                        {
                            "token": "ghs_SECRET_INSTALLATION_TOKEN",
                            "expires_at": "2026-08-25T01:00:00Z",
                            "permissions": {"pull_requests": "write", "metadata": "read"},
                            "repositories": [{"full_name": REPOSITORY}],
                        },
                        status=201,
                    )
                ]
            )
            provider = GitHubAppTokenProvider(
                1,
                2,
                key,
                REPOSITORY,
                opener=opener,
                signer=FakeSigner(),
            )
            token = provider.mint()
        request = opener.requests[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "https://api.github.com/app/installations/2/access_tokens")
        self.assertEqual(json.loads(request.data), {"permissions": {"pull_requests": "write"}, "repositories": ["review-fixture"]})
        self.assertEqual(token.value, "ghs_SECRET_INSTALLATION_TOKEN")
        self.assertEqual(provider.request_count, 1)

    def test_installation_scope_mismatch_is_rejected_without_token_leak(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "app.pem"
            key.write_text("secret")
            key.chmod(0o600)
            opener = FakeOpener(
                [
                    FakeResponse(
                        {
                            "token": "SECRET_TOKEN_BODY",
                            "expires_at": "later",
                            "permissions": {"contents": "write"},
                            "repositories": [{"full_name": "other/repo"}],
                        },
                        status=201,
                    )
                ]
            )
            provider = GitHubAppTokenProvider(1, 2, key, REPOSITORY, opener=opener, signer=FakeSigner())
            with self.assertRaises(GitHubAppAuthError) as caught:
                provider.mint()
        self.assertNotIn("SECRET_TOKEN_BODY", "".join(traceback.format_exception(caught.exception)))

    def test_prepare_can_downscope_installation_token_to_pull_requests_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "app.pem"
            key.write_text("secret")
            key.chmod(0o600)
            opener = FakeOpener(
                [
                    FakeResponse(
                        {
                            "token": "read-token",
                            "expires_at": "2026-08-25T01:00:00Z",
                            "permissions": {"pull_requests": "read", "metadata": "read"},
                            "repositories": [{"full_name": REPOSITORY}],
                        },
                        status=201,
                    )
                ]
            )
            provider = GitHubAppTokenProvider(
                1,
                2,
                key,
                REPOSITORY,
                pull_requests_permission="read",
                opener=opener,
                signer=FakeSigner(),
            )
            provider.mint()
        self.assertEqual(json.loads(opener.requests[0].data)["permissions"], {"pull_requests": "read"})

    def test_payload_is_deterministic_comment_and_only_publishes_confirmed_finding(self) -> None:
        payload_a, marker_a = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        payload_b, marker_b = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        self.assertEqual(payload_a, payload_b)
        self.assertEqual(marker_a, marker_b)
        self.assertEqual(payload_a["event"], "COMMENT")
        self.assertEqual(payload_a["comments"][0]["side"], "RIGHT")
        self.assertIn(marker_a, payload_a["body"])

    def test_confirmed_findings_on_same_changed_line_merge_deterministically(self) -> None:
        candidate = review()
        candidate["findings"].append(
            {
                "file": "app.py",
                "line": 1,
                "severity": "high",
                "category": "maintainability",
                "assessment": "confirmed",
                "evidence": "The same changed line also bypasses the fallback.",
                "recommendation": "Preserve the fallback while restoring the value.",
            }
        )

        payload_a, marker_a = build_publish_payload(candidate, snapshot(), evidence_commit="a" * 40)
        payload_b, marker_b = build_publish_payload(candidate, snapshot(), evidence_commit="a" * 40)

        self.assertEqual(payload_a, payload_b)
        self.assertEqual(marker_a, marker_b)
        self.assertEqual(len(payload_a["comments"]), 1)
        self.assertEqual(payload_a["comments"][0]["path"], "app.py")
        self.assertEqual(payload_a["comments"][0]["line"], 1)
        self.assertIn("The changed assignment returns the wrong value.", payload_a["comments"][0]["body"])
        self.assertIn("The same changed line also bypasses the fallback.", payload_a["comments"][0]["body"])

    def test_marker_binds_review_hash_without_payload_self_reference(self) -> None:
        first = marker_id(REPOSITORY, 7, HEAD, "a" * 64)
        second = marker_id(REPOSITORY, 7, HEAD, "b" * 64)
        self.assertNotEqual(first, second)
        self.assertEqual(first, marker_id(REPOSITORY, 7, HEAD, "a" * 64))

    def test_no_confirmed_finding_refuses_publication(self) -> None:
        with self.assertRaisesRegex(GitHubPublishError, "PUBLISHABLE_FINDING_COUNT_INVALID"):
            build_publish_payload(review(assessment="suggestion"), snapshot(), evidence_commit="a" * 40)

    def test_payload_rejects_event_or_changed_line_tampering(self) -> None:
        payload, marker = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        payload["event"] = "APPROVE"
        with self.assertRaises(GitHubPublishError):
            validate_publish_payload(payload, snapshot(), expected_marker=marker)
        payload["event"] = "COMMENT"
        payload["comments"][0]["line"] = 2
        with self.assertRaises(GitHubPublishError):
            validate_publish_payload(payload, snapshot(), expected_marker=marker)

    def test_transport_allows_only_review_gets_and_one_review_post_shape(self) -> None:
        payload, _ = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        opener = FakeOpener([FakeResponse(remote_review(payload))])
        transport = GitHubReviewTransport("SECRET_TOKEN", REPOSITORY, 7, opener=opener)
        transport.post_review(payload)
        self.assertEqual(transport.stats.write_requests, 1)
        self.assertEqual(opener.requests[0].get_method(), "POST")
        self.assertTrue(opener.requests[0].full_url.endswith("/pulls/7/reviews"))
        self.assertEqual(opener.requests[0].data, json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        with self.assertRaisesRegex(GitHubPublishError, "READ_PATH_NOT_ALLOWED"):
            transport.get_json("/repos/example/review-fixture/issues/7/comments")
        self.assertEqual(len(opener.requests), 1)

    def test_review_pagination_is_rejected(self) -> None:
        opener = FakeOpener([FakeResponse([], link='<https://api.github.com/page=2>; rel="next"')])
        transport = GitHubReviewTransport("token", REPOSITORY, 7, opener=opener)
        with self.assertRaisesRegex(GitHubPublishError, "PAGINATION_LIMIT_EXCEEDED"):
            transport.get_json(transport.reviews_path, query={"page": 1, "per_page": 100})

    def test_existing_marker_is_detected(self) -> None:
        payload, marker = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        matches = find_marker_reviews([remote_review(payload)], marker)
        self.assertEqual(len(matches), 1)

    def test_remote_review_and_inline_comments_must_equal_payload(self) -> None:
        payload, _ = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        remote = remote_review(payload)
        comments = [dict(payload["comments"][0])]
        receipt = validate_remote_review(remote, comments, payload, expected_repository=REPOSITORY, expected_pull_number=7)
        self.assertEqual(receipt["review_id"], 91)
        comments[0]["line"] = 2
        with self.assertRaisesRegex(GitHubPublishError, "REMOTE_COMMENTS_MISMATCH"):
            validate_remote_review(remote, comments, payload, expected_repository=REPOSITORY, expected_pull_number=7)

    def test_transport_exception_is_sanitized_and_marks_write_ambiguous(self) -> None:
        payload, _ = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        transport = GitHubReviewTransport(
            "SECRET_TOKEN",
            REPOSITORY,
            7,
            opener=FakeOpener(error=URLError("SECRET_REMOTE_RESPONSE")),
        )
        with self.assertRaises(GitHubPublishError) as caught:
            transport.post_review(payload)
        self.assertTrue(caught.exception.ambiguous)
        trace = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn("SECRET_REMOTE_RESPONSE", trace)
        self.assertNotIn("SECRET_TOKEN", trace)

    def test_invalid_json_after_post_is_ambiguous_and_eligible_for_reconciliation(self) -> None:
        payload, _ = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        transport = GitHubReviewTransport(
            "token",
            REPOSITORY,
            7,
            opener=FakeOpener([FakeResponse({}, raw=b"{")]),
        )
        with self.assertRaises(GitHubPublishError) as caught:
            transport.post_review(payload)
        self.assertEqual(caught.exception.reason, "RESPONSE_INVALID")
        self.assertTrue(caught.exception.ambiguous)
        self.assertEqual(transport.stats.write_requests, 1)

    def test_remote_review_url_must_be_exact_not_prefix_only(self) -> None:
        payload, _ = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        remote = remote_review(payload)
        remote["html_url"] += "/attacker-controlled-suffix"
        with self.assertRaisesRegex(GitHubPublishError, "REMOTE_REVIEW_MISMATCH"):
            validate_remote_review(
                remote,
                [dict(payload["comments"][0])],
                payload,
                expected_repository=REPOSITORY,
                expected_pull_number=7,
            )

    def test_prepare_unapproved_target_refuses_before_app_client(self) -> None:
        runner = load_runner()
        environment = {
            "OPEN_SWE_PHASE4_PREPARE_ALLOW_NETWORK": "YES_ONCE",
            "MIMO_ACCOUNT_TYPE": "PAY_AS_YOU_GO",
            "MIMO_API_KEY": "not-a-real-key",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(runner, "ensure_clean_committed_contract", return_value="a" * 40),
            patch.object(runner, "load_target_contract", return_value={"approval_status": "NOT_APPROVED"}),
            patch.object(runner, "create_token_provider") as provider,
        ):
            with self.assertRaisesRegex(RuntimeError, "TARGET_PR_NOT_APPROVED"):
                runner.prepare_once(runner.PREPARE_ACK, REPOSITORY, 7)
        provider.assert_not_called()

    def test_target_contract_rejects_third_party_repository(self) -> None:
        runner = load_runner()
        contract = {
            "version": "phase4_target_v1",
            "approval_status": "APPROVED",
            "repository": "third-party/repository",
            "pull_number": 7,
            "authentication_mode": "GITHUB_APP",
            "base_sha": BASE,
            "head_sha": HEAD,
            "prepare_github_write_allowed": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.json"
            path.write_text(json.dumps(contract))
            with patch.object(runner, "TARGET_CONTRACT", path):
                with self.assertRaisesRegex(RuntimeError, "TARGET_REPOSITORY_NOT_CONTROLLED"):
                    runner.load_target_contract()

    def test_private_key_must_be_outside_repository(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "app.pem"
            key.write_text("secret")
            key.chmod(0o600)
            environment = {
                "GITHUB_APP_ID": "1",
                "GITHUB_APP_INSTALLATION_ID": "2",
                "GITHUB_APP_PRIVATE_KEY_PATH": str(key),
            }
            with patch.dict(os.environ, environment, clear=True), patch.object(runner, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "MUST_BE_OUTSIDE_REPOSITORY"):
                    runner.create_token_provider(REPOSITORY, "write")

    def test_publish_rejects_changed_implementation_since_prepare_commit(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.txt").write_bytes(b"new")
            historical = SimpleNamespace(stdout=b"old")
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "IMMUTABLE_AFTER_PREPARE_FILES", ("file.txt",)),
                patch.object(runner, "run", return_value=""),
                patch.object(runner.subprocess, "run", return_value=historical),
            ):
                with self.assertRaisesRegex(RuntimeError, "PREPARE_CONTRACT_IDENTITY_MISMATCH"):
                    runner.verify_prepare_contract_identity("a" * 40)

    def test_prepare_dirty_contract_refuses_before_app_client(self) -> None:
        runner = load_runner()
        environment = {
            "OPEN_SWE_PHASE4_PREPARE_ALLOW_NETWORK": "YES_ONCE",
            "MIMO_ACCOUNT_TYPE": "PAY_AS_YOU_GO",
            "MIMO_API_KEY": "not-a-real-key",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(runner, "ensure_clean_committed_contract", side_effect=RuntimeError("WORKTREE_NOT_CLEAN")),
            patch.object(runner, "create_token_provider") as provider,
        ):
            with self.assertRaisesRegex(RuntimeError, "WORKTREE_NOT_CLEAN"):
                runner.prepare_once(runner.PREPARE_ACK, REPOSITORY, 7)
        provider.assert_not_called()

    def test_publish_unapproved_payload_refuses_before_app_client(self) -> None:
        runner = load_runner()
        with (
            patch.dict(os.environ, {"OPEN_SWE_PHASE4_PUBLISH_ALLOW_WRITE": "YES_ONCE"}, clear=True),
            patch.object(runner, "ensure_clean_committed_contract", return_value="a" * 40),
            patch.object(runner, "load_target_contract", return_value=target()),
            patch.object(runner, "load_publish_approval", return_value={"approval_status": "NOT_APPROVED"}),
            patch.object(runner, "create_token_provider") as provider,
        ):
            with self.assertRaisesRegex(RuntimeError, "PUBLISH_NOT_APPROVED"):
                runner.publish_once(runner.PUBLISH_ACK)
        provider.assert_not_called()

    def test_publish_success_uses_exactly_one_write_and_verifies_remote_comments(self) -> None:
        runner = load_runner()
        payload, marker = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        approval = {
            **target(),
            "approval_status": "APPROVED",
            "payload_sha256": "f" * 64,
        }
        fake_provider = SimpleNamespace(
            request_count=1,
            response_bytes=20,
            mint=Mock(return_value=SimpleNamespace(value="token")),
        )
        fake_read_transport = SimpleNamespace(stats=SimpleNamespace(request_count=1, response_bytes=30))
        fake_read_client = SimpleNamespace(
            metadata=Mock(
                return_value={
                    "number": 7,
                    "state": "open",
                    "draft": False,
                    "base": {"sha": BASE, "repo": {"full_name": REPOSITORY}},
                    "head": {"sha": HEAD},
                }
            )
        )

        class FakePublisher:
            def __init__(self) -> None:
                self.reviews_path = "/repos/example/review-fixture/pulls/7/reviews"
                self.stats = SimpleNamespace(write_requests=0, get_requests=3, response_bytes=40)
                self.list_calls = 0

            def get_json(self, path: str, query: object = None) -> object:
                if path == self.reviews_path:
                    self.list_calls += 1
                    return []
                if path.endswith("/comments"):
                    return [dict(payload["comments"][0])]
                return remote_review(payload)

            def post_review(self, candidate: object) -> dict[str, object]:
                self.stats.write_requests += 1
                self.asserted_payload = candidate
                return remote_review(payload)

        publisher = FakePublisher()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "phase4"
            output.mkdir()
            (output / "publish_payload.json").write_text("payload")
            (output / "prepare_summary.json").write_text(json.dumps({"contract_commit": "a" * 40}))
            with (
                patch.dict(os.environ, {"OPEN_SWE_PHASE4_PUBLISH_ALLOW_WRITE": "YES_ONCE"}, clear=True),
                patch.object(runner, "OUTPUT_DIR", output),
                patch.object(runner, "LOCK_PATH", Path(directory) / "lock"),
                patch.object(runner, "ensure_clean_committed_contract", return_value="a" * 40),
                patch.object(runner, "load_target_contract", return_value=target()),
                patch.object(runner, "load_publish_approval", return_value=approval),
                patch.object(runner, "_snapshot_from_prepared", return_value=(snapshot(), review(), payload, marker)),
                patch.object(runner, "verify_prepare_contract_identity"),
                patch.object(runner, "file_sha256", return_value="f" * 64),
                patch.object(runner, "create_token_provider", return_value=fake_provider),
                patch.object(runner, "GitHubReadOnlyTransport", return_value=fake_read_transport),
                patch.object(runner, "GitHubReadOnlyClient", return_value=fake_read_client),
                patch.object(runner, "GitHubReviewTransport", return_value=publisher),
            ):
                runner.publish_once(runner.PUBLISH_ACK)
            summary = json.loads((output / "run_summary.json").read_text())
            receipt = json.loads((output / "publish_receipt.json").read_text())
        self.assertEqual(publisher.stats.write_requests, 1)
        self.assertEqual(summary["github_review_write_requests"], 1)
        self.assertEqual(summary["github_review_event"], "COMMENT")
        self.assertEqual(summary["github_token_pull_requests_permission"], "write")
        self.assertEqual(summary["github_response_bytes"], 90)
        self.assertEqual(receipt["comments_verified"], 1)
        self.assertRegex(receipt["remote_review_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(receipt["remote_comments_sha256"], r"^[0-9a-f]{64}$")

    def test_head_drift_refuses_before_review_transport_or_post(self) -> None:
        runner = load_runner()
        payload, marker = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        approval = {**target(), "approval_status": "APPROVED", "payload_sha256": "f" * 64}
        provider = SimpleNamespace(
            request_count=1,
            response_bytes=10,
            mint=Mock(return_value=SimpleNamespace(value="token")),
        )
        read_transport = SimpleNamespace(stats=SimpleNamespace(request_count=1, response_bytes=10))
        read_client = SimpleNamespace(
            metadata=Mock(
                return_value={
                    "number": 7,
                    "state": "open",
                    "draft": False,
                    "base": {"sha": BASE, "repo": {"full_name": REPOSITORY}},
                    "head": {"sha": "9" * 40},
                }
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "phase4"
            output.mkdir()
            (output / "publish_payload.json").write_text("payload")
            (output / "prepare_summary.json").write_text(json.dumps({"contract_commit": "a" * 40}))
            with (
                patch.dict(os.environ, {"OPEN_SWE_PHASE4_PUBLISH_ALLOW_WRITE": "YES_ONCE"}, clear=True),
                patch.object(runner, "OUTPUT_DIR", output),
                patch.object(runner, "LOCK_PATH", Path(directory) / "lock"),
                patch.object(runner, "ensure_clean_committed_contract", return_value="a" * 40),
                patch.object(runner, "load_target_contract", return_value=target()),
                patch.object(runner, "load_publish_approval", return_value=approval),
                patch.object(runner, "_snapshot_from_prepared", return_value=(snapshot(), review(), payload, marker)),
                patch.object(runner, "verify_prepare_contract_identity"),
                patch.object(runner, "file_sha256", return_value="f" * 64),
                patch.object(runner, "create_token_provider", return_value=provider),
                patch.object(runner, "GitHubReadOnlyTransport", return_value=read_transport),
                patch.object(runner, "GitHubReadOnlyClient", return_value=read_client),
                patch.object(runner, "GitHubReviewTransport") as publisher,
            ):
                with self.assertRaisesRegex(RuntimeError, "TARGET_RECHECK:LIVE_PR_IDENTITY_MISMATCH"):
                    runner.publish_once(runner.PUBLISH_ACK)
            failure = json.loads((output / "failure.json").read_text())
        publisher.assert_not_called()
        self.assertEqual(failure["github_review_write_requests"], 0)

    def test_ambiguous_post_is_reconciled_by_get_without_second_post(self) -> None:
        runner = load_runner()
        payload, marker = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        approval = {**target(), "approval_status": "APPROVED", "payload_sha256": "f" * 64}
        provider = SimpleNamespace(
            request_count=1,
            response_bytes=20,
            mint=Mock(return_value=SimpleNamespace(value="token")),
        )
        read_transport = SimpleNamespace(stats=SimpleNamespace(request_count=1, response_bytes=30))
        read_client = SimpleNamespace(
            metadata=Mock(
                return_value={
                    "number": 7,
                    "state": "open",
                    "draft": False,
                    "base": {"sha": BASE, "repo": {"full_name": REPOSITORY}},
                    "head": {"sha": HEAD},
                }
            )
        )

        class AmbiguousPublisher:
            def __init__(self) -> None:
                self.reviews_path = "/repos/example/review-fixture/pulls/7/reviews"
                self.stats = SimpleNamespace(write_requests=0, get_requests=4, response_bytes=40)
                self.list_calls = 0

            def get_json(self, path: str, query: object = None) -> object:
                if path == self.reviews_path:
                    self.list_calls += 1
                    return [] if self.list_calls == 1 else [remote_review(payload)]
                if path.endswith("/comments"):
                    return [dict(payload["comments"][0])]
                return remote_review(payload)

            def post_review(self, candidate: object) -> dict[str, object]:
                self.stats.write_requests += 1
                raise GitHubPublishError("TRANSPORT_FAILURE", ambiguous=True)

        publisher = AmbiguousPublisher()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "phase4"
            output.mkdir()
            (output / "publish_payload.json").write_text("payload")
            (output / "prepare_summary.json").write_text(json.dumps({"contract_commit": "a" * 40}))
            with (
                patch.dict(os.environ, {"OPEN_SWE_PHASE4_PUBLISH_ALLOW_WRITE": "YES_ONCE"}, clear=True),
                patch.object(runner, "OUTPUT_DIR", output),
                patch.object(runner, "LOCK_PATH", Path(directory) / "lock"),
                patch.object(runner, "ensure_clean_committed_contract", return_value="a" * 40),
                patch.object(runner, "load_target_contract", return_value=target()),
                patch.object(runner, "load_publish_approval", return_value=approval),
                patch.object(runner, "_snapshot_from_prepared", return_value=(snapshot(), review(), payload, marker)),
                patch.object(runner, "verify_prepare_contract_identity"),
                patch.object(runner, "file_sha256", return_value="f" * 64),
                patch.object(runner, "create_token_provider", return_value=provider),
                patch.object(runner, "GitHubReadOnlyTransport", return_value=read_transport),
                patch.object(runner, "GitHubReadOnlyClient", return_value=read_client),
                patch.object(runner, "GitHubReviewTransport", return_value=publisher),
            ):
                runner.publish_once(runner.PUBLISH_ACK)
            receipt = json.loads((output / "publish_receipt.json").read_text())
        self.assertEqual(publisher.stats.write_requests, 1)
        self.assertEqual(publisher.list_calls, 2)
        self.assertTrue(receipt["reconciled_after_ambiguous_response"])

    def test_check_rebinds_approval_receipt_summary_payload_and_marker(self) -> None:
        runner = load_runner()
        mutations = ("approval_repository", "receipt_commit", "malicious_url", "forged_marker", "comment_count")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "phase4"
                output.mkdir()
                payload, marker, payload_hash = write_publishable_prepared_evidence(runner, output)
                write_publish_success_evidence(runner, output, payload, marker, payload_hash)
                approval = {**target(), "approval_status": "APPROVED", "payload_sha256": payload_hash}
                receipt = json.loads((output / "publish_receipt.json").read_text())
                summary = json.loads((output / "run_summary.json").read_text())
                if mutation == "approval_repository":
                    approval["repository"] = "attacker/other"
                elif mutation == "receipt_commit":
                    receipt["commit_id"] = "9" * 40
                elif mutation == "malicious_url":
                    bad_url = receipt["html_url"] + "/attacker"
                    receipt["html_url"] = bad_url
                    summary["review_html_url"] = bad_url
                elif mutation == "forged_marker":
                    receipt["idempotency_marker"] = "f" * 64
                    summary["idempotency_marker"] = "f" * 64
                else:
                    receipt["comments_verified"] = 2
                    summary["comments_verified"] = 2
                runner.atomic_json(output / "publish_receipt.json", receipt)
                runner.atomic_json(output / "run_summary.json", summary)
                with (
                    patch.object(runner, "OUTPUT_DIR", output),
                    patch.object(runner, "load_target_contract", return_value=target()),
                    patch.object(runner, "load_publish_approval", return_value=approval),
                ):
                    with self.assertRaises(RuntimeError):
                        runner.check()

    def test_check_accepts_only_fully_bound_success_evidence(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "phase4"
            output.mkdir()
            payload, marker, payload_hash = write_publishable_prepared_evidence(runner, output)
            write_publish_success_evidence(runner, output, payload, marker, payload_hash)
            approval = {**target(), "approval_status": "APPROVED", "payload_sha256": payload_hash}
            stdout = io.StringIO()
            with (
                patch.object(runner, "OUTPUT_DIR", output),
                patch.object(runner, "load_target_contract", return_value=target()),
                patch.object(runner, "load_publish_approval", return_value=approval),
                redirect_stdout(stdout),
            ):
                runner.check()
        self.assertIn("prepare=PASS publish=PASS", stdout.getvalue())

    def test_summary_write_failure_preserves_verified_remote_receipt(self) -> None:
        runner = load_runner()
        payload, marker = build_publish_payload(review(), snapshot(), evidence_commit="a" * 40)
        approval = {**target(), "approval_status": "APPROVED", "payload_sha256": "f" * 64}
        provider = SimpleNamespace(
            request_count=1,
            response_bytes=20,
            mint=Mock(return_value=SimpleNamespace(value="token")),
        )
        read_transport = SimpleNamespace(stats=SimpleNamespace(request_count=1, response_bytes=30))
        read_client = SimpleNamespace(
            metadata=Mock(
                return_value={
                    "number": 7,
                    "state": "open",
                    "draft": False,
                    "base": {"sha": BASE, "repo": {"full_name": REPOSITORY}},
                    "head": {"sha": HEAD},
                }
            )
        )

        class Publisher:
            def __init__(self) -> None:
                self.reviews_path = "/repos/example/review-fixture/pulls/7/reviews"
                self.stats = SimpleNamespace(write_requests=0, get_requests=3, response_bytes=40)

            def get_json(self, path: str, query: object = None) -> object:
                if path == self.reviews_path:
                    return []
                if path.endswith("/comments"):
                    return [dict(payload["comments"][0])]
                return remote_review(payload)

            def post_review(self, candidate: object) -> dict[str, object]:
                self.stats.write_requests += 1
                return remote_review(payload)

        publisher = Publisher()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "phase4"
            output.mkdir()
            (output / "publish_payload.json").write_text("payload")
            (output / "prepare_summary.json").write_text(json.dumps({"contract_commit": "a" * 40}))
            original_atomic_json = runner.atomic_json

            def fail_only_summary(path: Path, candidate: object) -> None:
                if path.name == "run_summary.json":
                    raise OSError("SECRET_LOCAL_WRITE_FAILURE")
                original_atomic_json(path, candidate)

            with (
                patch.dict(os.environ, {"OPEN_SWE_PHASE4_PUBLISH_ALLOW_WRITE": "YES_ONCE"}, clear=True),
                patch.object(runner, "OUTPUT_DIR", output),
                patch.object(runner, "LOCK_PATH", Path(directory) / "lock"),
                patch.object(runner, "ensure_clean_committed_contract", return_value="a" * 40),
                patch.object(runner, "load_target_contract", return_value=target()),
                patch.object(runner, "load_publish_approval", return_value=approval),
                patch.object(runner, "_snapshot_from_prepared", return_value=(snapshot(), review(), payload, marker)),
                patch.object(runner, "verify_prepare_contract_identity"),
                patch.object(runner, "file_sha256", return_value="f" * 64),
                patch.object(runner, "create_token_provider", return_value=provider),
                patch.object(runner, "GitHubReadOnlyTransport", return_value=read_transport),
                patch.object(runner, "GitHubReadOnlyClient", return_value=read_client),
                patch.object(runner, "GitHubReviewTransport", return_value=publisher),
                patch.object(runner, "atomic_json", side_effect=fail_only_summary),
            ):
                with self.assertRaises(RuntimeError) as caught:
                    runner.publish_once(runner.PUBLISH_ACK)
            receipt = json.loads((output / "publish_receipt.json").read_text())
            failure = json.loads((output / "failure.json").read_text())
        self.assertTrue((receipt["review_id"], receipt["html_url"]))
        self.assertTrue(failure["remote_side_effect_confirmed"])
        self.assertEqual(failure["remote_review_id"], receipt["review_id"])
        self.assertEqual(failure["remote_review_html_url"], receipt["html_url"])
        self.assertNotIn("SECRET_LOCAL_WRITE_FAILURE", "".join(traceback.format_exception(caught.exception)))

    def test_check_accepts_preserved_receipt_only_as_local_summary_failure(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "phase4"
            output.mkdir()
            payload, marker, payload_hash = write_publishable_prepared_evidence(runner, output)
            write_publish_success_evidence(runner, output, payload, marker, payload_hash)
            receipt = json.loads((output / "publish_receipt.json").read_text())
            (output / "run_summary.json").unlink()
            runner.atomic_json(
                output / "failure.json",
                {
                    "status": "FAILED",
                    "failure_stage": "REMOTE_VERIFICATION",
                    "failure_reason": "SAFE_EXECUTION_FAILURE",
                    "github_review_write_requests": 1,
                    "ambiguous_write_state": False,
                    "automatic_post_retries": 0,
                    "remote_side_effect_confirmed": True,
                    "remote_review_id": receipt["review_id"],
                    "remote_review_html_url": receipt["html_url"],
                },
            )
            approval = {**target(), "approval_status": "APPROVED", "payload_sha256": payload_hash}
            stdout = io.StringIO()
            with (
                patch.object(runner, "OUTPUT_DIR", output),
                patch.object(runner, "load_target_contract", return_value=target()),
                patch.object(runner, "load_publish_approval", return_value=approval),
                redirect_stdout(stdout),
            ):
                runner.check()
        self.assertIn("PUBLISHED_REMOTE_VERIFIED_LOCAL_SUMMARY_FAILED", stdout.getvalue())

    def test_no_finding_prepare_cli_reports_human_review_not_payload_review(self) -> None:
        runner = load_runner()
        stdout = io.StringIO()
        argv = [
            "run_phase4_controlled_publish.py",
            "--prepare-once",
            "--repository",
            REPOSITORY,
            "--pull-number",
            "7",
            "--acknowledgement",
            runner.PREPARE_ACK,
        ]
        with (
            patch("sys.argv", argv),
            patch.object(runner, "prepare_once", return_value="PREPARED_NOT_PUBLISHED"),
            redirect_stdout(stdout),
        ):
            self.assertEqual(runner.main(), 0)
        self.assertIn("next=HUMAN_REVIEW_REQUIRED", stdout.getvalue())
        self.assertNotIn("next=HUMAN_PAYLOAD_REVIEW_REQUIRED", stdout.getvalue())

    def test_offline_check_reports_not_started_without_artifacts(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(runner, "OUTPUT_DIR", Path(directory) / "missing"),
                patch.object(runner, "load_target_contract", return_value={"approval_status": "NOT_APPROVED"}),
                patch.object(runner, "load_publish_approval", return_value={"approval_status": "NOT_APPROVED"}),
            ):
                runner.check()

    def test_no_confirmed_finding_is_preserved_as_not_published_result(self) -> None:
        runner = load_runner()
        local_review = review(assessment="suggestion")
        file_item = {
            "filename": "app.py",
            "status": "modified",
            "additions": 1,
            "deletions": 1,
            "changes": 2,
            "patch": "@@ -1 +1 @@\n-old = 1\n+new = 2",
        }
        safe_files = [
            {
                "filename": "app.py",
                "status": "modified",
                "additions": 1,
                "deletions": 1,
                "changes": 2,
                "patch_sha256": hashlib.sha256(file_item["patch"].encode()).hexdigest(),
            }
        ]
        lines = [{"file": "app.py", "line": 1}]
        metadata_evidence = {
            "repository": REPOSITORY,
            "pull_number": 7,
            "base_sha": BASE,
            "head_sha": HEAD,
            "state": "open",
            "title": "Small fix",
            "body": "Review this",
            "changed_files": 1,
        }
        local_snapshot = PullRequestSnapshot(
            repository=REPOSITORY,
            pull_number=7,
            base_sha=BASE,
            head_sha=HEAD,
            title="Small fix",
            body="Review this",
            state="open",
            files=(file_item,),
            diff_text=DIFF,
            anchors=(("app.py", 1),),
            metadata_sha256=hashlib.sha256(runner.canonical_json(metadata_evidence)).hexdigest(),
            files_sha256=hashlib.sha256(runner.canonical_json(safe_files)).hexdigest(),
            diff_sha256=hashlib.sha256(DIFF.encode()).hexdigest(),
            changed_lines_sha256=hashlib.sha256(runner.canonical_json(lines)).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "phase4"
            output.mkdir()
            runner.atomic_json(output / "pr_snapshot.json", runner.snapshot_json(local_snapshot))
            runner.atomic_text(output / "diff.patch", DIFF)
            runner.atomic_json(output / "changed_lines.json", lines)
            runner.atomic_json(output / "review.json", local_review)
            runner.atomic_text(output / "review.md", runner.render_markdown(local_review))
            review_hash = runner.file_sha256(output / "review.json")
            runner.atomic_json(
                output / "prepare_summary.json",
                {
                    "status": "PREPARED_NOT_PUBLISHED",
                    "contract_commit": "a" * 40,
                    "repository": REPOSITORY,
                    "pull_number": 7,
                    "base_sha": BASE,
                    "head_sha": HEAD,
                    "authentication_mode": "GITHUB_APP",
                    "model": "mimo-v2.5-pro",
                    "response_model": "mimo-v2.5-pro",
                    "finish_reason": "tool_calls",
                    "model_calls": 1,
                    "github_token_pull_requests_permission": "read",
                    "review_file_sha256": review_hash,
                    "publish_payload_sha256": None,
                    "idempotency_marker": None,
                    "publishable_findings": 0,
                    "github_review_write_requests": 0,
                    "github_write_performed": False,
                    "pr_code_executed": False,
                    "tests_status": "NOT_RUN_READ_ONLY",
                    "automatic_retries": 0,
                },
            )
            with (
                patch.object(runner, "OUTPUT_DIR", output),
                patch.object(runner, "load_target_contract", return_value=target()),
                patch.object(runner, "load_publish_approval", return_value={"approval_status": "NOT_APPROVED"}),
            ):
                runner.check()
            self.assertFalse((output / "publish_payload.json").exists())


if __name__ == "__main__":
    unittest.main()
