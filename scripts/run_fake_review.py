#!/usr/bin/env python3
"""Run the deterministic Phase 1 review without network or external services."""

from __future__ import annotations

import json
from pathlib import Path

from open_swe_review_agent.fakes import FakeModel, FakeSandbox
from open_swe_review_agent.render import render_markdown
from open_swe_review_agent.workflow import ReviewRequest, ReviewWorkflow

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures" / "phase1_logic_error"
OUTPUT_DIR = ROOT / "artifacts" / "fake_review"


def main() -> int:
    fixture = json.loads((FIXTURE_DIR / "fixture.json").read_text(encoding="utf-8"))
    diff_text = (FIXTURE_DIR / "diff.patch").read_text(encoding="utf-8")
    expected = fixture["expected_primary_finding"]
    model = FakeModel(
        {
            "summary": "The changed zero-denominator branch raises instead of returning the documented sentinel.",
            "findings": [
                {
                    "file": expected["file"],
                    "line": expected["line"],
                    "severity": expected["severity"],
                    "category": expected["category"],
                    "assessment": "confirmed",
                    "evidence": "The changed branch raises ZeroDivisionError when denominator is zero.",
                    "recommendation": "Restore the documented zero-denominator return behavior.",
                }
            ],
            "uncertainties": [],
            "decision": "REQUEST_CHANGES",
        }
    )
    sandbox = FakeSandbox(
        diff_text=diff_text,
        expected_base=fixture["base_commit"],
        expected_candidate=fixture["candidate_commit"],
        test_returncodes={fixture["test_commands"][0]: 1},
    )
    request = ReviewRequest(
        repository=fixture["repository"],
        base_commit=fixture["base_commit"],
        candidate_commit=fixture["candidate_commit"],
        test_commands=tuple(fixture["test_commands"]),
    )
    result = ReviewWorkflow(model=model, sandbox=sandbox).run(request)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "review.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "review.md").write_text(render_markdown(result), encoding="utf-8")
    print(f"PASS fake-review findings={len(result['findings'])} output={OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
