"""TALOS-ICHI live-execution config — single knob/secret surface for the gold (XAUUSDT) Binance bridge.

Reuses tsc._read_env() (the same .env parser the sync jobs use). All TALOS-ICHI knobs are namespaced
`TALOS_ICHI_*` so this executor coexists on ONE .env with the OPUS executor (which owns EXEC_*/RISK_*).
Shared master/network/secret switches (LIVE_TRADING_ENABLED, BINANCE_TESTNET, BINANCE_[TESTNET_]API_*,
BINANCE_PROXY, TELEGRAM_*) are read from the same keys both executors use.

Everything is fail-CLOSED: if TALOS-ICHI is armed for real orders (LIVE_TRADING_ENABLED=true AND
TALOS_ICHI_EXEC_ENABLED=true AND TALOS_ICHI_EXEC_DRY_RUN=false) but the API keys are missing, load_cfg()
hard-exits BEFORE any network call.

TESTNET-FIRST posture: BINANCE_TESTNET and TALOS_ICHI_EXEC_DRY_RUN both default TRUE, so a bare run is a
no-op intent logger against testnet until the operator explicitly flips them.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))           # sync/ -> trade_sync_common
import trade_sync_common as tsc                      # noqa: E402

# Binance USDⓈ-M Futures REST. Mainnet by default; testnet base kept for testnet-first validation.
MAINNET_BASE = "https://fapi.binance.com"
TESTNET_BASE = "https://testnet.binancefuture.com"


def _b(env: dict, key: str, default: bool) -> bool:
    return str(env.get(key, str(default))).strip().lower() in ("1", "true", "yes", "on")


def _f(env: dict, key: str, default: float) -> float:
    try:
        return float(env.get(key, default))
    except (TypeError, ValueError):
        return default


def _i(env: dict, key: str, default: int) -> int:
    try:
        return int(float(env.get(key, default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class MidasExecCfg:
    # ---- master switches ----
    trading_enabled: bool          # LIVE_TRADING_ENABLED — shared master kill (false => no-op)
    exec_enabled: bool             # TALOS_ICHI_EXEC_ENABLED — per-strategy arm (lets TALOS-ICHI run while OPUS is off)
    dry_run: bool                  # TALOS_ICHI_EXEC_DRY_RUN — compute + log intents, send NOTHING
    testnet: bool                  # BINANCE_TESTNET — point REST at the testnet base + testnet keys
    # ---- secrets ----
    api_key: str
    api_secret: str
    base_url: str
    proxy: str                     # BINANCE_PROXY — optional egress proxy (geo-blocked runners)
    # ---- instrument / sizing / risk ----
    symbol: str                    # TALOS_ICHI_SYMBOL (XAUUSDT)
    risk_usd: float                # TALOS_ICHI_RISK_PER_TRADE_USD — USD lost if the 1.5*ATR stop hits
    leverage: int                  # TALOS_ICHI_LEVERAGE — fixed fallback when auto_leverage is off/errors
    auto_leverage: bool            # TALOS_ICHI_AUTO_LEVERAGE — per-trade leverage from the SL distance
    leverage_max: int              # TALOS_ICHI_LEVERAGE_MAX — hard cap on the auto leverage (exchange max)
    # TARGET-MARGIN leverage (2026-07-08 owner request): the $ LOSS at the stop is fixed by qty
    # (= risk_usd/|entry-sl|) and NEVER depends on leverage. Leverage only sets margin + liquidation
    # distance. Since notional = risk_usd/slpct is pinned by the stop, margin = notional/L, so we pick
    # L = notional/target_margin to land the margin on this number ($10-20 band). Safe by construction:
    # target_margin > 2*risk_usd  =>  L < 0.5/slpct  =>  liquidation sits >2x the SL distance away.
    target_margin_usd: float       # TALOS_ICHI_TARGET_MARGIN_USD (0 = off, fall back to the cap)
    margin_type: str               # TALOS_ICHI_MARGIN_TYPE — ISOLATED | CROSSED
    max_concurrent: int            # TALOS_ICHI_MAX_CONCURRENT — hard 1 (also enforced by the unique index)
    # ---- entry (maker-first) ----
    maker_entry: bool              # TALOS_ICHI_MAKER_ENTRY — post-only LIMIT (GTX); false => MARKET (testnet only)
    entry_timeout_sec: int         # TALOS_ICHI_ENTRY_TIMEOUT_SEC — cancel an unfilled maker entry after this
    entry_max_slip_r: float        # TALOS_ICHI_ENTRY_MAX_SLIP_R — abandon if price ran this many R past the ref
    # maker→taker fallback (2026-07-08, pos#47 post-mortem): a pure-GTX entry only fills when price
    # comes back THROUGH the limit (adverse selection) — the runners we live off run away unfilled
    # and the trade is missed entirely (research: passive maker loses 40-60% of runners = half the
    # edge; taker book is +53.6R w/ the after-loss gate). After this many seconds unfilled, if price
    # is STILL within entry_max_slip_r, cancel the GTX and take MARKET. 0 = old pure-maker behavior.
    # Keep this STRICTLY between one cron period (60s) and entry_timeout_sec, with margin on BOTH
    # sides: at 60s the fallback window [created+60, deadline] is phase-locked to the 60s tick and a
    # few hundred ms of cron jitter can leave it with zero ticks inside (pos#1, 2026-07-08 — the
    # entry was cancelled having never reached the exchange). 45s gives the t+60s tick ~15s of slack.
    entry_taker_fallback_sec: int  # TALOS_ICHI_ENTRY_TAKER_FALLBACK_SEC — maker→taker fallback delay (0=off)
    # after-loss gate (2026-07-07 backtest, TALOS-ICHI.md): enter ONLY when the SAME fx-day's previous
    # SETTLED paper trade closed negative. 2026: 204tr +53.6R PF1.37 @taker vs full set +27.1R/1.09.
    # ⚠️ NOT a regime shield — 2024/2025 stay negative (softer); it's a fee-economics overlay only.
    after_loss_only: bool          # TALOS_ICHI_EXEC_AFTER_LOSS_ONLY — skip first-of-day / after-win signals
    # ---- trailing (mainnet resting-stop cancel/replace) ----
    sl_deadband_ticks: int         # TALOS_ICHI_SL_DEADBAND_TICKS — only replace the stop past this many ticks
    # ---- writeback / notify ----
    exec_version: str              # TALOS_ICHI_EXEC_VERSION — trading_signals tag (distinct from paper 'talos_ichi')
    exec_name: str                 # TALOS_ICHI_EXEC_NAME — Telegram prefix
    telegram_chat_id: str          # TELEGRAM_EXEC_CHAT_ID (falls back to TELEGRAM_CHAT_ID)
    # ---- multi-user (EXEC_MULTI_USER — same one cutover switch as OPUS; identity set by cfg_for_user) ----
    multi_user: bool = False       # fan out over ict_trade.user_stream_settings instead of env keys
    user_id: str | None = None     # profiles.user_id of the account being driven (None = legacy env)
    user_email: str = ""
    is_canonical: bool = True      # legacy env == the owner: gates Telegram + trading_signals writeback

    @property
    def armed(self) -> bool:
        """True only when real orders may be sent (everything else is a no-op / intent log)."""
        return self.trading_enabled and self.exec_enabled and not self.dry_run

    @property
    def symbols(self) -> tuple[str, ...]:
        return (self.symbol,)


def load_cfg() -> MidasExecCfg:
    env = {**os.environ, **tsc._read_env()}   # .env wins for secrets; process env for cron overrides

    trading_enabled = _b(env, "LIVE_TRADING_ENABLED", False)
    exec_enabled = _b(env, "TALOS_ICHI_EXEC_ENABLED", False)
    dry_run = _b(env, "TALOS_ICHI_EXEC_DRY_RUN", True)
    # TALOS-ICHI has its OWN network flag (default TRUE = testnet-first), independent of the shared
    # BINANCE_TESTNET that OPUS uses — so TALOS-ICHI can validate on testnet while OPUS trades mainnet on
    # the same .env. Flip TALOS_ICHI_BINANCE_TESTNET=false only when TALOS-ICHI graduates to mini-mainnet.
    testnet = _b(env, "TALOS_ICHI_BINANCE_TESTNET", True)

    # Keys are network-specific so testnet + mainnet creds coexist in .env: flipping BINANCE_TESTNET
    # switches which pair is used. STRICT separation (no cross-fallback): paper (testnet) uses ONLY the
    # testnet/paper key, live (mainnet) uses ONLY the mainnet/live key — the paper executor can never
    # borrow the real-money key, and vice-versa. Missing the required key => fail-closed below when armed.
    if testnet:
        api_key = (env.get("BINANCE_TESTNET_API_KEY") or "").strip()
        api_secret = (env.get("BINANCE_TESTNET_API_SECRET") or "").strip()
    else:
        api_key = (env.get("BINANCE_API_KEY") or "").strip()
        api_secret = (env.get("BINANCE_API_SECRET") or "").strip()

    cfg = MidasExecCfg(
        trading_enabled=trading_enabled,
        exec_enabled=exec_enabled,
        dry_run=dry_run,
        testnet=testnet,
        api_key=api_key,
        api_secret=api_secret,
        base_url=TESTNET_BASE if testnet else MAINNET_BASE,
        proxy=str(env.get("BINANCE_PROXY", "")).strip(),
        symbol=str(env.get("TALOS_ICHI_SYMBOL", "XAUUSDT")).strip().upper(),
        risk_usd=_f(env, "TALOS_ICHI_RISK_PER_TRADE_USD", 2.0),
        leverage=_i(env, "TALOS_ICHI_LEVERAGE", 5),
        auto_leverage=_b(env, "TALOS_ICHI_AUTO_LEVERAGE", False),
        leverage_max=_i(env, "TALOS_ICHI_LEVERAGE_MAX", 25),
        target_margin_usd=_f(env, "TALOS_ICHI_TARGET_MARGIN_USD", 0.0),
        margin_type=str(env.get("TALOS_ICHI_MARGIN_TYPE", "ISOLATED")).strip().upper(),
        max_concurrent=_i(env, "TALOS_ICHI_MAX_CONCURRENT", 1),
        maker_entry=_b(env, "TALOS_ICHI_MAKER_ENTRY", True),
        entry_timeout_sec=_i(env, "TALOS_ICHI_ENTRY_TIMEOUT_SEC", 120),
        entry_max_slip_r=_f(env, "TALOS_ICHI_ENTRY_MAX_SLIP_R", 0.25),
        entry_taker_fallback_sec=_i(env, "TALOS_ICHI_ENTRY_TAKER_FALLBACK_SEC", 45),
        after_loss_only=_b(env, "TALOS_ICHI_EXEC_AFTER_LOSS_ONLY", False),
        sl_deadband_ticks=_i(env, "TALOS_ICHI_SL_DEADBAND_TICKS", 2),
        exec_version=str(env.get("TALOS_ICHI_EXEC_VERSION", "tichix")).strip(),
        exec_name=str(env.get("TALOS_ICHI_EXEC_NAME", "TALOS-ICHI-X")).strip(),
        telegram_chat_id=str(env.get("TELEGRAM_EXEC_CHAT_ID") or env.get("TELEGRAM_CHAT_ID") or "").strip(),
        multi_user=_b(env, "EXEC_MULTI_USER", False),
    )

    # fail-CLOSED: armed for real orders but no credentials -> stop before any network call.
    # Multi-user mode carries keys PER USER (cfg_for_user) — a keyless user is skipped with an
    # admin alert by the executor instead of hard-exiting the whole fleet.
    if cfg.armed and not cfg.multi_user and not (cfg.api_key and cfg.api_secret):
        raise SystemExit("TALOS-ICHI armed (LIVE_TRADING_ENABLED=true & TALOS_ICHI_EXEC_ENABLED=true & "
                         "TALOS_ICHI_EXEC_DRY_RUN=false) but Binance API key/secret are empty — refusing to run.")
    return cfg


def cfg_for_user(base: MidasExecCfg, u) -> MidasExecCfg:
    """Specialize the env-level cfg for one ExecUser (sync/users/store.py): their keys, their
    network, their risk knobs. Everything else (symbol, maker entry, trailing deadband, telegram)
    stays global so the live layer can never drift from the paper strategy it mirrors. TALOS-ICHI users
    are hard-locked to testnet by the store (and the table CHECK), but this stays generic."""
    import dataclasses
    testnet = (u.network == "testnet")
    return dataclasses.replace(
        base,
        testnet=testnet,
        base_url=TESTNET_BASE if testnet else MAINNET_BASE,
        api_key=u.api_key,
        api_secret=u.api_secret,
        risk_usd=float(u.risk_usd),
        max_concurrent=int(u.max_concurrent),
        user_id=u.user_id,
        user_email=u.email,
        is_canonical=bool(u.is_canonical),
    )
