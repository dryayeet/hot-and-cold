"""Shared helpers for dev tools: load .env, connect to Supabase Postgres."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = REPO_ROOT / ".env"


def load_env() -> None:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)
    missing = [k for k in ("DATABASE_URL", "SUPABASE_URL") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"missing env vars: {', '.join(missing)} (expected in {ENV_PATH})")


def connect(autocommit: bool = False) -> psycopg.Connection:
    load_env()
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=autocommit)
