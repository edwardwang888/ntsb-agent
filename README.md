# NTSB Accident Analyst

Answers questions about aviation accidents from NTSB data. Learning project; see `AGENTS.md` for goals and phases, `docs/decisions.md` for why things are built the way they are.

## Setup
```bash
apt-get install mdbtools        # or: brew install mdbtools
pip install -r requirements.txt
cp .env.example .env            # add ANTHROPIC_API_KEY
python -m ntsb_agent.load       # downloads avall.zip (~100 MB), builds data/ntsb.db
```

## Ask a question (Phase 1: fixed two-call pipeline)
```bash
python -m ntsb_agent.qa "How many fatal accidents involved Cessna 172s in 2023?"
```
Every model call and SQL execution is logged to `logs/YYYY-MM-DD.jsonl`, grouped by `run_id`.

## Layout
| File | Role |
|---|---|
| `ntsb_agent/ingest.py` | `fetch_ntsb_tables()`: the only code that knows the data source (swap point for the 2027 NTSB API) |
| `ntsb_agent/load.py` | Builds SQLite from the fetched tables |
| `ntsb_agent/db.py` | `execute_sql()`: read-only, time/row/size-bounded query execution |
| `ntsb_agent/llm.py` | `call_model()`: single choke point for Claude API calls + logging |
| `ntsb_agent/qa.py` | The pipeline: question → SQL → rows → answer |
| `ntsb_agent/prompts/` | System prompts and the hand-written schema description |
