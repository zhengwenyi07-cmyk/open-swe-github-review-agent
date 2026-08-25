"""MiMo Chat Completions adapter for the future paid preflight.

Open SWE's frozen ``make_model('openai:...')`` path defaults to the OpenAI
Responses API. MiMo is OpenAI-compatible through Chat Completions, so Phase 1
uses the officially documented pre-configured-model escape hatch instead of
changing Open SWE's global routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import SecretStr

MIMO_MODEL = "mimo-v2.5-pro"
MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"


@dataclass(frozen=True)
class MimoConfig:
    model: str = MIMO_MODEL
    base_url: str = MIMO_BASE_URL
    temperature: float = 0.0
    max_tokens: int = 4096
    max_retries: int = 0
    use_responses_api: bool = False


def validate_mimo_response_identity(response: Any) -> tuple[str, str]:
    """Return the API-reported model and finish reason or fail closed."""

    metadata = getattr(response, "response_metadata", None) or {}
    response_model = metadata.get("model_name") or metadata.get("model")
    finish_reason = metadata.get("finish_reason")
    if response_model != MIMO_MODEL:
        raise ValueError("MiMo response model identity mismatch")
    if finish_reason != "tool_calls":
        raise ValueError("MiMo response finish reason mismatch")
    return response_model, finish_reason


def create_mimo_model(api_key: str, config: MimoConfig | None = None) -> Any:
    """Return a pre-configured LangChain model without making a network call."""

    if not api_key or api_key.strip() != api_key:
        raise ValueError("MIMO_API_KEY must be a non-empty unpadded value")
    selected = config or MimoConfig()
    if selected.model != MIMO_MODEL or selected.base_url != MIMO_BASE_URL:
        raise ValueError("MiMo identity mismatch")
    if selected.use_responses_api:
        raise ValueError("MiMo must use Chat Completions, not Responses")

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=selected.model,
        api_key=SecretStr(api_key),
        base_url=selected.base_url,
        temperature=selected.temperature,
        max_tokens=selected.max_tokens,
        max_retries=selected.max_retries,
        use_responses_api=False,
    )
