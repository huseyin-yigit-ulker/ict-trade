"""Inject the d30so8c env knobs from .env into os.environ — MUST be imported FIRST by every
entry point, BEFORE trade_sync_common / ict.config / scaleout load.

`scaleout.RUNNER_CAP` + `scaleout.VERSION` and `ict.config.ENTRY_AT_CONFIRM` are evaluated at
IMPORT time from os.environ, but .env is only parsed by tsc._read_env() (never pushed to
os.environ). Without this preload, a prefix-less launch (`python executor.py`, or a cron line
without the inline `DCH_SO_RUNNER_CAP=8 DCH_ENTRY_AT_CONFIRM=1`) silently runs the 4R / entry@close
defaults instead of the 8R confirmed (d30so8c) twin. Precedence: an explicit process env (cron
prefix) wins; else .env; else the d30so8c default.
"""
from __future__ import annotations

import os
from pathlib import Path

_DEFAULTS = (("DCH_SO_RUNNER_CAP", "8"), ("DCH_ENTRY_AT_CONFIRM", "1"))


def _load() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"   # repo/.env
    vals: dict[str, str] = {}
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if (v[:1], v[-1:]) in (('"', '"'), ("'", "'")):
                v = v[1:-1]
            vals[k.strip()] = v
    except OSError:
        pass
    for k, default in _DEFAULTS:
        # setdefault: a value already in os.environ (cron prefix) is explicit operator intent — keep
        # it; otherwise take .env, else the default.
        os.environ.setdefault(k, vals.get(k, default))


_load()
