"""DB connection helpers.

Reads connection strings from the repo .env and parses them MANUALLY
(the passwords contain %, £, backticks etc. which break urllib parsing /
URL-encoding). Returns psycopg2 connections.
"""
from __future__ import annotations
import os
import re
from pathlib import Path

import psycopg2

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        out[k] = v
    return out


_DSN_RE = re.compile(
    r"^postgres(?:ql)?://(?P<user>[^:]+):(?P<password>.*)@(?P<host>[^:/@]+):(?P<port>\d+)/(?P<db>.+)$"
)


def parse_dsn(dsn: str) -> dict:
    """Parse a postgres URL whose password may contain special chars.

    user has no ':'; password is everything up to the LAST '@' before host:port/db.
    """
    # Split off scheme
    body = dsn.split("://", 1)[1]
    # host:port/db is after the last '@'
    creds, hostpart = body.rsplit("@", 1)
    user, password = creds.split(":", 1)
    hostport, db = hostpart.split("/", 1)
    host, port = hostport.rsplit(":", 1)
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": int(port),
        "dbname": db,
    }


def _connect(dsn_key: str):
    env = _read_env()
    dsn = env[dsn_key]
    params = parse_dsn(dsn)
    return psycopg2.connect(connect_timeout=20, **params)


def live_conn():
    """LIVE signals DB (ict_trade.signals)."""
    return _connect("DB_CONNECTION_STRING")


def backtest_conn():
    """BACKTEST results DB (ict_trade.trading_signals)."""
    return _connect("BACKTESTING_DB_CONNECTION_STRING")
