"""execute_sql(): the only way model-written SQL touches the database.

Phase 1 calls this directly from the pipeline; Phase 3 wraps the same function
as the `run_sql` tool. Its guarantees therefore have to hold no matter who
wrote the SQL:

  1. Read-only, enforced by SQLite itself (three independent layers below),
     not by inspecting the SQL text.
  2. Bounded: a time limit, a row cap, and a per-cell character cap, so one bad
     query can't hang the app or flood the model's context.
  3. Never raises for bad SQL: errors come back as data, so the caller (and
     later, the model) can see what went wrong.
"""
from __future__ import annotations

import sqlite3
import time

from .config import DB_PATH

MAX_ROWS = 200          # rows returned to the caller
MAX_CELL_CHARS = 1500   # narratives can be 70k+ chars; truncate per cell
TIMEOUT_S = 10.0

# Authorizer: SQLite asks this callback about every operation while compiling a
# statement. Anything not on this list (INSERT, UPDATE, DELETE, CREATE, DROP,
# ATTACH, PRAGMA, ...) is denied before it can run.
_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,  # WITH RECURSIVE
}


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _connect() -> sqlite3.Connection:
    # Layer 1: the file is opened read-only at the OS/driver level.
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    # Layer 2: SQLite refuses any statement that would write.
    con.execute("PRAGMA query_only = ON")
    # Layer 3: per-operation allow-list (also blocks ATTACH of other files).
    con.set_authorizer(_authorizer)
    return con


def execute_sql(sql: str) -> dict:
    """Run one SELECT. Returns a JSON-serializable dict; never raises on bad SQL."""
    t0 = time.monotonic()
    result = {"sql": sql, "columns": [], "rows": [], "row_count": 0,
              "truncated_rows": False, "truncated_cells": 0, "error": None}
    con = _connect()
    deadline = t0 + TIMEOUT_S
    # Called every N VM steps; returning non-zero aborts the query.
    con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    try:
        cur = con.execute(sql)  # sqlite3 rejects multiple statements on its own
        result["columns"] = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(MAX_ROWS + 1)
        result["truncated_rows"] = len(rows) > MAX_ROWS
        for row in rows[:MAX_ROWS]:
            out = []
            for v in row:
                if isinstance(v, str) and len(v) > MAX_CELL_CHARS:
                    v = v[:MAX_CELL_CHARS] + " …[truncated]"
                    result["truncated_cells"] += 1
                out.append(v)
            result["rows"].append(out)
        result["row_count"] = len(result["rows"])
    except sqlite3.Error as e:
        msg = str(e)
        if msg == "interrupted":
            msg = f"query exceeded {TIMEOUT_S:.0f}s time limit"
        result["error"] = f"{type(e).__name__}: {msg}"
    finally:
        con.close()
    result["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return result
