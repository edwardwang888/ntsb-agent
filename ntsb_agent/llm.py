"""ModelGateway: the single choke point for every Claude API request.

Everything that talks to the model goes through a ModelGateway instance, so
logging (and later: retries, token budgets, governance checks) is applied in
exactly one place.

The gateway is created once at the entry point (qa.main(), later the Streamlit
app) and passed to whatever needs the model. No module-level client: callers
receive their dependency explicitly, so tests and evals can pass a fake client.
"""
from __future__ import annotations

import os
import time

import anthropic

from .calllog import log
from .config import MODEL


class ModelError(RuntimeError):
    pass


class ModelGateway:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL):
        # The SDK client holds the HTTP connection pool, so build it once per
        # gateway and reuse it for every call.
        # Default SDK retries (2) stay on in Phase 1. In Phase 3 we set
        # max_retries=0 and own the retry policy so every attempt is logged.
        # The cloud environment withholds ANTHROPIC_API_KEY from the shell
        # (reserved for the platform's own connection), so the key is stored as
        # NTSB_ANTHROPIC_API_KEY there. None falls back to ANTHROPIC_API_KEY
        # (from .env or the shell) for local runs.
        self.client = client or anthropic.Anthropic(
            api_key=os.environ.get("NTSB_ANTHROPIC_API_KEY") or None
        )
        self.model = model

    def call(
        self,
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
            "model": self.model,
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
            resp = self.client.beta.messages.create(**request)
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
