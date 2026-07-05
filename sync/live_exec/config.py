"""Live-execution config — single knob/secret surface for the d30so8c Binance bridge.

Reuses tsc._read_env() (the same .env parser the sync jobs use; special-char-safe) and the
scale-out economics constants from sync/donchian/scaleout.py so the live layer can NEVER drift
from the backtest it mirrors (FIRST_R / CLOSE_FRAC / RUNNER_CAP / HORIZON come from there).

Everything is fail-CLOSED: if real trading is armed (LIVE_TRADING_ENABLED=true and
EXEC_DRY_RUN=false) but the API keys are missing, load_cfg() hard-exits BEFORE any network
call so a misconfigured cron can never run blind.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))               # sync/live_exec -> _bootenv
sys.path.insert(0, str(_HERE.parents[1]))           # sync/          -> trade_sync_common
sys.path.insert(0, str(_HERE.parents[1] / "donchian"))  # sync/donchian -> scaleout
import _bootenv                                      # noqa: E402,F401  -- MUST precede the imports below
import trade_sync_common as tsc                      # noqa: E402
import scaleout as so                                # noqa: E402  (RUNNER_CAP read at import)
from ict import config as C                          # noqa: E402  (ENTRY_CONFIRM_BUF/ENTRY_AT_CONFIRM)

# Binance USDⓈ-M Futures REST. Mainnet by default; testnet base kept for the optional fallback.
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
class LiveCfg:
    # ---- master switches ----
    trading_enabled: bool          # LIVE_TRADING_ENABLED — master kill flag (false => both crons no-op)
    dry_run: bool                  # EXEC_DRY_RUN — compute + log intended orders, send NOTHING
    testnet: bool                  # BINANCE_TESTNET — point REST at the testnet base
    entry_mode: str                # LIVE_ENTRY_MODE — 'B' (confirmed ·0.5R) | 'A' (breakout-close LIMIT)
    # ---- secrets ----
    api_key: str
    api_secret: str
    base_url: str
    proxy: str                     # BINANCE_PROXY — optional egress proxy (geo-blocked runners)
    # ---- sizing / risk ----
    risk_usd: float                # RISK_PER_TRADE_USD — USD lost if the full position hits SL
    leverage: int                  # LEVERAGE — fixed fallback when auto_leverage is off
    auto_leverage: bool            # AUTO_LEVERAGE — per-trade leverage from the SL distance (risk-safe)
    leverage_max: int              # LEVERAGE_MAX — hard cap on the auto leverage
    margin_type: str               # MARGIN_TYPE — ISOLATED | CROSSED
    max_concurrent: int            # MAX_CONCURRENT_POSITIONS
    max_total_risk_usd: float      # MAX_TOTAL_RISK_USD — cap on summed open risk
    symbols: tuple[str, ...]       # EXEC_ENABLED_SYMBOLS (⊆ scaleout.SO_SYMBOLS)
    # ---- scale-out economics (mirrored from scaleout.py — never set by hand) ----
    confirm_buf: float             # ENTRY_CONFIRM_BUF (0.5)  — the ·0.5R directional buffer
    first_r: float                 # so.FIRST_R   (1.0)       — TP1, books close_frac
    close_frac: float              # so.CLOSE_FRAC (0.6)      — fraction booked at TP1
    runner_cap_r: float            # so.RUNNER_CAP (8.0)      — runner cap, in R0 (breakout-close risk)
    horizon_days: int              # so.HORIZON.days (3)      — whole-trade time limit
    expiry_min: int                # tsc.EXPIRY_MINUTES (180) — entry-fill window
    # ---- notify ----
    telegram_chat_id: str          # TELEGRAM_EXEC_CHAT_ID (falls back to TELEGRAM_CHAT_ID)
    # ---- multi-user (EXEC_MULTI_USER; identity fields set by cfg_for_user) ----
    multi_user: bool = False       # fan out over ict_trade.user_stream_settings instead of env keys
    user_id: str | None = None     # profiles.user_id of the account being driven (None = legacy env)
    user_email: str = ""
    is_canonical: bool = True      # legacy env == the owner: gates Telegram + trading_signals writeback

    @property
    def armed(self) -> bool:
        """True only when real orders may be sent (everything below dry-run is a no-op)."""
        return self.trading_enabled and not self.dry_run


def load_cfg() -> LiveCfg:
    env = {**os.environ, **tsc._read_env()}   # .env wins for secrets; process env for cron overrides

    trading_enabled = _b(env, "LIVE_TRADING_ENABLED", False)
    dry_run = _b(env, "EXEC_DRY_RUN", True)
    testnet = _b(env, "BINANCE_TESTNET", False)
    entry_mode = str(env.get("LIVE_ENTRY_MODE", "B")).strip().upper()
    if entry_mode not in ("A", "B"):
        raise SystemExit(f"LIVE_ENTRY_MODE must be A or B, got {entry_mode!r}")

    syms = [s.strip().upper() for s in str(env.get("EXEC_ENABLED_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT")).split(",") if s.strip()]
    bad = [s for s in syms if s not in so.SO_SYMBOLS]
    if bad:
        raise SystemExit(f"EXEC_ENABLED_SYMBOLS not in scaleout.SO_SYMBOLS: {bad}")

    # Keys are network-specific so testnet + mainnet creds can coexist in .env: flipping
    # BINANCE_TESTNET switches which pair is used (testnet-specific names win on testnet,
    # falling back to the generic BINANCE_API_KEY/SECRET if only one pair is present).
    if testnet:
        api_key = (env.get("BINANCE_TESTNET_API_KEY") or env.get("BINANCE_API_KEY") or "").strip()
        api_secret = (env.get("BINANCE_TESTNET_API_SECRET") or env.get("BINANCE_API_SECRET") or "").strip()
    else:
        api_key = (env.get("BINANCE_API_KEY") or "").strip()
        api_secret = (env.get("BINANCE_API_SECRET") or "").strip()

    cfg = LiveCfg(
        trading_enabled=trading_enabled,
        dry_run=dry_run,
        testnet=testnet,
        entry_mode=entry_mode,
        api_key=api_key,
        api_secret=api_secret,
        base_url=TESTNET_BASE if testnet else MAINNET_BASE,
        proxy=str(env.get("BINANCE_PROXY", "")).strip(),
        risk_usd=_f(env, "RISK_PER_TRADE_USD", 5.0),
        leverage=_i(env, "LEVERAGE", 3),
        auto_leverage=_b(env, "AUTO_LEVERAGE", False),
        leverage_max=_i(env, "LEVERAGE_MAX", 25),
        margin_type=str(env.get("MARGIN_TYPE", "ISOLATED")).strip().upper(),
        max_concurrent=_i(env, "MAX_CONCURRENT_POSITIONS", 3),
        max_total_risk_usd=_f(env, "MAX_TOTAL_RISK_USD", 15.0),
        symbols=tuple(syms),
        confirm_buf=float(getattr(C, "ENTRY_CONFIRM_BUF", 0.5)),
        first_r=float(so.FIRST_R),
        # EXEC-specific economics overrides (default to scaleout.py globals) — let the live bridge
        # run the d30so8f3h7 candidate (close_frac 0.3, cap8, 7d) WITHOUT touching any backtest global.
        close_frac=_f(env, "CLOSE_FRAC", float(so.CLOSE_FRAC)),
        runner_cap_r=_f(env, "RUNNER_CAP_R", float(so.RUNNER_CAP)),
        horizon_days=_i(env, "HORIZON_DAYS", int(so.HORIZON.days)),
        expiry_min=int(tsc.EXPIRY_MINUTES),
        telegram_chat_id=str(env.get("TELEGRAM_EXEC_CHAT_ID") or env.get("TELEGRAM_CHAT_ID") or "").strip(),
        multi_user=_b(env, "EXEC_MULTI_USER", False),
    )

    # fail-CLOSED: armed for real orders but no credentials -> stop before any network call.
    # Multi-user mode carries keys PER USER (cfg_for_user) — a keyless user is skipped with an
    # admin alert by the executor instead of hard-exiting the whole fleet.
    if cfg.armed and not cfg.multi_user and not (cfg.api_key and cfg.api_secret):
        raise SystemExit("LIVE_TRADING_ENABLED=true & EXEC_DRY_RUN=false but "
                         "BINANCE_API_KEY/SECRET are empty — refusing to run.")
    return cfg


def cfg_for_user(base: LiveCfg, u) -> LiveCfg:
    """Specialize the env-level cfg for one ExecUser (sync/users/store.py): their keys, their
    network, their risk/symbol knobs. Everything else (economics, entry mode, proxy, telegram)
    stays global so the live layer can never drift from the backtest it mirrors."""
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
        max_total_risk_usd=float(u.max_total_risk_usd),
        symbols=tuple(u.symbols),
        user_id=u.user_id,
        user_email=u.email,
        is_canonical=bool(u.is_canonical),
    )
