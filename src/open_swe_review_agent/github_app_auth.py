"""Minimal GitHub App installation-token authentication for Phase 4."""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from .github_readonly import JSON_ACCEPT, NoRedirect, OpenerLike, canonical_json

class GitHubAppAuthError(RuntimeError):
    """A fixed-code error that never exposes private-key or token material."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"APP_AUTH:{reason}")


class JwtSigner(Protocol):
    def sign(self, signing_input: bytes, private_key_path: Path) -> bytes: ...


class OpenSSLJwtSigner:
    """Sign RS256 input with the system OpenSSL binary without loading keys in Python."""

    def sign(self, signing_input: bytes, private_key_path: Path) -> bytes:
        try:
            completed = subprocess.run(
                ["openssl", "dgst", "-sha256", "-sign", os.fspath(private_key_path)],
                input=signing_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except BaseException:
            raise GitHubAppAuthError("JWT_SIGNING_FAILED") from None
        if completed.returncode != 0 or not completed.stdout:
            raise GitHubAppAuthError("JWT_SIGNING_FAILED")
        return completed.stdout


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def validate_private_key_path(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise GitHubAppAuthError("PRIVATE_KEY_INVALID")
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        raise GitHubAppAuthError("PRIVATE_KEY_INVALID") from None
    if mode & 0o077:
        raise GitHubAppAuthError("PRIVATE_KEY_PERMISSIONS_TOO_OPEN")
    return path


def create_app_jwt(
    app_id: int,
    private_key_path: Path,
    *,
    signer: JwtSigner | None = None,
    now: int | None = None,
) -> str:
    if not isinstance(app_id, int) or isinstance(app_id, bool) or app_id < 1:
        raise GitHubAppAuthError("APP_ID_INVALID")
    key_path = validate_private_key_path(private_key_path)
    issued = int(time.time()) if now is None else now
    if not isinstance(issued, int) or isinstance(issued, bool) or issued < 1:
        raise GitHubAppAuthError("CLOCK_INVALID")
    header = _b64url(canonical_json({"alg": "RS256", "typ": "JWT"}))
    payload = _b64url(canonical_json({"iat": issued - 60, "exp": issued + 540, "iss": str(app_id)}))
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = (signer or OpenSSLJwtSigner()).sign(signing_input, key_path)
    return f"{header}.{payload}.{_b64url(signature)}"


@dataclass(frozen=True)
class InstallationToken:
    value: str
    expires_at: str
    repository: str


@dataclass
class GitHubAppTokenProvider:
    app_id: int
    installation_id: int
    private_key_path: Path
    repository: str
    pull_requests_permission: str = "write"
    opener: OpenerLike | None = None
    signer: JwtSigner | None = None
    timeout_seconds: int = 30
    request_count: int = 0
    response_bytes: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.installation_id, int) or isinstance(self.installation_id, bool) or self.installation_id < 1:
            raise GitHubAppAuthError("INSTALLATION_ID_INVALID")
        if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", self.repository):
            raise GitHubAppAuthError("REPOSITORY_INVALID")
        if self.pull_requests_permission not in {"read", "write"}:
            raise GitHubAppAuthError("PERMISSION_INVALID")
        if not 1 <= self.timeout_seconds <= 30:
            raise GitHubAppAuthError("TIMEOUT_INVALID")
        validate_private_key_path(self.private_key_path)
        if self.opener is None:
            context = ssl.create_default_context()
            self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))

    def mint(self) -> InstallationToken:
        jwt = create_app_jwt(
            self.app_id,
            self.private_key_path,
            signer=self.signer,
        )
        owner, name = self.repository.split("/", 1)
        body = canonical_json(
            {
                "repositories": [name],
                "permissions": {"pull_requests": self.pull_requests_permission},
            }
        )
        request = Request(
            f"https://api.github.com/app/installations/{self.installation_id}/access_tokens",
            data=body,
            headers={
                "Accept": JSON_ACCEPT,
                "Accept-Encoding": "identity",
                "Authorization": f"Bearer {jwt}",
                "Content-Type": "application/json",
                "User-Agent": "open-swe-github-review-agent-phase4",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="POST",
        )
        raw = self._open(request, 1024 * 1024)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubAppAuthError("TOKEN_RESPONSE_INVALID") from None
        if not isinstance(payload, dict):
            raise GitHubAppAuthError("TOKEN_RESPONSE_INVALID")
        token = payload.get("token")
        expires_at = payload.get("expires_at")
        permissions = payload.get("permissions")
        repositories = payload.get("repositories")
        if (
            not isinstance(token, str)
            or not token
            or token.strip() != token
            or not isinstance(expires_at, str)
            or not expires_at
            or not isinstance(permissions, dict)
            or permissions.get("pull_requests") != self.pull_requests_permission
            or any(key not in {"pull_requests", "metadata"} for key in permissions)
            or ("metadata" in permissions and permissions["metadata"] != "read")
            or not isinstance(repositories, list)
            or len(repositories) != 1
            or not isinstance(repositories[0], dict)
            or repositories[0].get("full_name", "").casefold() != f"{owner}/{name}".casefold()
        ):
            raise GitHubAppAuthError("TOKEN_SCOPE_MISMATCH")
        return InstallationToken(value=token, expires_at=expires_at, repository=self.repository)

    def _open(self, request: Request, max_bytes: int) -> bytes:
        try:
            assert self.opener is not None
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                if getattr(response, "status", 201) != 201:
                    raise GitHubAppAuthError("TOKEN_HTTP_STATUS")
                if response.headers.get("Content-Encoding", "identity") not in {"", "identity"}:
                    raise GitHubAppAuthError("TOKEN_COMPRESSED_RESPONSE")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type not in {"application/json", "application/vnd.github+json"}:
                    raise GitHubAppAuthError("TOKEN_CONTENT_TYPE_MISMATCH")
                declared_text = response.headers.get("Content-Length")
                if declared_text is not None:
                    try:
                        declared = int(declared_text)
                    except ValueError:
                        raise GitHubAppAuthError("TOKEN_RESPONSE_TOO_LARGE") from None
                    if declared < 0 or declared > max_bytes:
                        raise GitHubAppAuthError("TOKEN_RESPONSE_TOO_LARGE")
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(min(65536, max_bytes + 1 - total))
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise GitHubAppAuthError("TOKEN_RESPONSE_INVALID")
                    total += len(chunk)
                    if total > max_bytes:
                        raise GitHubAppAuthError("TOKEN_RESPONSE_TOO_LARGE")
                    chunks.append(chunk)
                self.request_count += 1
                self.response_bytes += total
                return b"".join(chunks)
        except GitHubAppAuthError:
            raise
        except (HTTPError, URLError, OSError, TimeoutError):
            raise GitHubAppAuthError("TOKEN_TRANSPORT_FAILURE") from None
        except BaseException:
            raise GitHubAppAuthError("TOKEN_SAFE_FAILURE") from None
