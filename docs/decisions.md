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

## 2026-11-13 — API key read from `NTSB_ANTHROPIC_API_KEY` first
- **Decision:** `llm._get_client()` passes `NTSB_ANTHROPIC_API_KEY` to the SDK if set; otherwise the SDK's default `ANTHROPIC_API_KEY` lookup applies.
- **Alternatives considered:** Keep only `ANTHROPIC_API_KEY`; store the key as a network secret on `api.anthropic.com`.
- **Why:** The cloud environment defines `ANTHROPIC_API_KEY`, but it never reaches the session shell (likely reserved because Claude Code uses that name for its own connection), and `api.anthropic.com` can't hold a network secret. A project-prefixed name avoids the collision; the fallback keeps `.env`-based local runs unchanged.
- **Revisit when:** The platform passes `ANTHROPIC_API_KEY` through, or Phase 4 moves secrets into a dedicated secrets manager.

## 2026-11-13 — `ModelGateway` class, passed in explicitly, replaces `call_model()` + module-level client
- **Decision:** `llm.ModelGateway(client=None, model=MODEL)` owns the Anthropic client and exposes `.call(...)` (same logging and behavior as the old `call_model()`). It is built once at the entry point (`qa.main()`, later the Streamlit app) and passed down: `ask(question, llm)`. No module-level instance. Supersedes the "choke point" mechanism in the 2026-11-12 entry; the choke-point idea itself is unchanged.
- **Alternatives considered:** (a) Keep the function with a lazily created `global _client`. (b) Same, but `@functools.cache` on `_get_client()` instead of `global`. (c) A class plus a module-level `default_gateway`.
- **Why:** (a)–(c) all keep the dependency on the model hidden module state; (b) and (c) only rename the global. Passing the gateway in (dependency injection) makes the dependency visible in `ask()`'s signature, lets tests and evals pass a fake or replaying client instead of monkeypatching, and gives Phase 3 per-run state (retry policy, token budget) and Phase 4 governance checks an obvious home. Cost: one extra parameter at each call site.
- **Revisit when:** Phase 3 adds retries/budgets (put them on the instance, not module globals). If several gateways with different configs coexist, consider a small config dataclass passed to `__init__`.

## 2026-11-16 — Secret scanning with gitleaks in CI
- **Decision:** A GitHub Actions workflow (`.github/workflows/secret-scan.yml`) runs `gitleaks/gitleaks-action` on every push and pull request, scanning each commit in the range rather than only the final tree.
- **Alternatives considered:** A local pre-commit hook (catches a secret before it ever leaves the machine, but needs the `pre-commit` tool installed on every clone and can be skipped with `--no-verify`); TruffleHog (verifies live keys against provider APIs, heavier and noisier for a small repo); relying on GitHub's built-in push protection alone (only covers partner-registered token formats).
- **Why:** CI can't be skipped and needs nothing installed locally. Scanning per commit matters because a key added and then deleted is still in history. No new Python dependency.
- **Revisit when:** A secret slips through (add a pre-commit hook for earlier blocking), we get false positives (add a `.gitleaks.toml` allowlist), or the repo moves under a GitHub organization (the action then needs a free `GITLEAKS_LICENSE` key).
