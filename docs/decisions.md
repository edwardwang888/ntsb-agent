# Decision Log

One entry per meaningful design choice. Newest at the bottom.

Template:

## YYYY-MM-DD — <decision title>
- **Decision:**
- **Alternatives considered:**
- **Why:**
- **Revisit when:**

---

## 2026-11-12 — Phase 1 Q&A uses a fixed two-call pipeline, not a tool-use loop
- **Decision:** Question → model writes SQL (call 1) → our code runs it on a read-only SQLite connection → model writes the answer from the rows (call 2). Code controls the sequence; the model never decides when to query.
- **Alternatives considered:** Give the model a `run_sql` tool and loop until `stop_reason != "tool_use"`. Recovers from bad SQL and can explore coded values (`SELECT DISTINCT`), but variable cost/latency, needs a turn cap, and harder to eval.
- **Why:** Simplest thing that works; each step is inspectable and the SQL can be scored separately from the answer. Its failures (especially guessing NTSB coded values wrong) make the case for the loop concrete before Phase 3.
- **Revisit when:** Phase 3. Keep `execute_sql()` as the shared seam so it becomes the `run_sql` tool unchanged. If we add "retry with the error message", note that we're hand-building the loop.
