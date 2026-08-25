"""Small unified-diff parser used to enforce Open SWE's in-diff finding boundary."""

from __future__ import annotations

import re

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class DiffParseError(ValueError):
    """Raised when a fixture is not a supported unified diff."""


def changed_lines(diff_text: str) -> set[tuple[str, int]]:
    """Return every added or modified candidate-side ``(file, line)`` anchor."""

    current_file: str | None = None
    candidate_line: int | None = None
    anchors: set[tuple[str, int]] = set()

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ "):
            path = raw_line[4:].strip()
            if path == "/dev/null":
                current_file = None
            else:
                current_file = path[2:] if path.startswith("b/") else path
            candidate_line = None
            continue

        match = _HUNK_RE.match(raw_line)
        if match:
            candidate_line = int(match.group(1))
            continue

        if current_file is None or candidate_line is None:
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            anchors.add((current_file, candidate_line))
            candidate_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        elif raw_line.startswith("\\ No newline at end of file"):
            continue
        else:
            candidate_line += 1

    if not anchors:
        raise DiffParseError("diff contains no candidate-side changed lines")
    return anchors
