"""Apply supabase/migrations/*.sql over the owner DSN + seed the stream universe.

  .venv/bin/python sync/users/apply_sql.py --phase1          # 001..004 + 005a + 006 (additive set)
  .venv/bin/python sync/users/apply_sql.py --file supabase/migrations/005b_user_scope_indexes.sql
  .venv/bin/python sync/users/apply_sql.py --seed-universe   # scaleout.SO_SYMBOLS -> 'opus', XAUUSDT -> 'midas'

Each .sql file is idempotent and executed as ONE statement batch (dollar-quoted bodies safe).
If 001 fails with a permission error on auth.users (trigger creation), run that single file
in the Supabase SQL editor instead — everything else applies fine over the DSN.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[2]
sys.path.insert(0, str(_HERE.parents[1]))                 # sync/
sys.path.insert(0, str(_HERE.parents[1] / "donchian"))    # scaleout (SO_SYMBOLS)
import trade_sync_common as tsc                            # noqa: E402

MIG_DIR = REPO / "supabase" / "migrations"
PHASE1 = ["001_profiles.sql", "002_audit_log.sql", "003_user_api_keys.sql",
          "004_user_stream_settings.sql", "005a_add_user_id.sql", "006_push_user.sql"]


def apply_file(conn, path: Path) -> None:
    sql = path.read_text()
    print(f"[sql] applying {path.name} ...", flush=True)
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"[sql] {path.name} OK", flush=True)


def seed_universe(conn) -> None:
    import scaleout as so  # deferred: heavy import chain
    rows = [("opus", s) for s in so.SO_SYMBOLS] + [("midas", "XAUUSDT")]
    with conn.cursor() as cur:
        cur.executemany(
            "insert into ict_trade.stream_universe (stream, symbol) values (%s, %s)"
            " on conflict do nothing", rows)
    conn.commit()
    print(f"[sql] stream_universe seeded ({len(rows)} rows: opus={len(rows) - 1}, midas=1)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", default=[])
    ap.add_argument("--phase1", action="store_true")
    ap.add_argument("--seed-universe", action="store_true")
    args = ap.parse_args()

    files = [Path(f) for f in args.file]
    if args.phase1:
        files += [MIG_DIR / f for f in PHASE1]
    if not files and not args.seed_universe:
        ap.error("nothing to do: pass --phase1, --file or --seed-universe")

    conn = tsc.live_conn()
    try:
        for f in files:
            apply_file(conn, f)
        if args.seed_universe:
            seed_universe(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
