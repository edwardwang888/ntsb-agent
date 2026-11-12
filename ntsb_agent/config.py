"""Paths and settings. Secrets come from .env (never committed)."""
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "ntsb.db"
LOG_DIR = ROOT / "logs"

MODEL = "claude-opus-5-5"
SINCE_YEAR = 2015
