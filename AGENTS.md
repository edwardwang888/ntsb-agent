# NTSB Accident Analyst

A learning project: an agent that answers questions about aviation accidents and air traffic control (ATC) incidents. It starts with NTSB accident data and later adds NASA ASRS incident reports and the FAA ATC rulebook (JO 7110.65), all linked in a knowledge graph.

## My goal

I'm learning AI architecture: knowledge graphs, agentic infrastructure, the inference harness, and governance. You can write the code, but I need to understand **why** it's built the way it is. Working code I don't understand is a failed outcome.

I'm a data engineer and very familiar with Python. Data loading, ETL, and SQL need no explanation. I have less experience with API design, so explain decisions about interfaces, tool schemas, and service structure in more depth.

## How to work with me

**Before writing non-trivial code:**
- Give a short plan (3–5 bullets) and the main alternative you considered, with the trade-off in one line.
- If it's a real design choice (schema, tool interface, loop structure, eval method), stop and let me weigh in.

**After writing code:**
- Summarize the key decisions in plain language: what it does, why this way, and what would break if we did it differently.
- Name the concept it relates to (e.g. "this is context management, part of the harness").
- Point out the 1–2 lines I should look at most closely.

**Decision log:**
- Add an entry to `docs/decisions.md` for every meaningful design choice: date, decision, alternatives, why, and what we'd revisit later.

**Keep it proportionate:**
- Boilerplate (file parsing, UI layout, config) needs only a one-line explanation.
- Spend the explanation on the agent loop, tools, graph schema, retrieval, evals, and governance checks.

**End of each phase:**
- Ask me 3 short questions to check that I understand what we built. Don't move on until I've answered.

## Technical constraints

- Plain Python and the Anthropic SDK. **No agent frameworks** (LangChain, LlamaIndex, etc.). I want to see the loop.
- Ask before adding any new dependency, and say why it's worth it.
- Stack: SQLite → Neo4j, Claude API with tool use, Streamlit for the UI.
- Keep secrets in `.env` and never commit them.
- Log every model call and tool call to `logs/` as JSONL (inputs, outputs, tokens, latency).

## Phases

1. **NTSB data + basic Q&A.** Download `avall.zip` from https://data.ntsb.gov/avdata/ (Access .mdb, updated monthly). Convert the tables with mdbtools and load them into SQLite, starting with 2015 onward. Build question → model writes SQL → answer. (NTSB plans to move bulk downloads to an API on April 5, 2027. Keep ingestion behind one function so it's easy to swap.)
2. **Knowledge graph.** Schema: Aircraft Model, Event, Phase of Flight, Finding, Airport, Weather Condition, plus ATC Factor (for accidents that involve ATC). Use the model to extract entities from narratives. Compare graph queries with text search on 20 questions.
3. **Agent + harness.** Hand-written loop with tools `query_graph`, `search_narratives`, `get_metar`, and `lookup_tail_number`. Add retries and context trimming. Build a 30-question eval set with a scoring script.
4. **Governance.** Product rules below, enforced in code, plus an audit log, red-team evals, a one-page system card, and a mapping to the NIST AI RMF (Govern / Map / Measure / Manage).
5. **Add ATC sources.** Load NASA ASRS reports, starting with the Hugging Face subset `NASA-AIML/ASRS` and moving to manual CSV exports later, filtered to ATC-related reports. Parse JO 7110.65 into searchable rules. Link entities across sources (airport, aircraft type, phase of flight) and link incidents to the rules involved. Add the new sources to the evals.

Stretch: OpenSky flight tracks (`query_tracks` tool), FAA SWIM live streaming, ATCO2 radio audio, exposing the tools as an MCP server.

## Product rules (the agent's own behavior)

- It analyzes historical data. It **never** gives go/no-go flight advice or operational recommendations to pilots.
- It never phrases output as a controller instruction and never uses ATC phraseology as a directive.
- Every factual claim cites its source: an NTSB report number, ASRS report number, or 7110.65 paragraph. Answers without one get flagged.
- ASRS reports are unverified, self-reported accounts. Say so whenever an answer relies on them.
- Tools are read-only.
- When data is missing or ambiguous, say so rather than guess.
