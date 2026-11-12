"""Phase 1 question-answering: a fixed two-call pipeline.

    question --(model call 1)--> SQL --(execute_sql)--> rows --(model call 2)--> answer

Our code decides the sequence. The model never chooses whether or when to
query; that is the difference from the Phase 3 agent loop.

Run: python -m ntsb_agent.qa "How many fatal accidents involved Cessna 172s in 2023?"
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from .calllog import log, new_run_id
from .db import execute_sql
from .llm import call_model

PROMPTS = Path(__file__).parent / "prompts"

# Contract for model call 1. Structured output guarantees the response parses
# into exactly these fields, so there is no regex-scraping SQL out of prose.
SQL_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "sql": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["answerable", "sql", "notes"],
    "additionalProperties": False,
}


@dataclass
class Answer:
    run_id: str
    question: str
    answerable: bool
    sql: str
    notes: str
    result: dict | None
    text: str


def _prompts() -> tuple[str, str]:
    meta = dict(execute_sql("SELECT key, value FROM load_metadata")["rows"])
    fill = {"{since_year}": meta.get("since_year", "?"), "{max_ev_date}": (meta.get("max_ev_date") or "?")[:10]}

    def render(text: str) -> str:
        for k, v in fill.items():
            text = text.replace(k, v)
        return text

    schema = render((PROMPTS / "schema.md").read_text())
    write_sql = render((PROMPTS / "write_sql.md").read_text()).replace("{schema}", schema)
    answer = render((PROMPTS / "answer.md").read_text())
    return write_sql, answer


def ask(question: str) -> Answer:
    run_id = new_run_id()
    log("question", run_id, question=question)
    write_sql_system, answer_system = _prompts()

    # Step 1: model writes SQL (or says the question isn't answerable from data).
    plan = json.loads(call_model(
        run_id=run_id, step="write_sql",
        system=write_sql_system, user=question, output_schema=SQL_PLAN_SCHEMA,
    ))

    # Step 2: our code runs it. No retry on error in Phase 1, by design.
    result = None
    if plan["answerable"] and plan["sql"].strip():
        result = execute_sql(plan["sql"])
        log("tool_call", run_id, tool="execute_sql", input={"sql": plan["sql"]},
            output=result, latency_ms=result["latency_ms"])

    # Step 3: model writes the answer from the rows only.
    answer_input = (
        f"<question>{question}</question>\n"
        f"<query_notes>{plan['notes']}</query_notes>\n"
        + (f"<sql>{plan['sql']}</sql>\n<query_results>{json.dumps(result, default=str)}</query_results>"
           if result is not None else
           "<query_results>No query was run: the question was judged not answerable from the database.</query_results>")
    )
    text = call_model(run_id=run_id, step="answer", system=answer_system, user=answer_input)

    out = Answer(run_id, question, plan["answerable"], plan["sql"], plan["notes"], result, text)
    log("answer", run_id, answer=text)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("question")
    a = ask(p.parse_args().question)
    print(a.text)
    print("\n---")
    print(f"run_id: {a.run_id}")
    print(f"notes:  {a.notes}")
    if a.sql:
        print(f"sql:\n{a.sql}")
    if a.result and a.result["error"]:
        print(f"sql error: {a.result['error']}")


if __name__ == "__main__":
    main()
