"""Build data/ntsb.db from fetch_ntsb_tables(). Run: python -m ntsb_agent.load

Full rebuild each time (avall is a full monthly snapshot). We write to a temp
file and rename it into place, so a half-finished load is never queried.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone

from .config import DB_PATH, SINCE_YEAR
from .ingest import AVALL_URL, fetch_ntsb_tables

# events_sequence.phase_no codes are not in NTSB's data dictionary. Names below
# are the phase text that prefixes events_sequence.occurrence_description for
# each code (derived from the data, 2026-11 snapshot).
PHASES = {
    "100": "Prior to flight", "150": "Standing", "151": "Standing-engine(s) not oper",
    "152": "Standing-engine(s) start-up", "153": "Standing-engine(s) operating",
    "154": "Standing-engine(s) shutdown", "200": "Pushback/towing",
    "201": "Pushback/tow-engine not oper", "202": "Pushback/tow-engine start-up",
    "203": "Pushback/tow-engine oper", "250": "Taxi", "251": "Taxi-to runway",
    "252": "Taxi-into takeoff position", "253": "Taxi-from runway", "300": "Takeoff",
    "301": "Takeoff-rejected takeoff", "350": "Initial climb", "400": "Enroute",
    "401": "Enroute-climb to cruise", "402": "Enroute-cruise",
    "403": "Enroute-change of cruise level", "404": "Enroute-descent",
    "405": "Enroute-holding (IFR)", "450": "Maneuvering", "451": "Maneuvering-aerobatics",
    "452": "Maneuvering-low-alt flying", "453": "Maneuvering-hover", "500": "Approach",
    "501": "Approach-IFR initial approach", "502": "Approach-IFR final approach",
    "503": "Approach-circling (IFR)", "504": "Approach-IFR missed approach",
    "505": "Approach-VFR pattern crosswind", "506": "Approach-VFR pattern downwind",
    "507": "Approach-VFR pattern base", "508": "Approach-VFR pattern final",
    "509": "Approach-VFR go-around", "550": "Landing", "551": "Landing-flare/touchdown",
    "552": "Landing-landing roll", "553": "Landing-aborted after touchdown",
    "600": "Emergency descent", "601": "Autorotation", "650": "Uncontrolled descent",
    "700": "Post-impact", "750": "After landing", "800": "Other", "990": "Unknown",
}


def build(since_year: int = SINCE_YEAR, refresh: bool = False) -> None:
    tables = fetch_ntsb_tables(since_year, refresh=refresh)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)

    con = sqlite3.connect(tmp)
    for t in tables:
        cols = ", ".join(f'"{c}" {typ}' for c, typ in t.columns)
        con.execute(f'CREATE TABLE "{t.name}" ({cols})')
        marks = ", ".join("?" * len(t.columns))
        con.executemany(f'INSERT INTO "{t.name}" VALUES ({marks})', t.rows)
        if any(c == "ev_id" for c, _ in t.columns):
            con.execute(f'CREATE INDEX "ix_{t.name}_ev_id" ON "{t.name}"(ev_id)')
        print(f"{t.name:18} {len(t.rows):>8,} rows")
    con.execute("CREATE INDEX ix_events_ntsb_no ON events(ntsb_no)")
    con.execute("CREATE TABLE phase_of_flight (phase_no TEXT PRIMARY KEY, phase_name TEXT)")
    con.executemany("INSERT INTO phase_of_flight VALUES (?, ?)", PHASES.items())
    con.execute("CREATE INDEX ix_dd_lookup ON data_dictionary(table_name, column_name, code_iaids)")

    # Provenance: lets answers say "data as of ..." and lets us audit loads later.
    con.execute("CREATE TABLE load_metadata (key TEXT PRIMARY KEY, value TEXT)")
    con.executemany("INSERT INTO load_metadata VALUES (?, ?)", [
        ("source", AVALL_URL),
        ("since_year", str(since_year)),
        ("loaded_at_utc", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ("max_ev_date", con.execute("SELECT max(ev_date) FROM events").fetchone()[0]),
    ])
    con.commit()
    con.close()
    os.replace(tmp, DB_PATH)
    print(f"Wrote {DB_PATH}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--since-year", type=int, default=SINCE_YEAR)
    p.add_argument("--refresh", action="store_true", help="re-download avall.zip")
    a = p.parse_args()
    build(a.since_year, a.refresh)
