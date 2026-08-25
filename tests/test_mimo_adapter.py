from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_mimo_preflight
from open_swe_review_agent.mimo import (
    MIMO_BASE_URL,
    MIMO_MODEL,
    MimoConfig,
    create_mimo_model,
    validate_mimo_response_identity,
)


class MimoAdapterTests(unittest.TestCase):
    def test_frozen_identity_uses_chat_completions(self) -> None:
        config = MimoConfig()
        self.assertEqual(config.model, MIMO_MODEL)
        self.assertEqual(config.base_url, MIMO_BASE_URL)
        self.assertFalse(config.use_responses_api)
        self.assertEqual(config.temperature, 0.0)
        self.assertEqual(config.max_retries, 0)

    def test_factory_passes_secret_without_network_call(self) -> None:
        with patch("langchain_openai.ChatOpenAI") as constructor:
            create_mimo_model("secret-for-test-only")
        kwargs = constructor.call_args.kwargs
        self.assertEqual(kwargs["model"], MIMO_MODEL)
        self.assertEqual(kwargs["base_url"], MIMO_BASE_URL)
        self.assertFalse(kwargs["use_responses_api"])
        self.assertEqual(kwargs["api_key"].get_secret_value(), "secret-for-test-only")

    def test_empty_or_padded_key_is_rejected(self) -> None:
        for value in ("", " padded", "padded "):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    create_mimo_model(value)

    def test_responses_api_cannot_be_enabled(self) -> None:
        with self.assertRaisesRegex(ValueError, "Chat Completions"):
            create_mimo_model("secret", MimoConfig(use_responses_api=True))

    def test_wrong_response_model_identity_is_rejected(self) -> None:
        response = type(
            "Response",
            (),
            {"response_metadata": {"model_name": "other-model", "finish_reason": "tool_calls"}},
        )()
        with self.assertRaisesRegex(ValueError, "model identity mismatch"):
            validate_mimo_response_identity(response)

    def test_wrong_finish_reason_is_rejected(self) -> None:
        response = type(
            "Response",
            (),
            {"response_metadata": {"model_name": MIMO_MODEL, "finish_reason": "stop"}},
        )()
        with self.assertRaisesRegex(ValueError, "finish reason mismatch"):
            validate_mimo_response_identity(response)

    def test_preflight_evidence_with_wrong_response_model_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preflight.json"
            output.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "configured_model": MIMO_MODEL,
                        "model": "other-model",
                        "response_model": "other-model",
                        "finish_reason": "tool_calls",
                        "transport": "OPENAI_CHAT_COMPLETIONS",
                        "tool_calls": 1,
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(run_mimo_preflight, "OUTPUT", output):
                with self.assertRaisesRegex(RuntimeError, "PREFLIGHT_EVIDENCE_INVALID"):
                    run_mimo_preflight.load_evidence()


if __name__ == "__main__":
    unittest.main()
