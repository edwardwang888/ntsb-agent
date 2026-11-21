"""Append-only JSONL log of every model call and tool call.

One file per UTC day in logs/. Every record carries a `run_id` so all the steps
of one question (model call -> SQL -> model call) can be pulled back together:
    jq 'select(.run_id=="...")' logs/2026-11-12.jsonl
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from .config import LOG_DIR


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def log(kind: str, run_id: str, **fields) -> None:
    now = datetime.now(timezone.utc)
    record = {"ts": now.isoformat(timespec="milliseconds"), "kind": kind, "run_id": run_id, **fields}
    LOG_DIR.mkdir(exist_ok=True)
    with open(LOG_DIR / f"{now:%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
