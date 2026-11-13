"""call_model(): the single choke point for every Claude API request.

Everything that talks to the model goes through here, so logging (and later:
retries, token budgets, governance checks) is applied in exactly one place.
"""
from __future__ import annotations

import os
import time

import anthropic

from .calllog import log
from .config import MODEL

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Default SDK retries (2) stay on in Phase 1. In Phase 3 we set
        # max_retries=0 and own the retry policy so every attempt is logged.
        # The cloud environment withholds ANTHROPIC_API_KEY from the shell
        # (reserved for the platform's own connection), so the key is stored as
        # NTSB_ANTHROPIC_API_KEY there. None falls back to ANTHROPIC_API_KEY
        # (from .env or the shell) for local runs.
        _client = anthropic.Anthropic(
            api_key=os.environ.get("NTSB_ANTHROPIC_API_KEY") or None
        )
    return _client


class ModelError(RuntimeError):
    pass


def call_model(
    *,
    run_id: str,
    step: str,
    system: str,
    user: str,
    output_schema: dict | None = None,
    effort: str = "medium",
    max_tokens: int = 16000,
) -> str:
    """One request/response. Returns the response text (JSON text if output_schema)."""
    output_config: dict = {"effort": effort}
    if output_schema is not None:
        # Structured output: the API guarantees the text is JSON matching this schema.
        output_config["format"] = {"type": "json_schema", "schema": output_schema}

    request = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": output_config,
        # If the model declines on safety grounds, the API retries on a fallback
        # model inside the same call instead of returning an empty refusal.
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }

    t0 = time.monotonic()
    try:
        resp = _get_client().beta.messages.create(**request)
    except anthropic.APIError as e:
        log("model_call", run_id, step=step, request=request, error=f"{type(e).__name__}: {e}",
            latency_ms=round((time.monotonic() - t0) * 1000, 1))
        raise
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    text = "".join(b.text for b in resp.content if b.type == "text")
    log(
        "model_call", run_id,
        step=step,
        request=request,
        response={"content": [b.to_dict() for b in resp.content], "model": resp.model},
        stop_reason=resp.stop_reason,
        usage=resp.usage.to_dict(),
        request_id=resp._request_id,
        latency_ms=latency_ms,
    )

    if resp.stop_reason == "refusal":
        raise ModelError(f"model declined ({step}): {resp.stop_details}")
    if resp.stop_reason == "max_tokens":
        raise ModelError(f"response hit max_tokens ({step})")
    return text
