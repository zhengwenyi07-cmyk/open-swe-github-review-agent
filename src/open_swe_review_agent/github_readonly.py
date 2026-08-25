"""Bounded GitHub Pull Request reader with no write-capable surface."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from .diff_parser import DiffParseError, changed_lines

API_ORIGIN = "https://api.github.com"
JSON_ACCEPT = "application/vnd.github+json"
DIFF_ACCEPT = "application/vnd.github.v3.diff"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}[A-Za-z0-9])?/[A-Za-z0-9._-]+$")
SAFE_PATH_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._@+/-]+$")
DIFF_HEADER_RE = re.compile(r"^diff --git a/([^\s]+) b/([^\s]+)$")


class GitHubReadOnlyError(RuntimeError):
    """A fixed-code error that never retains remote bodies or exception chains."""

    def __init__(self, stage: str, reason: str) -> None:
        self.stage = stage
        self.reason = reason
        super().__init__(f"{stage}:{reason}")


@dataclass(frozen=True)
class ReadLimits:
    max_changed_files: int = 8
    max_metadata_bytes: int = 1024 * 1024
    max_files_bytes: int = 4 * 1024 * 1024
    max_raw_diff_bytes: int = 96 * 1024
    max_single_patch_bytes: int = 32 * 1024
    max_total_diff_lines: int = 2000
    max_candidate_changed_lines: int = 600
    max_pr_title_chars: int = 256
    max_pr_body_chars: int = 4000
    max_prompt_chars: int = 120000
    timeout_seconds: int = 30


@dataclass
class TransportStats:
    request_count: int = 0
    response_bytes: int = 0
    rate_limit_remaining: int | None = None
    last_response_has_next_page: bool = False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class ResponseLike(Protocol):
    headers: Any
    status: int

    def read(self, amount: int = -1) -> bytes: ...

    def __enter__(self) -> "ResponseLike": ...

    def __exit__(self, *args: object) -> None: ...


class OpenerLike(Protocol):
    def open(self, request: Request, timeout: int) -> ResponseLike: ...


@dataclass
class GitHubReadOnlyTransport:
    token: str | None = None
    timeout_seconds: int = 30
    opener: OpenerLike | None = None
    stats: TransportStats = field(default_factory=TransportStats)

    def __post_init__(self) -> None:
        if self.token is not None and (not self.token or self.token.strip() != self.token):
            raise GitHubReadOnlyError("AUTH", "INVALID_TOKEN_SHAPE")
        if not 1 <= self.timeout_seconds <= 30:
            raise GitHubReadOnlyError("HTTP", "INVALID_TIMEOUT")
        if self.opener is None:
            context = ssl.create_default_context()
            self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))

    def get(self, path: str, *, accept: str, query: dict[str, int] | None, max_bytes: int) -> bytes:
        if accept not in {JSON_ACCEPT, DIFF_ACCEPT}:
            raise GitHubReadOnlyError("HTTP", "ACCEPT_NOT_ALLOWED")
        if not re.fullmatch(r"/repos/[A-Za-z0-9-]+/[A-Za-z0-9._-]+/pulls/[1-9][0-9]*(?:/files)?", path):
            raise GitHubReadOnlyError("HTTP", "PATH_NOT_ALLOWED")
        if query is not None:
            if not path.endswith("/files") or set(query) != {"page", "per_page"}:
                raise GitHubReadOnlyError("HTTP", "QUERY_NOT_ALLOWED")
            if query != {"page": 1, "per_page": 100}:
                raise GitHubReadOnlyError("HTTP", "PAGINATION_NOT_ALLOWED")
        suffix = f"?{urlencode(query)}" if query else ""
        url = f"{API_ORIGIN}{path}{suffix}"
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api.github.com" or parsed.port is not None:
            raise GitHubReadOnlyError("HTTP", "ORIGIN_NOT_ALLOWED")
        headers = {
            "Accept": accept,
            "Accept-Encoding": "identity",
            "User-Agent": "open-swe-github-review-agent-phase3",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token is not None:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, headers=headers, method="GET")
        try:
            assert self.opener is not None
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                if getattr(response, "status", 200) != 200:
                    raise GitHubReadOnlyError("HTTP", "HTTP_STATUS")
                encoding = response.headers.get("Content-Encoding", "identity")
                if encoding not in {"", "identity"}:
                    raise GitHubReadOnlyError("HTTP", "COMPRESSED_RESPONSE")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                allowed_types = (
                    {"application/json", "application/vnd.github+json"}
                    if accept == JSON_ACCEPT
                    else {"text/plain", "application/vnd.github.v3.diff"}
                )
                if content_type not in allowed_types:
                    raise GitHubReadOnlyError("HTTP", "CONTENT_TYPE_MISMATCH")
                length_text = response.headers.get("Content-Length")
                if length_text is not None:
                    try:
                        declared = int(length_text)
                    except ValueError:
                        raise GitHubReadOnlyError("HTTP", "INVALID_CONTENT_LENGTH") from None
                    if declared < 0 or declared > max_bytes:
                        raise GitHubReadOnlyError("HTTP", "RESPONSE_TOO_LARGE")
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(min(65536, max_bytes + 1 - total))
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise GitHubReadOnlyError("HTTP", "NON_BYTES_RESPONSE")
                    total += len(chunk)
                    if total > max_bytes:
                        raise GitHubReadOnlyError("HTTP", "RESPONSE_TOO_LARGE")
                    chunks.append(chunk)
                self.stats.request_count += 1
                self.stats.response_bytes += total
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining is not None and remaining.isdigit():
                    self.stats.rate_limit_remaining = int(remaining)
                link = response.headers.get("Link", "")
                self.stats.last_response_has_next_page = 'rel="next"' in link
                return b"".join(chunks)
        except GitHubReadOnlyError:
            raise
        except HTTPError as error:
            reason = "RATE_LIMITED" if error.code in {403, 429} else "HTTP_STATUS"
        except URLError:
            reason = "NETWORK_FAILURE"
        except (OSError, TimeoutError):
            reason = "NETWORK_FAILURE"
        except BaseException:
            reason = "SAFE_TRANSPORT_FAILURE"
        raise GitHubReadOnlyError("HTTP", reason) from None


@dataclass
class GitHubReadOnlyClient:
    transport: GitHubReadOnlyTransport
    limits: ReadLimits = field(default_factory=ReadLimits)

    @staticmethod
    def validate_identity(repository: str, pull_number: int) -> tuple[str, str]:
        if not REPOSITORY_RE.fullmatch(repository) or repository.endswith("."):
            raise GitHubReadOnlyError("IDENTITY", "REPOSITORY_INVALID")
        if not isinstance(pull_number, int) or isinstance(pull_number, bool) or pull_number < 1:
            raise GitHubReadOnlyError("IDENTITY", "PULL_NUMBER_INVALID")
        owner, name = repository.split("/", 1)
        return owner, name

    def metadata(self, repository: str, pull_number: int) -> dict[str, Any]:
        owner, name = self.validate_identity(repository, pull_number)
        data = self.transport.get(
            f"/repos/{owner}/{name}/pulls/{pull_number}",
            accept=JSON_ACCEPT,
            query=None,
            max_bytes=self.limits.max_metadata_bytes,
        )
        return _decode_json_object(data, "METADATA")

    def files(self, repository: str, pull_number: int) -> list[dict[str, Any]]:
        owner, name = self.validate_identity(repository, pull_number)
        data = self.transport.get(
            f"/repos/{owner}/{name}/pulls/{pull_number}/files",
            accept=JSON_ACCEPT,
            query={"page": 1, "per_page": 100},
            max_bytes=self.limits.max_files_bytes,
        )
        payload = _decode_json(data, "FILES")
        if self.transport.stats.last_response_has_next_page:
            raise GitHubReadOnlyError("FILES", "PAGINATION_LIMIT_EXCEEDED")
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise GitHubReadOnlyError("FILES", "FILES_RESPONSE_INVALID")
        return payload

    def diff(self, repository: str, pull_number: int) -> bytes:
        owner, name = self.validate_identity(repository, pull_number)
        return self.transport.get(
            f"/repos/{owner}/{name}/pulls/{pull_number}",
            accept=DIFF_ACCEPT,
            query=None,
            max_bytes=self.limits.max_raw_diff_bytes,
        )


@dataclass(frozen=True)
class PullRequestSnapshot:
    repository: str
    pull_number: int
    base_sha: str
    head_sha: str
    title: str
    body: str
    state: str
    files: tuple[dict[str, Any], ...]
    diff_text: str
    anchors: tuple[tuple[str, int], ...]
    metadata_sha256: str
    files_sha256: str
    diff_sha256: str
    changed_lines_sha256: str

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "pull_number": self.pull_number,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "state": self.state,
            "title": self.title,
            "body": self.body,
            "changed_files": len(self.files),
            "metadata_sha256": self.metadata_sha256,
            "files_sha256": self.files_sha256,
            "diff_sha256": self.diff_sha256,
            "changed_lines_sha256": self.changed_lines_sha256,
        }

    def safe_files(self) -> list[dict[str, Any]]:
        return safe_file_evidence(self.files)


def read_pull_request_snapshot(
    client: GitHubReadOnlyClient, repository: str, pull_number: int
) -> PullRequestSnapshot:
    client.validate_identity(repository, pull_number)
    before = client.metadata(repository, pull_number)
    files = client.files(repository, pull_number)
    raw_diff = client.diff(repository, pull_number)
    after = client.metadata(repository, pull_number)
    before_identity = _metadata_identity(before)
    after_identity = _metadata_identity(after)
    if before_identity != after_identity:
        raise GitHubReadOnlyError("SNAPSHOT", "SNAPSHOT_SHA_DRIFT")
    full_name, number, base_sha, head_sha, state, title, body, metadata_changed_files = before_identity
    if full_name.casefold() != repository.casefold() or number != pull_number:
        raise GitHubReadOnlyError("SNAPSHOT", "PR_IDENTITY_MISMATCH")
    limits = client.limits
    if len(title) > limits.max_pr_title_chars or len(body) > limits.max_pr_body_chars:
        raise GitHubReadOnlyError("SNAPSHOT", "INPUT_BUDGET_EXCEEDED")
    if not 1 <= len(files) <= limits.max_changed_files:
        raise GitHubReadOnlyError("FILES", "INPUT_BUDGET_EXCEEDED")
    if metadata_changed_files != len(files):
        raise GitHubReadOnlyError("SNAPSHOT", "CHANGED_FILES_COUNT_MISMATCH")
    normalized_files = tuple(_validate_file(item, limits) for item in files)
    try:
        diff_text = raw_diff.decode("utf-8")
    except UnicodeDecodeError:
        raise GitHubReadOnlyError("DIFF", "UNSUPPORTED_DIFF") from None
    if len(diff_text.splitlines()) > limits.max_total_diff_lines:
        raise GitHubReadOnlyError("DIFF", "INPUT_BUDGET_EXCEEDED")
    blocks = diff_file_blocks(diff_text)
    header_paths = set(blocks)
    api_paths = {item["filename"] for item in normalized_files}
    if header_paths != api_paths:
        raise GitHubReadOnlyError("DIFF", "PATCH_FILE_SET_MISMATCH")
    for item in normalized_files:
        if item["patch"] not in blocks[item["filename"]]:
            raise GitHubReadOnlyError("DIFF", "PATCH_MISSING_OR_TRUNCATED")
    try:
        anchors = tuple(sorted(changed_lines(diff_text)))
    except DiffParseError:
        raise GitHubReadOnlyError("DIFF", "CHANGED_LINE_PARSE_FAILURE") from None
    if not anchors:
        raise GitHubReadOnlyError("DIFF", "CHANGED_LINE_PARSE_FAILURE")
    if len(anchors) > limits.max_candidate_changed_lines:
        raise GitHubReadOnlyError("DIFF", "INPUT_BUDGET_EXCEEDED")
    prompt_chars = len(title) + len(body) + len(diff_text) + len(repository) + 200
    if prompt_chars > limits.max_prompt_chars:
        raise GitHubReadOnlyError("DIFF", "INPUT_BUDGET_EXCEEDED")
    files_bytes = canonical_json(safe_file_evidence(normalized_files))
    lines_bytes = canonical_json([{"file": path, "line": line} for path, line in anchors])
    metadata_bytes = canonical_json(safe_metadata_evidence(before_identity))
    return PullRequestSnapshot(
        repository=repository,
        pull_number=pull_number,
        base_sha=base_sha,
        head_sha=head_sha,
        title=title,
        body=body,
        state=state,
        files=normalized_files,
        diff_text=diff_text,
        anchors=anchors,
        metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(),
        files_sha256=hashlib.sha256(files_bytes).hexdigest(),
        diff_sha256=hashlib.sha256(raw_diff).hexdigest(),
        changed_lines_sha256=hashlib.sha256(lines_bytes).hexdigest(),
    )


def _decode_json(data: bytes, stage: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GitHubReadOnlyError(stage, "INVALID_JSON") from None


def _decode_json_object(data: bytes, stage: str) -> dict[str, Any]:
    payload = _decode_json(data, stage)
    if not isinstance(payload, dict):
        raise GitHubReadOnlyError(stage, "INVALID_JSON_OBJECT")
    return payload


def _metadata_identity(payload: dict[str, Any]) -> tuple[str, int, str, str, str, str, str, int]:
    try:
        full_name = payload["base"]["repo"]["full_name"]
        number = payload["number"]
        base_sha = payload["base"]["sha"]
        head_sha = payload["head"]["sha"]
        state = payload["state"]
        title = payload["title"]
        body = payload.get("body") or ""
        metadata_changed_files = payload["changed_files"]
    except (KeyError, TypeError):
        raise GitHubReadOnlyError("METADATA", "METADATA_FIELDS_MISSING") from None
    if (
        not isinstance(full_name, str)
        or not isinstance(number, int)
        or isinstance(number, bool)
        or not isinstance(state, str)
        or not isinstance(title, str)
        or not isinstance(body, str)
        or not isinstance(metadata_changed_files, int)
        or isinstance(metadata_changed_files, bool)
        or metadata_changed_files < 1
        or not SHA_RE.fullmatch(str(base_sha))
        or not SHA_RE.fullmatch(str(head_sha))
    ):
        raise GitHubReadOnlyError("METADATA", "METADATA_FIELDS_INVALID")
    return full_name, number, str(base_sha), str(head_sha), state, title, body, metadata_changed_files


def _validate_file(item: dict[str, Any], limits: ReadLimits) -> dict[str, Any]:
    required = {"filename", "status", "additions", "deletions", "changes", "patch"}
    if not required.issubset(item):
        raise GitHubReadOnlyError("FILES", "PATCH_MISSING_OR_TRUNCATED")
    filename = item["filename"]
    status = item["status"]
    patch = item["patch"]
    counts = (item["additions"], item["deletions"], item["changes"])
    if not isinstance(filename, str) or not SAFE_PATH_RE.fullmatch(filename):
        raise GitHubReadOnlyError("FILES", "UNSUPPORTED_DIFF")
    if status not in {"added", "modified", "removed"}:
        raise GitHubReadOnlyError("FILES", "UNSUPPORTED_DIFF")
    if not isinstance(patch, str) or not patch or len(patch.encode("utf-8")) > limits.max_single_patch_bytes:
        raise GitHubReadOnlyError("FILES", "PATCH_MISSING_OR_TRUNCATED")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts):
        raise GitHubReadOnlyError("FILES", "FILES_RESPONSE_INVALID")
    return {
        "filename": filename,
        "status": status,
        "additions": counts[0],
        "deletions": counts[1],
        "changes": counts[2],
        "patch": patch,
    }


def diff_file_blocks(diff_text: str) -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            match = DIFF_HEADER_RE.fullmatch(line.rstrip("\r\n"))
            if not match or match.group(1) != match.group(2):
                raise GitHubReadOnlyError("DIFF", "UNSUPPORTED_DIFF")
            current = match.group(2)
            if not SAFE_PATH_RE.fullmatch(current) or current in blocks:
                raise GitHubReadOnlyError("DIFF", "UNSUPPORTED_DIFF")
            blocks[current] = []
        if current is not None:
            blocks[current].append(line)
    if not blocks:
        raise GitHubReadOnlyError("DIFF", "UNSUPPORTED_DIFF")
    return {path: "".join(lines) for path, lines in blocks.items()}


def canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def safe_metadata_evidence(
    identity: tuple[str, int, str, str, str, str, str, int]
) -> dict[str, Any]:
    full_name, number, base_sha, head_sha, state, title, body, changed_file_count = identity
    return {
        "repository": full_name,
        "pull_number": number,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "state": state,
        "title": title,
        "body": body,
        "changed_files": changed_file_count,
    }


def safe_file_evidence(files: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "filename": item["filename"],
            "status": item["status"],
            "additions": item["additions"],
            "deletions": item["deletions"],
            "changes": item["changes"],
            "patch_sha256": hashlib.sha256(item["patch"].encode("utf-8")).hexdigest(),
        }
        for item in files
    ]
