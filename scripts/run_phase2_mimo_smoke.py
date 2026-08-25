#!/usr/bin/env python3
"""Run the frozen three-task Phase 2 MiMo review smoke once."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from open_swe_review_agent.contracts import validate_review
from open_swe_review_agent.local_git_sandbox import LocalGitSandbox
from open_swe_review_agent.mimo import MIMO_MODEL, create_mimo_model
from open_swe_review_agent.open_swe_adapter import OpenSWECompatibleReviewModel
from open_swe_review_agent.render import render_markdown
from open_swe_review_agent.workflow import ReviewRequest

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "artifacts" / "mimo_preflight.json"
OUTPUT_DIR = ROOT / "artifacts" / "phase2"
SCORING_PATH = ROOT / "fixtures" / "phase2_scoring.json"
ACK = "OPEN_SWE_PHASE2_THREE_TASK_SMOKE"
UPSTREAM_COMMIT = "daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc"
ADAPTER_KIND = "OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE"
SEVERITY_VALUE = {"low": 1, "medium": 2, "high": 3, "critical": 4}
FAILURE_REASON_BY_STAGE = {
    "LOCAL_FIXTURE": {"LOCAL_FIXTURE_FAILURE"},
    "MODEL_CLIENT": {"MODEL_CLIENT_CONSTRUCTION_FAILURE"},
    "MODEL_RESPONSE": {
        "MODEL_IDENTITY_MISMATCH",
        "FINISH_REASON_MISMATCH",
        "TOOL_CALL_COUNT_MISMATCH",
        "TOOL_CALL_SEMANTICS_MISMATCH",
        "MODEL_API_OR_RESPONSE_FAILURE",
    },
    "TEST_EXECUTION": {"TEST_EXECUTION_FAILURE"},
    "REVIEW_VALIDATION": {"REVIEW_CONTRACT_FAILURE"},
    "EVIDENCE_WRITE": {"EVIDENCE_WRITE_FAILURE"},
}


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    fixture_dir: Path
    repository: Path


TASKS = (
    TaskSpec(
        task_id="logic_error",
        fixture_dir=ROOT / "fixtures" / "phase1_logic_error",
        repository=ROOT / ".fixtures" / "phase1_repo",
    ),
    TaskSpec(
        task_id="boundary_error",
        fixture_dir=ROOT / "fixtures" / "phase2_boundary_error",
        repository=ROOT / ".fixtures" / "phase2_boundary_repo",
    ),
    TaskSpec(
        task_id="permission_error",
        fixture_dir=ROOT / "fixtures" / "phase2_permission_error",
        repository=ROOT / ".fixtures" / "phase2_permission_repo",
    ),
)


def run(*args: str, cwd: Path = ROOT) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_fixture(spec: TaskSpec) -> dict[str, Any]:
    fixture_path = spec.fixture_dir / "fixture.json"
    diff_path = spec.fixture_dir / "diff.patch"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    required = {
        "fixture_id",
        "repository",
        "base_commit",
        "candidate_commit",
        "diff_sha256",
        "test_commands",
        "expected_primary_finding",
    }
    if not required.issubset(fixture):
        raise RuntimeError(f"{spec.task_id}: FIXTURE_FIELDS_MISSING")
    if sha256(diff_path) != fixture["diff_sha256"]:
        raise RuntimeError(f"{spec.task_id}: FIXTURE_DIFF_HASH_MISMATCH")
    expected = fixture["expected_primary_finding"]
    if set(expected) != {"file", "line", "category", "severity"}:
        raise RuntimeError(f"{spec.task_id}: EXPECTED_FINDING_INVALID")
    if expected["severity"] not in SEVERITY_VALUE:
        raise RuntimeError(f"{spec.task_id}: EXPECTED_SEVERITY_INVALID")
    if not isinstance(fixture["test_commands"], list) or len(fixture["test_commands"]) != 1:
        raise RuntimeError(f"{spec.task_id}: TEST_COMMAND_INVALID")
    return fixture


def load_scoring_rubric() -> dict[str, dict[str, Any]]:
    payload = json.loads(SCORING_PATH.read_text(encoding="utf-8"))
    if set(payload) != {"version", "tasks"} or payload["version"] != "phase2_scoring_v1":
        raise RuntimeError("SCORING_RUBRIC_INVALID")
    rubrics: dict[str, dict[str, Any]] = {}
    expected_fields = {
        "fixture_id",
        "file",
        "line",
        "category",
        "severity",
        "semantic_evidence_all_of_any",
    }
    for item in payload["tasks"]:
        if set(item) != expected_fields or item["fixture_id"] in rubrics:
            raise RuntimeError("SCORING_RUBRIC_INVALID")
        if item["severity"] not in SEVERITY_VALUE:
            raise RuntimeError("SCORING_RUBRIC_INVALID")
        groups = item["semantic_evidence_all_of_any"]
        if (
            not isinstance(groups, list)
            or not groups
            or any(
                not isinstance(group, list)
                or not group
                or any(not isinstance(term, str) or not term.strip() for term in group)
                for group in groups
            )
        ):
            raise RuntimeError("SCORING_RUBRIC_INVALID")
        rubrics[item["fixture_id"]] = item
    if set(rubrics) != {load_fixture(spec)["fixture_id"] for spec in TASKS}:
        raise RuntimeError("SCORING_RUBRIC_TASK_SET_MISMATCH")
    for spec in TASKS:
        fixture = load_fixture(spec)
        rubric = rubrics[fixture["fixture_id"]]
        expected = fixture["expected_primary_finding"]
        if any(rubric[key] != expected[key] for key in ("file", "line", "category", "severity")):
            raise RuntimeError("SCORING_RUBRIC_FIXTURE_IDENTITY_MISMATCH")
    return rubrics


def materialize_all() -> None:
    run(str(ROOT / ".venv" / "bin" / "python"), "scripts/materialize_phase1_fixture.py")
    run(str(ROOT / ".venv" / "bin" / "python"), "scripts/materialize_phase2_fixtures.py", "--check")


def load_preflight() -> dict[str, Any]:
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
    return evidence


def ensure_clean_committed_contract() -> str:
    if run("git", "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("WORKTREE_NOT_CLEAN")
    required = (
        "scripts/run_phase2_mimo_smoke.py",
        "scripts/materialize_phase2_fixtures.py",
        "tests/test_phase2_mimo_smoke.py",
        "fixtures/phase1_logic_error/fixture.json",
        "fixtures/phase1_logic_error/diff.patch",
        "fixtures/phase2_boundary_error/fixture.json",
        "fixtures/phase2_boundary_error/diff.patch",
        "fixtures/phase2_permission_error/fixture.json",
        "fixtures/phase2_permission_error/diff.patch",
        "fixtures/phase2_scoring.json",
        "src/open_swe_review_agent/open_swe_adapter.py",
        "src/open_swe_review_agent/local_git_sandbox.py",
        "schemas/review.schema.json",
        "docs/phases/phase-02-three-task-smoke/PLAN.md",
        "docs/phases/phase-02-three-task-smoke/CONCEPTS.md",
        "docs/phases/phase-02-three-task-smoke/RESULTS.md",
    )
    run("git", "ls-files", "--error-unmatch", "--", *required)
    return run("git", "rev-parse", "HEAD")


def matches_primary(finding: dict[str, Any], rubric: dict[str, Any]) -> bool:
    evidence = f"{finding.get('evidence', '')} {finding.get('recommendation', '')}".casefold()
    semantic_match = all(
        any(term.casefold() in evidence for term in group)
        for group in rubric["semantic_evidence_all_of_any"]
    )
    return (
        finding.get("file") == rubric["file"]
        and finding.get("line") == rubric["line"]
        and finding.get("category") == rubric["category"]
        and finding.get("assessment") == "confirmed"
        and semantic_match
    )


def score_reviews(
    records: list[tuple[dict[str, Any], dict[str, Any]]],
    *,
    total_task_count: int | None = None,
) -> dict[str, Any]:
    rubrics = load_scoring_rubric()
    total_findings = 0
    correct_findings = 0
    false_findings = 0
    duplicate_findings = 0
    file_anchors = 0
    line_anchors = 0
    severity_errors: list[int] = []
    overestimate_magnitudes: list[int] = []
    underestimate_magnitudes: list[int] = []
    overestimates = 0
    underestimates = 0
    exact_severity = 0
    per_task: list[dict[str, Any]] = []

    for fixture, review in records:
        rubric = rubrics[fixture["fixture_id"]]
        findings = review["findings"]
        total_findings += len(findings)
        file_anchors += sum(item.get("file") == rubric["file"] for item in findings)
        line_anchors += sum(
            item.get("file") == rubric["file"] and item.get("line") == rubric["line"]
            for item in findings
        )
        matches = [item for item in findings if matches_primary(item, rubric)]
        found = bool(matches)
        if found:
            correct_findings += 1
            duplicate_findings += max(0, len(matches) - 1)
            predicted = matches[0]["severity"]
            error = SEVERITY_VALUE[predicted] - SEVERITY_VALUE[rubric["severity"]]
            severity_errors.append(abs(error))
            exact_severity += error == 0
            overestimates += error > 0
            underestimates += error < 0
            if error > 0:
                overestimate_magnitudes.append(error)
            elif error < 0:
                underestimate_magnitudes.append(abs(error))
        else:
            predicted = None
        false_findings += len(findings) - len(matches)
        per_task.append(
            {
                "fixture_id": fixture["fixture_id"],
                "semantic_rubric_match": found,
                "finding_count": len(findings),
                "false_findings": len(findings) - len(matches),
                "duplicate_findings": max(0, len(matches) - 1),
                "predicted_severity": predicted,
                "expected_severity": rubric["severity"],
                "decision": review["decision"],
            }
        )

    task_count = total_task_count if total_task_count is not None else len(records)
    if task_count < len(records):
        raise ValueError("total_task_count cannot be smaller than completed records")
    severity_count = len(severity_errors)
    return {
        "task_count": task_count,
        "semantic_rubric_recall": {
            "found": correct_findings,
            "total": task_count,
            "rate": correct_findings / task_count if task_count else 0.0,
        },
        "semantic_rubric_precision": {
            "correct": correct_findings,
            "total": total_findings,
            "rate": correct_findings / total_findings if total_findings else 0.0,
        },
        "file_anchor_accuracy": file_anchors / total_findings if total_findings else 0.0,
        "line_anchor_accuracy": line_anchors / total_findings if total_findings else 0.0,
        "false_findings": false_findings,
        "duplicate_findings": duplicate_findings,
        "uncertainty_count": sum(len(review["uncertainties"]) for _, review in records),
        "severity_calibration": {
            "matched_findings": severity_count,
            "exact_matches": exact_severity,
            "exact_match_rate": exact_severity / severity_count if severity_count else 0.0,
            "mean_absolute_error": (
                sum(severity_errors) / severity_count if severity_count else None
            ),
            "overestimation_count": overestimates,
            "mean_overestimation_magnitude": (
                sum(overestimate_magnitudes) / len(overestimate_magnitudes)
                if overestimate_magnitudes
                else None
            ),
            "underestimation_count": underestimates,
            "mean_underestimation_magnitude": (
                sum(underestimate_magnitudes) / len(underestimate_magnitudes)
                if underestimate_magnitudes
                else None
            ),
        },
        "tasks": per_task,
    }


def model_response_failure_reason(error: Exception) -> str:
    fixed_messages = {
        "MiMo response model identity mismatch": "MODEL_IDENTITY_MISMATCH",
        "MiMo response finish reason mismatch": "FINISH_REASON_MISMATCH",
        "expected exactly one structured review tool call": "TOOL_CALL_COUNT_MISMATCH",
        "structured review tool call has invalid semantics": "TOOL_CALL_SEMANTICS_MISMATCH",
    }
    return fixed_messages.get(str(error), "MODEL_API_OR_RESPONSE_FAILURE")


def write_task_failure(
    *,
    spec: TaskSpec,
    fixture: dict[str, Any],
    contract_commit: str,
    stage: str,
    reason: str,
    model: OpenSWECompatibleReviewModel | None,
) -> None:
    if stage not in FAILURE_REASON_BY_STAGE or reason not in FAILURE_REASON_BY_STAGE[stage]:
        raise RuntimeError("UNSAFE_FAILURE_CLASSIFICATION")
    usage = model.usage if model is not None else {}
    failure = {
        "status": "FAILED",
        "task_id": spec.task_id,
        "fixture_id": fixture["fixture_id"],
        "contract_commit": contract_commit,
        "failure_stage": stage,
        "failure_reason": reason,
        "model": MIMO_MODEL,
        "model_calls": model.calls if model is not None else 0,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "github_api_called": False,
        "github_write_performed": False,
    }
    atomic_json(OUTPUT_DIR / spec.task_id / "failure.json", failure)
    print(f"RUN_FAILED task={spec.task_id} stage={stage} reason={reason}")


def load_task_evidence(spec: TaskSpec) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    fixture = load_fixture(spec)
    task_dir = OUTPUT_DIR / spec.task_id
    review = json.loads((task_dir / "review.json").read_text(encoding="utf-8"))
    diff_text = (spec.fixture_dir / "diff.patch").read_text(encoding="utf-8")
    validate_review(review, diff_text)
    if (task_dir / "review.md").read_text(encoding="utf-8") != render_markdown(review):
        raise RuntimeError(f"{spec.task_id}: REVIEW_MARKDOWN_MISMATCH")
    summary = json.loads((task_dir / "run_summary.json").read_text(encoding="utf-8"))
    required = {
        "status": "PASS",
        "adapter_kind": ADAPTER_KIND,
        "model": MIMO_MODEL,
        "response_model": MIMO_MODEL,
        "finish_reason": "tool_calls",
        "schema_valid": True,
        "github_api_called": False,
        "github_write_performed": False,
    }
    if any(summary.get(key) != value for key, value in required.items()):
        raise RuntimeError(f"{spec.task_id}: RUN_SUMMARY_INVALID")
    if summary.get("fixture_id") != fixture["fixture_id"] or summary.get("model_calls") != 1:
        raise RuntimeError(f"{spec.task_id}: RUN_SUMMARY_INVALID")
    if not isinstance(summary.get("test_returncode"), int):
        raise RuntimeError(f"{spec.task_id}: TEST_EXECUTION_MISSING")
    contract_commit = summary.get("contract_commit")
    if not isinstance(contract_commit, str) or re.fullmatch(r"[0-9a-f]{40}", contract_commit) is None:
        raise RuntimeError(f"{spec.task_id}: CONTRACT_COMMIT_INVALID")
    return fixture, review, summary


def load_task_failure(spec: TaskSpec) -> dict[str, Any]:
    path = OUTPUT_DIR / spec.task_id / "failure.json"
    failure = json.loads(path.read_text(encoding="utf-8"))
    expected_fields = {
        "status",
        "task_id",
        "fixture_id",
        "contract_commit",
        "failure_stage",
        "failure_reason",
        "model",
        "model_calls",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "github_api_called",
        "github_write_performed",
    }
    if set(failure) != expected_fields:
        raise RuntimeError(f"{spec.task_id}: FAILURE_EVIDENCE_FIELDS_INVALID")
    if (
        failure["status"] != "FAILED"
        or failure["task_id"] != spec.task_id
        or failure["fixture_id"] != load_fixture(spec)["fixture_id"]
        or failure["failure_stage"] not in FAILURE_REASON_BY_STAGE
        or failure["failure_reason"] not in FAILURE_REASON_BY_STAGE[failure["failure_stage"]]
        or failure["model"] != MIMO_MODEL
        or not isinstance(failure["model_calls"], int)
        or failure["model_calls"] not in {0, 1}
        or failure["github_api_called"] is not False
        or failure["github_write_performed"] is not False
    ):
        raise RuntimeError(f"{spec.task_id}: FAILURE_EVIDENCE_INVALID")
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        if failure[key] is not None and not isinstance(failure[key], int):
            raise RuntimeError(f"{spec.task_id}: FAILURE_EVIDENCE_INVALID")
    commit = failure["contract_commit"]
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise RuntimeError(f"{spec.task_id}: FAILURE_CONTRACT_COMMIT_INVALID")
    return failure


def task_evidence_kind(spec: TaskSpec) -> str | None:
    task_dir = OUTPUT_DIR / spec.task_id
    success_files = [task_dir / "review.json", task_dir / "review.md", task_dir / "run_summary.json"]
    success_count = sum(path.is_file() for path in success_files)
    failure_exists = (task_dir / "failure.json").is_file()
    if success_count == 3 and not failure_exists:
        return "SUCCESS"
    if success_count == 0 and failure_exists:
        return "FAILED"
    if success_count == 0 and not failure_exists:
        return None
    raise RuntimeError(f"{spec.task_id}: INCONSISTENT_TASK_EVIDENCE")


def build_summary(contract_commit: str) -> dict[str, Any]:
    successes: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    failures: list[dict[str, Any]] = []
    for spec in TASKS:
        kind = task_evidence_kind(spec)
        if kind == "SUCCESS":
            successes.append(load_task_evidence(spec))
        elif kind == "FAILED":
            failures.append(load_task_failure(spec))
        else:
            raise RuntimeError("PHASE2_TASK_EVIDENCE_MISSING")
    evidence_commits = {
        *[summary["contract_commit"] for _, _, summary in successes],
        *[failure["contract_commit"] for failure in failures],
    }
    if evidence_commits != {contract_commit}:
        raise RuntimeError("PHASE2_CONTRACT_COMMIT_MISMATCH")
    score = score_reviews(
        [(fixture, review) for fixture, review, _ in successes],
        total_task_count=len(TASKS),
    )
    all_summaries: list[dict[str, Any]] = [summary for _, _, summary in successes] + failures
    input_tokens = sum(int(summary.get("input_tokens") or 0) for summary in all_summaries)
    output_tokens = sum(int(summary.get("output_tokens") or 0) for summary in all_summaries)
    total_tokens = sum(int(summary.get("total_tokens") or 0) for summary in all_summaries)
    elapsed = round(sum(float(summary["elapsed_seconds"]) for _, _, summary in successes), 3)
    return {
        "status": "PASS" if not failures else "COMPLETED_WITH_FAILURES",
        "phase": "PHASE_2_THREE_TASK_SMOKE",
        "contract_commit": contract_commit,
        "upstream_commit": UPSTREAM_COMMIT,
        "configured_model": MIMO_MODEL,
        "adapter_kind": ADAPTER_KIND,
        "successful_reviews": len(successes),
        "failed_reviews": len(failures),
        "schema_valid_rate": len(successes) / len(TASKS),
        "test_execution_rate": len(successes) / len(TASKS),
        "model_calls": sum(int(summary.get("model_calls") or 0) for summary in all_summaries),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "elapsed_seconds": elapsed,
        "automatic_retries": 0,
        "cost": None,
        "github_api_called": False,
        "github_write_performed": False,
        "test_split_status": "NOT_APPLICABLE",
        "quality": score,
        "human_evaluation": {
            "status": "PENDING_HUMAN_REVIEW",
            "core_bug_recall": None,
            "finding_precision": None,
            "severity_calibration_accepted": None,
        },
        "next_step": "HUMAN_REVIEW_REQUIRED",
    }


def execute(acknowledgement: str) -> None:
    if acknowledgement != ACK:
        raise RuntimeError("ACKNOWLEDGEMENT_REQUIRED")
    if os.environ.get("OPEN_SWE_PHASE2_ALLOW_NETWORK") != "YES_ONCE":
        raise RuntimeError("NETWORK_GATE_REQUIRED")
    if os.environ.get("MIMO_ACCOUNT_TYPE") != "PAY_AS_YOU_GO":
        raise RuntimeError("ACCOUNT_TYPE_MISMATCH")
    if OUTPUT_DIR.exists():
        raise RuntimeError("PHASE2_OUTPUT_ALREADY_EXISTS")
    contract_commit = ensure_clean_committed_contract()
    load_preflight()
    api_key = os.environ.get("MIMO_API_KEY", "")
    materialize_all()

    for spec in TASKS:
        fixture = load_fixture(spec)
        task_dir = OUTPUT_DIR / spec.task_id
        model: OpenSWECompatibleReviewModel | None = None
        try:
            sandbox = LocalGitSandbox(
                repository=spec.repository,
                allowed_test_commands=frozenset(fixture["test_commands"]),
            )
            request = ReviewRequest(
                repository=str(fixture["repository"]),
                base_commit=str(fixture["base_commit"]),
                candidate_commit=str(fixture["candidate_commit"]),
                test_commands=tuple(fixture["test_commands"]),
            )
            actual_diff = sandbox.read_diff(
                base_commit=request.base_commit,
                candidate_commit=request.candidate_commit,
            )
            if actual_diff != (spec.fixture_dir / "diff.patch").read_text(encoding="utf-8"):
                raise RuntimeError("MATERIALIZED_FIXTURE_DIFF_MISMATCH")
        except Exception:
            write_task_failure(
                spec=spec,
                fixture=fixture,
                contract_commit=contract_commit,
                stage="LOCAL_FIXTURE",
                reason="LOCAL_FIXTURE_FAILURE",
                model=None,
            )
            continue

        try:
            model = OpenSWECompatibleReviewModel(create_mimo_model(api_key))
        except Exception:
            write_task_failure(
                spec=spec,
                fixture=fixture,
                contract_commit=contract_commit,
                stage="MODEL_CLIENT",
                reason="MODEL_CLIENT_CONSTRUCTION_FAILURE",
                model=None,
            )
            continue

        started = time.monotonic()
        try:
            candidate = model.review(request=request, diff_text=actual_diff)
        except Exception as error:
            reason = model_response_failure_reason(error)
            write_task_failure(
                spec=spec,
                fixture=fixture,
                contract_commit=contract_commit,
                stage="MODEL_RESPONSE",
                reason=reason,
                model=model,
            )
            continue

        try:
            tests = sandbox.run_tests(request.test_commands)
        except Exception:
            write_task_failure(
                spec=spec,
                fixture=fixture,
                contract_commit=contract_commit,
                stage="TEST_EXECUTION",
                reason="TEST_EXECUTION_FAILURE",
                model=model,
            )
            continue

        try:
            review = dict(candidate)
            review["commit_sha"] = request.candidate_commit
            review["tests"] = {
                "commands": [item.command for item in tests],
                "passed": bool(tests) and all(item.returncode == 0 for item in tests),
            }
            validate_review(review, actual_diff)
            markdown = render_markdown(review)
        except Exception:
            write_task_failure(
                spec=spec,
                fixture=fixture,
                contract_commit=contract_commit,
                stage="REVIEW_VALIDATION",
                reason="REVIEW_CONTRACT_FAILURE",
                model=model,
            )
            continue

        elapsed = time.monotonic() - started
        test_returncode = tests[0].returncode if tests else None
        run_summary = {
            "status": "PASS",
            "task_id": spec.task_id,
            "fixture_id": fixture["fixture_id"],
            "adapter_kind": ADAPTER_KIND,
            "contract_commit": contract_commit,
            "upstream_commit": UPSTREAM_COMMIT,
            "model": MIMO_MODEL,
            "response_model": model.response_model,
            "finish_reason": model.finish_reason,
            "model_calls": model.calls,
            **model.usage,
            "elapsed_seconds": round(elapsed, 3),
            "test_returncode": test_returncode,
            "schema_valid": True,
            "github_api_called": False,
            "github_write_performed": False,
        }
        try:
            atomic_json(task_dir / "review.json", review)
            atomic_text(task_dir / "review.md", markdown)
            atomic_json(task_dir / "run_summary.json", run_summary)
            print(f"RUN_COMPLETED task={spec.task_id}")
        except Exception:
            for path in (task_dir / "review.json", task_dir / "review.md", task_dir / "run_summary.json"):
                path.unlink(missing_ok=True)
            write_task_failure(
                spec=spec,
                fixture=fixture,
                contract_commit=contract_commit,
                stage="EVIDENCE_WRITE",
                reason="EVIDENCE_WRITE_FAILURE",
                model=model,
            )
            continue

    atomic_json(OUTPUT_DIR / "summary.json", build_summary(contract_commit))


def check() -> None:
    materialize_all()
    for spec in TASKS:
        load_fixture(spec)
    load_scoring_rubric()
    load_preflight()
    kinds = [(spec, task_evidence_kind(spec)) for spec in TASKS]
    present = [(spec, kind) for spec, kind in kinds if kind is not None]
    if not present:
        smoke = "NOT_RUN"
    elif len(present) != len(TASKS):
        for spec, kind in present:
            load_task_evidence(spec) if kind == "SUCCESS" else load_task_failure(spec)
        smoke = f"PARTIAL_{len(present)}_OF_{len(TASKS)}"
    else:
        saved = json.loads((OUTPUT_DIR / "summary.json").read_text(encoding="utf-8"))
        expected = build_summary(str(saved.get("contract_commit")))
        if saved != expected:
            raise RuntimeError("PHASE2_SUMMARY_MISMATCH")
        smoke = str(saved["status"])
    print(
        f"VALID phase2-smoke model={MIMO_MODEL} tasks={len(TASKS)} "
        f"smoke={smoke} github_write=false"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run-smoke", action="store_true")
    parser.add_argument("--acknowledgement", default="")
    args = parser.parse_args()
    if args.check == args.run_smoke:
        parser.error("choose exactly one of --check or --run-smoke")
    if args.check:
        check()
        return 0
    execute(args.acknowledgement)
    summary = json.loads((OUTPUT_DIR / "summary.json").read_text(encoding="utf-8"))
    print(
        f"COMPLETED phase2-smoke status={summary['status']} "
        f"output={OUTPUT_DIR} next=HUMAN_REVIEW_REQUIRED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
