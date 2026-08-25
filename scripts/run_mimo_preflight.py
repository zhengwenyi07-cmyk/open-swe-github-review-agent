#!/usr/bin/env python3
"""Non-benchmark MiMo tool-call preflight. Network execution is explicit."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from open_swe_review_agent.mimo import MIMO_BASE_URL, MIMO_MODEL, MimoConfig, create_mimo_model

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "mimo_preflight.json"
ACK = "OPEN_SWE_PHASE1_MIMO_PREFLIGHT"

TOOL = {
    "name": "record_preflight_status",
    "description": "Record the single expected preflight status.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["status"],
        "properties": {"status": {"const": "READY"}},
    },
}


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def execute(acknowledgement: str) -> None:
    if acknowledgement != ACK:
        raise RuntimeError("ACKNOWLEDGEMENT_REQUIRED")
    if os.environ.get("OPEN_SWE_MIMO_ALLOW_NETWORK") != "YES_ONCE":
        raise RuntimeError("NETWORK_GATE_REQUIRED")
    if os.environ.get("MIMO_ACCOUNT_TYPE") != "PAY_AS_YOU_GO":
        raise RuntimeError("ACCOUNT_TYPE_MISMATCH")
    if OUTPUT.exists():
        raise RuntimeError("PREFLIGHT_ALREADY_EXISTS")

    api_key = os.environ.get("MIMO_API_KEY", "")
    model = create_mimo_model(api_key)
    bound = model.bind_tools([TOOL], tool_choice="record_preflight_status", parallel_tool_calls=False)
    response = bound.invoke(
        [
            ("system", "Return exactly one required tool call and no prose."),
            ("human", "Record the preflight status READY."),
        ]
    )
    calls = response.tool_calls
    if len(calls) != 1:
        raise RuntimeError("EXPECTED_ONE_TOOL_CALL")
    call = calls[0]
    if call.get("name") != "record_preflight_status" or call.get("args") != {"status": "READY"}:
        raise RuntimeError("TOOL_CALL_SEMANTICS_MISMATCH")

    usage = getattr(response, "usage_metadata", None) or {}
    atomic_json(
        OUTPUT,
        {
            "status": "PASS",
            "model": MIMO_MODEL,
            "base_url": MIMO_BASE_URL,
            "transport": "OPENAI_CHAT_COMPLETIONS",
            "tool_calls": 1,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledgement", default="")
    args = parser.parse_args()
    if args.check == args.execute:
        parser.error("choose exactly one of --check or --execute")

    config = MimoConfig()
    if args.check:
        if config.use_responses_api or config.base_url != MIMO_BASE_URL or config.model != MIMO_MODEL:
            raise RuntimeError("STATIC_MIMO_CONFIG_INVALID")
        state = "PASS" if OUTPUT.exists() else "NOT_RUN"
        print(
            f"VALID mimo-preflight model={config.model} transport=CHAT_COMPLETIONS "
            f"network={state}"
        )
        return 0

    execute(args.acknowledgement)
    print(f"PASS mimo-preflight output={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
