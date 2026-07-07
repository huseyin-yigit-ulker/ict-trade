"""Faz-5 cutover ÖN-DOĞRULAMA — salt okunur, HİÇBİR emir göndermez, DB yazmaz.

Multi-user makinesinin (load_exec_users + cfg_for_user) owner hesabını doğru
çözdüğünü ve çözülen anahtarın .env'deki mainnet anahtarıyla birebir aynı olduğunu
kanıtlar. Cutover'dan ÖNCE çalıştır: her şey yeşilse flip güvenli.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sync"))
sys.path.insert(0, str(REPO / "sync" / "live_exec"))
sys.path.insert(0, str(REPO / "sync" / "users"))

import trade_sync_common as tsc      # noqa: E402
import config as cfgmod              # noqa: E402
import state as st                   # noqa: E402
import store as ustore              # noqa: E402

env = tsc._read_env()
base = cfgmod.load_cfg()
print(f"base cfg: multi_user={base.multi_user} armed={base.armed} "
      f"testnet={base.testnet} is_canonical={base.is_canonical}")
print(f".env mainnet key last4 = ...{env.get('BINANCE_API_KEY','')[-4:]}  "
      f"secret last4 = ...{env.get('BINANCE_API_SECRET','')[-4:]}")
print()

live = tsc.live_conn()
for stream in ("opus", "midas"):
    users = ustore.load_exec_users(live, stream)
    print(f"=== stream={stream}: {len(users)} kullanıcı-satırı yüklenir ===")
    for u in users:
        match = "✓ .env ile AYNI" if (stream == "opus" and u.network == "mainnet"
                                       and u.api_key == env.get("BINANCE_API_KEY", "")
                                       and u.api_secret == env.get("BINANCE_API_SECRET", "")) else ""
        print(f"  {u.email} · {stream}/{u.network} · risk=${u.risk_usd} "
              f"maxc={u.max_concurrent} canonical={u.is_canonical} "
              f"key=...{u.api_key[-4:]} sec=...{u.api_secret[-4:]} {match}")
        print(f"    semboller: {list(u.symbols)}")
        pos_table = "ict_trade.live_positions" if stream == "opus" else "ict_trade.midas_positions"
        open_states = (('PENDING_ENTRY', 'ENTRY_WORKING', 'OPEN_FULL', 'RUNNER', 'CLOSING')
                       if stream == "opus" else ('PENDING_ENTRY', 'ENTRY_WORKING', 'OPEN'))
        with live.cursor() as cur:
            cur.execute(f"select symbol, direction, state, entry_coid from {pos_table} "
                        f"where state = any(%s) order by symbol", (list(open_states),))
            rows = cur.fetchall()
        print(f"    şu an açık ({len(rows)}): "
              + (", ".join(f"{r[0]}/{r[1]}/{r[2]} coid={r[3]}" for r in rows) or "yok"))
live.close()
print("\nÖnizleme bitti (hiçbir emir gönderilmedi, DB yazılmadı).")
