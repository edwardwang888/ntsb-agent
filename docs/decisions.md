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

## 2026-11-12 — Ingestion contract: canonical tables behind `fetch_ntsb_tables()`
- **Decision:** One function returns `Table(name, columns[(name, sqlite_type)], rows)` with lowercase snake_case names, ISO dates, and the since-year filter already applied. All mdbtools/avall specifics live below it. The loader only sees `Table`s.
- **Alternatives considered:** (a) Load the .mdb tables 1:1 and filter in SQL. (b) Have the loader shell out to mdbtools directly.
- **Why:** The 2027 NTSB API will return different field names and formats. If downstream code (loader, schema prompt, SQL the model learned to write) depends only on canonical names, the swap is one new function. Filtering at the source matches how an API with date parameters will work.
- **Revisit when:** The NTSB API ships; or we need incremental loads instead of full monthly rebuilds.

## 2026-11-12 — Read-only enforced by SQLite, not by inspecting SQL text
- **Decision:** `execute_sql()` opens the DB with `mode=ro`, sets `PRAGMA query_only`, and installs an authorizer that allows only SELECT/READ/FUNCTION/RECURSIVE. Also: 10 s time limit, 200-row cap, 1,500-char cell cap. Errors are returned as data, never raised.
- **Alternatives considered:** Regex/allow-list on the SQL string (e.g. "must start with SELECT"); a SQL parser.
- **Why:** String checks are bypassable (CTEs, comments, `ATTACH`, odd casing) and give false confidence. The database engine already knows exactly what each statement does. The caps are context management: a 70k-char narrative or 19k rows would swamp the answer prompt.
- **Revisit when:** Phase 3 (this becomes the `run_sql` tool; caps may need to be smarter, e.g. summarizing large results) and Phase 4 (governance: "tools are read-only" can point to this as its enforcement).

## 2026-11-12 — Model call 1 returns structured JSON `{answerable, sql, notes}`
- **Decision:** Use structured outputs (`output_config.format` with a JSON schema) for the SQL-writing step.
- **Alternatives considered:** Ask for a ```sql fenced block and parse it; force a tool call as a schema trick (not available: forced `tool_choice` returns 400 on this model).
- **Why:** Parsing prose is brittle. The schema guarantees parseable output and gives two extra channels we need for product rules: `answerable=false` (e.g. go/no-go advice requests skip the query entirely) and `notes` (assumptions the answer must surface, e.g. how "Cessna 172" was matched).
- **Revisit when:** Phase 3, where the SQL becomes a tool input instead.

## 2026-11-12 — Hand-written, data-verified schema description in the prompt
- **Decision:** `prompts/schema.md` describes only the columns that matter, the codes, and the traps found by profiling (make spelling variants, `UNK`/`Unk`, `COUNT(DISTINCT ev_id)` after joins, airport ID forms, `phase_flt_spec` always NULL). Codes not in NTSB's dictionary (`phase_no`) got a `phase_of_flight` lookup table.
- **Alternatives considered:** Dump the full DDL (~300 columns) into the prompt; let the model discover the schema with queries (needs the loop).
- **Why:** A raw DDL dump is longer and says nothing about what values look like, which is where text-to-SQL fails. The description is ~1,700 tokens.
- **Revisit when:** Eval failures point at a missing or wrong note. Phase 2 should resolve make/model variants as Aircraft Model entities instead of `LIKE` patterns.

## 2026-11-12 — `call_model()` as the single choke point; JSONL logs keyed by `run_id`
- **Decision:** Every API request goes through `llm.call_model()`, which logs the full request, response content, usage, stop_reason, request_id and latency. SQL executions are logged as `tool_call`. All records for one question share a `run_id`.
- **Alternatives considered:** Log at each call site; use the SDK's built-in debug logging.
- **Why:** One place to add retries, budgets and governance checks later. `run_id` is a minimal trace ID so a question can be replayed step by step.
- **Revisit when:** Phase 3 (own retries with `max_retries=0`, log each attempt) and Phase 4 (audit log may need tamper-evidence and PII handling).

## 2026-11-12 — Server-side refusal fallback enabled
- **Decision:** Requests go through `client.beta.messages.create` with `fallbacks="default"` (beta `server-side-fallback-2026-07-01`), so a safety refusal is retried on a fallback model inside the same call.
- **Alternatives considered:** Plain `messages.create` and treat refusals as errors.
- **Why:** Accident narratives can describe injuries and deaths in detail; a refusal would otherwise end the question. The fallback is visible in the logged response (`fallback` blocks / `usage.iterations`).
- **Revisit when:** If refusals never occur in eval runs, drop the beta to simplify. `stop_reason == "refusal"` still raises.
