"""Schema loading plus semantic checks that JSON Schema alone cannot express."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .diff_parser import changed_lines


class ReviewContractError(ValueError):
    """Raised when model output violates the frozen review contract."""


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_schema(root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    return json.loads((base / "schemas" / "review.schema.json").read_text(encoding="utf-8"))


def validate_review(review: dict[str, Any], diff_text: str, root: Path | None = None) -> None:
    validator = Draft202012Validator(load_schema(root))
    errors = sorted(validator.iter_errors(review), key=lambda error: list(error.path))
    if errors:
        raise ReviewContractError(errors[0].message)

    anchors = changed_lines(diff_text)
    fingerprints: set[tuple[str, int, str]] = set()
    for finding in review["findings"]:
        anchor = (finding["file"], finding["line"])
        if anchor not in anchors:
            raise ReviewContractError(f"finding is outside the changed diff: {anchor!r}")
        fingerprint = (
            finding["file"],
            finding["line"],
            " ".join(finding["evidence"].casefold().split()),
        )
        if fingerprint in fingerprints:
            raise ReviewContractError("duplicate finding")
        fingerprints.add(fingerprint)

    if review["decision"] == "APPROVE" and review["findings"]:
        raise ReviewContractError("APPROVE cannot contain findings")
    if review["decision"] == "REQUEST_CHANGES" and not any(
        item["assessment"] == "confirmed" and item["severity"] in {"high", "critical"}
        for item in review["findings"]
    ):
        raise ReviewContractError("REQUEST_CHANGES requires a confirmed high/critical finding")
