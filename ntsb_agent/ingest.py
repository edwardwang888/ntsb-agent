"""NTSB ingestion: the ONE place that knows where NTSB data comes from.

Contract (what the rest of the code relies on):
    fetch_ntsb_tables(since_year) -> list[Table]
    - table and column names are canonical: lowercase snake_case
    - types are SQLite types (INTEGER, REAL, TEXT); dates are ISO-8601 TEXT
    - rows are already filtered to events with ev_year >= since_year

Today this is backed by avall.zip + mdbtools. When NTSB moves bulk data to an
API (planned 2027-04-05), write a new fetcher that honors the same contract and
nothing downstream (loader, SQL prompt, pipeline) should need to change.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import RAW_DIR

AVALL_URL = "https://data.ntsb.gov/avdata/FileDirectory/DownloadFile?fileID=avall.zip"

# Source table name -> canonical name. Everything else in the .mdb is ignored.
TABLES = {
    "events": "events",
    "aircraft": "aircraft",
    "narratives": "narratives",
    "Findings": "findings",
    "Events_Sequence": "events_sequence",
    "eADMSPUB_DataDictionary": "data_dictionary",  # code -> meaning lookups
}
# Columns whose normalized names would collide with SQL keywords.
COLUMN_RENAMES = {"data_dictionary": {"table": "table_name", "column": "column_name"}}
# Tables not keyed by event, so not filtered by year.
UNFILTERED = {"data_dictionary"}

csv.field_size_limit(sys.maxsize)  # narratives can be very long


@dataclass
class Table:
    name: str
    columns: list[tuple[str, str]]  # (canonical column name, SQLite type)
    rows: list[tuple] = field(default_factory=list)


def fetch_ntsb_tables(since_year: int, raw_dir: Path = RAW_DIR, refresh: bool = False) -> list[Table]:
    """Return the core NTSB tables, filtered to events in or after `since_year`."""
    mdb = _get_mdb(raw_dir, refresh)

    tables = {canon: _read_table(mdb, src, canon) for src, canon in TABLES.items()}

    events = tables["events"]
    year_idx = _col_index(events, "ev_year")
    events.rows = [r for r in events.rows if r[year_idx] is not None and r[year_idx] >= since_year]
    keep = {r[_col_index(events, "ev_id")] for r in events.rows}

    # The dictionary refers to tables/columns by source names; rewrite them to
    # canonical names so it can be joined against our tables.
    dd = tables["data_dictionary"]
    ti, ci = _col_index(dd, "table_name"), _col_index(dd, "column_name")
    dd.rows = [
        tuple(_canonical(v) if i in (ti, ci) and v else v for i, v in enumerate(r))
        for r in dd.rows
    ]

    for name, t in tables.items():
        if name in ("events", *UNFILTERED):
            continue
        idx = _col_index(t, "ev_id")
        t.rows = [r for r in t.rows if r[idx] in keep]

    return list(tables.values())


# --- avall.zip / mdbtools specifics below -----------------------------------

def _get_mdb(raw_dir: Path, refresh: bool) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path, mdb_path = raw_dir / "avall.zip", raw_dir / "avall.mdb"
    if refresh or not zip_path.exists():
        print(f"Downloading {AVALL_URL} ...", file=sys.stderr)
        urllib.request.urlretrieve(AVALL_URL, zip_path)
    if refresh or not mdb_path.exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extract("avall.mdb", raw_dir)
    return mdb_path


def _canonical(name: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_")


def _source_types(mdb: Path, table: str) -> dict[str, str]:
    """Column -> SQLite type, from mdbtools' own SQLite DDL translation."""
    ddl = subprocess.run(
        ["mdb-schema", "-T", table, str(mdb), "sqlite"],
        check=True, capture_output=True, text=True,
    ).stdout
    types = {}
    for col, typ in re.findall(r"`([^`]+)`\s+(\w+)", ddl):
        if col == table:
            continue
        typ = typ.upper()
        types[col] = typ if typ in ("INTEGER", "REAL") else "TEXT"
    return types


def _read_table(mdb: Path, src: str, canon: str) -> Table:
    types = _source_types(mdb, src)
    proc = subprocess.Popen(
        ["mdb-export", "-D", "%Y-%m-%d", "-T", "%Y-%m-%d %H:%M:%S", str(mdb), src],
        stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    reader = csv.reader(proc.stdout)
    header = next(reader)
    renames = COLUMN_RENAMES.get(canon, {})
    columns = []
    for col in header:
        c = _canonical(col)
        columns.append((renames.get(c, c), types.get(col, "TEXT")))
    casts = [_caster(t) for _, t in columns]
    rows = [tuple(cast(v) for cast, v in zip(casts, rec)) for rec in reader]
    if proc.wait() != 0:
        raise RuntimeError(f"mdb-export failed for table {src}")
    return Table(canon, columns, rows)


def _caster(sqlite_type: str):
    def cast(v: str):
        if v == "":
            return None
        if sqlite_type == "INTEGER":
            try:
                return int(v)
            except ValueError:
                return int(float(v))
        if sqlite_type == "REAL":
            return float(v)
        return v.strip()
    return cast


def _col_index(t: Table, name: str) -> int:
    return [c for c, _ in t.columns].index(name)
