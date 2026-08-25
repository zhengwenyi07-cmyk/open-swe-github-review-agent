"""Deterministic, single-endpoint GitHub Review publishing for Phase 4."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from .contracts import validate_review
from .github_readonly import JSON_ACCEPT, NoRedirect, OpenerLike, PullRequestSnapshot, canonical_json

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MARKER_RE = re.compile(r"^<!-- open-swe-review-agent:phase4:([0-9a-f]{64}) -->$")
REVIEW_ID_PATH_RE = re.compile(
    r"^/repos/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)/pulls/([1-9][0-9]*)/reviews/([1-9][0-9]*)(/comments)?$"
)


class GitHubPublishError(RuntimeError):
    """A fixed-code publisher failure without remote response material."""

    def __init__(self, reason: str, *, ambiguous: bool = False) -> None:
        self.reason = reason
        self.ambiguous = ambiguous
        super().__init__(f"PUBLISH:{reason}")


@dataclass(frozen=True)
class PublishLimits:
    max_reviews: int = 100
    max_comments: int = 3
    max_review_body_chars: int = 4000
    max_comment_body_chars: int = 2000
    max_response_bytes: int = 1024 * 1024
    timeout_seconds: int = 30


@dataclass
class PublishStats:
    get_requests: int = 0
    write_requests: int = 0
    response_bytes: int = 0


@dataclass
class GitHubReviewTransport:
    token: str
    repository: str
    pull_number: int
    opener: OpenerLike | None = None
    limits: PublishLimits = field(default_factory=PublishLimits)
    stats: PublishStats = field(default_factory=PublishStats)

    def __post_init__(self) -> None:
        if not self.token or self.token.strip() != self.token:
            raise GitHubPublishError("TOKEN_INVALID")
        owner, separator, name = self.repository.partition("/")
        if not separator or not re.fullmatch(r"[A-Za-z0-9-]+", owner) or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise GitHubPublishError("REPOSITORY_INVALID")
        if not isinstance(self.pull_number, int) or isinstance(self.pull_number, bool) or self.pull_number < 1:
            raise GitHubPublishError("PULL_NUMBER_INVALID")
        if self.opener is None:
            context = ssl.create_default_context()
            self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))

    @property
    def reviews_path(self) -> str:
        owner, name = self.repository.split("/", 1)
        return f"/repos/{owner}/{name}/pulls/{self.pull_number}/reviews"

    def get_json(self, path: str, *, query: dict[str, int] | None = None) -> Any:
        self._validate_path(path, method="GET")
        if query is not None and query != {"page": 1, "per_page": 100}:
            raise GitHubPublishError("QUERY_NOT_ALLOWED")
        if query is not None and not (path == self.reviews_path or path.endswith("/comments")):
            raise GitHubPublishError("QUERY_NOT_ALLOWED")
        suffix = f"?{urlencode(query)}" if query else ""
        request = self._request(path + suffix, method="GET", body=None)
        raw, has_next = self._open(request, expected_status=200, write=False)
        if has_next:
            raise GitHubPublishError("PAGINATION_LIMIT_EXCEEDED")
        return self._decode(raw)

    def post_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = canonical_json(payload)
        request = self._request(self.reviews_path, method="POST", body=body)
        raw, _ = self._open(request, expected_status=200, write=True)
        result = self._decode(raw, ambiguous=True)
        if not isinstance(result, dict):
            raise GitHubPublishError("RESPONSE_INVALID", ambiguous=True)
        return result

    def _validate_path(self, path: str, *, method: str) -> None:
        owner, name = self.repository.split("/", 1)
        expected_prefix = f"/repos/{owner}/{name}/pulls/{self.pull_number}/reviews"
        if method == "POST":
            if path != expected_prefix:
                raise GitHubPublishError("WRITE_PATH_NOT_ALLOWED")
            return
        if path == expected_prefix:
            return
        match = REVIEW_ID_PATH_RE.fullmatch(path)
        if not match or f"{match.group(1)}/{match.group(2)}" != self.repository or int(match.group(3)) != self.pull_number:
            raise GitHubPublishError("READ_PATH_NOT_ALLOWED")

    def _request(self, path: str, *, method: str, body: bytes | None) -> Request:
        if method not in {"GET", "POST"}:
            raise GitHubPublishError("METHOD_NOT_ALLOWED")
        headers = {
            "Accept": JSON_ACCEPT,
            "Accept-Encoding": "identity",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "open-swe-github-review-agent-phase4",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        return Request(f"https://api.github.com{path}", headers=headers, data=body, method=method)

    def _open(self, request: Request, *, expected_status: int, write: bool) -> tuple[bytes, bool]:
        started_write = False
        try:
            assert self.opener is not None
            if write:
                self.stats.write_requests += 1
                started_write = True
            else:
                self.stats.get_requests += 1
            with self.opener.open(request, timeout=self.limits.timeout_seconds) as response:
                if getattr(response, "status", expected_status) != expected_status:
                    raise GitHubPublishError("HTTP_STATUS", ambiguous=started_write)
                if response.headers.get("Content-Encoding", "identity") not in {"", "identity"}:
                    raise GitHubPublishError("COMPRESSED_RESPONSE", ambiguous=started_write)
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type not in {"application/json", "application/vnd.github+json"}:
                    raise GitHubPublishError("CONTENT_TYPE_MISMATCH", ambiguous=started_write)
                max_bytes = self.limits.max_response_bytes
                declared_text = response.headers.get("Content-Length")
                if declared_text is not None:
                    try:
                        declared = int(declared_text)
                    except ValueError:
                        raise GitHubPublishError("RESPONSE_TOO_LARGE", ambiguous=started_write) from None
                    if declared < 0 or declared > max_bytes:
                        raise GitHubPublishError("RESPONSE_TOO_LARGE", ambiguous=started_write)
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(min(65536, max_bytes + 1 - total))
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise GitHubPublishError("RESPONSE_INVALID", ambiguous=started_write)
                    total += len(chunk)
                    if total > max_bytes:
                        raise GitHubPublishError("RESPONSE_TOO_LARGE", ambiguous=started_write)
                    chunks.append(chunk)
                self.stats.response_bytes += total
                return b"".join(chunks), 'rel="next"' in response.headers.get("Link", "")
        except GitHubPublishError:
            raise
        except (HTTPError, URLError, OSError, TimeoutError):
            raise GitHubPublishError("TRANSPORT_FAILURE", ambiguous=started_write) from None
        except BaseException:
            raise GitHubPublishError("SAFE_TRANSPORT_FAILURE", ambiguous=started_write) from None

    @staticmethod
    def _decode(raw: bytes, *, ambiguous: bool = False) -> Any:
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubPublishError("RESPONSE_INVALID", ambiguous=ambiguous) from None


def review_sha256(review: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(review)).hexdigest()


def marker_id(repository: str, pull_number: int, head_sha: str, review_hash: str) -> str:
    if not SHA_RE.fullmatch(head_sha) or not re.fullmatch(r"[0-9a-f]{64}", review_hash):
        raise GitHubPublishError("MARKER_INPUT_INVALID")
    material = b"\0".join(
        [repository.encode("utf-8"), str(pull_number).encode("ascii"), head_sha.encode("ascii"), review_hash.encode("ascii")]
    )
    return hashlib.sha256(material).hexdigest()


def build_publish_payload(
    review: dict[str, Any],
    snapshot: PullRequestSnapshot,
    *,
    evidence_commit: str,
    review_file_sha256: str | None = None,
    limits: PublishLimits | None = None,
) -> tuple[dict[str, Any], str]:
    active_limits = limits or PublishLimits()
    validate_review(review, snapshot.diff_text)
    if review.get("commit_sha") != snapshot.head_sha or not SHA_RE.fullmatch(evidence_commit):
        raise GitHubPublishError("REVIEW_IDENTITY_MISMATCH")
    confirmed = [item for item in review["findings"] if item["assessment"] == "confirmed"]
    if not 1 <= len(confirmed) <= active_limits.max_comments:
        raise GitHubPublishError("PUBLISHABLE_FINDING_COUNT_INVALID")
    review_hash = review_file_sha256 or review_sha256(review)
    if not re.fullmatch(r"[0-9a-f]{64}", review_hash):
        raise GitHubPublishError("REVIEW_HASH_INVALID")
    marker = marker_id(snapshot.repository, snapshot.pull_number, snapshot.head_sha, review_hash)
    marker_text = f"<!-- open-swe-review-agent:phase4:{marker} -->"
    body = (
        "Experimental automated diff review, explicitly approved by a human before publication.\n\n"
        "Only the supplied diff was reviewed; PR code and tests were not executed. "
        f"Evidence commit: `{evidence_commit}`.\n\n{marker_text}"
    )
    if len(body) > active_limits.max_review_body_chars:
        raise GitHubPublishError("REVIEW_BODY_TOO_LARGE")
    comments: list[dict[str, Any]] = []
    for item in confirmed:
        comment_body = (
            f"**{item['severity']} {item['category']}**\n\n"
            f"{item['evidence']}\n\nRecommendation: {item['recommendation']}"
        )
        if len(comment_body) > active_limits.max_comment_body_chars:
            raise GitHubPublishError("COMMENT_BODY_TOO_LARGE")
        comments.append(
            {
                "path": item["file"],
                "line": item["line"],
                "side": "RIGHT",
                "body": comment_body,
            }
        )
    payload = {
        "commit_id": snapshot.head_sha,
        "body": body,
        "event": "COMMENT",
        "comments": comments,
    }
    validate_publish_payload(payload, snapshot, expected_marker=marker)
    return payload, marker


def validate_publish_payload(
    payload: dict[str, Any],
    snapshot: PullRequestSnapshot,
    *,
    expected_marker: str,
    limits: PublishLimits | None = None,
) -> None:
    active_limits = limits or PublishLimits()
    if set(payload) != {"commit_id", "body", "event", "comments"}:
        raise GitHubPublishError("PAYLOAD_FIELDS_INVALID")
    if payload["commit_id"] != snapshot.head_sha or payload["event"] != "COMMENT":
        raise GitHubPublishError("PAYLOAD_IDENTITY_INVALID")
    body = payload["body"]
    comments = payload["comments"]
    marker_text = f"<!-- open-swe-review-agent:phase4:{expected_marker} -->"
    if not isinstance(body, str) or len(body) > active_limits.max_review_body_chars or body.count(marker_text) != 1:
        raise GitHubPublishError("PAYLOAD_MARKER_INVALID")
    if not isinstance(comments, list) or not 1 <= len(comments) <= active_limits.max_comments:
        raise GitHubPublishError("PAYLOAD_COMMENTS_INVALID")
    anchors = set(snapshot.anchors)
    seen: set[tuple[str, int]] = set()
    for comment in comments:
        if not isinstance(comment, dict) or set(comment) != {"path", "line", "side", "body"}:
            raise GitHubPublishError("PAYLOAD_COMMENT_FIELDS_INVALID")
        anchor = (comment["path"], comment["line"])
        if anchor not in anchors or anchor in seen or comment["side"] != "RIGHT":
            raise GitHubPublishError("PAYLOAD_COMMENT_ANCHOR_INVALID")
        if not isinstance(comment["body"], str) or not comment["body"] or len(comment["body"]) > active_limits.max_comment_body_chars:
            raise GitHubPublishError("PAYLOAD_COMMENT_BODY_INVALID")
        seen.add(anchor)


def find_marker_reviews(reviews: Any, marker: str, *, max_reviews: int = 100) -> list[dict[str, Any]]:
    marker_text = f"<!-- open-swe-review-agent:phase4:{marker} -->"
    if not isinstance(reviews, list) or len(reviews) > max_reviews or any(not isinstance(item, dict) for item in reviews):
        raise GitHubPublishError("REVIEWS_RESPONSE_INVALID")
    return [item for item in reviews if isinstance(item.get("body"), str) and marker_text in item["body"]]


def validate_remote_review(
    review: dict[str, Any],
    comments: Any,
    payload: dict[str, Any],
    *,
    expected_repository: str,
    expected_pull_number: int,
) -> dict[str, Any]:
    review_id = review.get("id")
    html_url = review.get("html_url")
    if (
        not isinstance(review_id, int)
        or isinstance(review_id, bool)
        or review_id < 1
        or not isinstance(html_url, str)
        or html_url
        != f"https://github.com/{expected_repository}/pull/{expected_pull_number}#pullrequestreview-{review_id}"
        or review.get("body") != payload["body"]
        or review.get("commit_id") != payload["commit_id"]
        or review.get("state") != "COMMENTED"
        or not isinstance(review.get("submitted_at"), str)
        or not review["submitted_at"]
    ):
        raise GitHubPublishError("REMOTE_REVIEW_MISMATCH")
    if not isinstance(comments, list) or len(comments) != len(payload["comments"]):
        raise GitHubPublishError("REMOTE_COMMENTS_MISMATCH")
    normalized = []
    for item in comments:
        if not isinstance(item, dict):
            raise GitHubPublishError("REMOTE_COMMENTS_MISMATCH")
        normalized.append(
            {
                "path": item.get("path"),
                "line": item.get("line"),
                "side": item.get("side"),
                "body": item.get("body"),
            }
        )
    if normalized != payload["comments"]:
        raise GitHubPublishError("REMOTE_COMMENTS_MISMATCH")
    return {
        "review_id": review_id,
        "html_url": html_url,
        "state": review["state"],
        "commit_id": review["commit_id"],
        "submitted_at": review.get("submitted_at"),
        "comments_verified": len(normalized),
    }
