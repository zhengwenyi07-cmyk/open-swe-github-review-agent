"""Render the frozen structured result into a local-only Markdown review."""

from __future__ import annotations

from typing import Any


def render_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# Local Code Review",
        "",
        f"- Commit: `{review['commit_sha']}`",
        f"- Decision: `{review['decision']}`",
        f"- Tests passed: `{str(review['tests']['passed']).lower()}`",
        "",
        "## Summary",
        "",
        review["summary"],
        "",
        "## Findings",
        "",
    ]
    if "status" in review["tests"]:
        lines.insert(4, f"- Test status: `{review['tests']['status']}`")
    if not review["findings"]:
        lines.append("No confirmed or suggested findings.")
    for index, finding in enumerate(review["findings"], start=1):
        lines.extend(
            [
                f"### {index}. {finding['severity'].upper()} — {finding['category']}",
                "",
                f"- Location: `{finding['file']}:{finding['line']}`",
                f"- Assessment: `{finding['assessment']}`",
                f"- Evidence: {finding['evidence']}",
                f"- Recommendation: {finding['recommendation']}",
                "",
            ]
        )
    lines.extend(["## Uncertainties", ""])
    if not review["uncertainties"]:
        lines.append("None recorded.")
    for item in review["uncertainties"]:
        location = item["file"]
        if item["line"] is not None:
            location += f":{item['line']}"
        lines.extend(
            [
                f"- `{location}` — {item['question']}",
                f"  Evidence needed: {item['evidence_needed']}",
            ]
        )
    lines.extend(["", "## Test Commands", ""])
    if review["tests"]["commands"]:
        lines.extend(f"- `{command}`" for command in review["tests"]["commands"])
    else:
        lines.append("No commands executed in GitHub read-only mode.")
    return "\n".join(lines) + "\n"
