"""Kapanış raporu — bir pozisyon TAM kapandığında Telegram'a grafik + gerçek ROI gönderir.

Grafik: işlem penceresindeki mumlar + giriş / SL / TP1 / BE / cap yatay çizgileri +
giriş ve çıkış işaretleri. ROI: Binance'in KENDİ kayıtlarından (userTrades.realizedPnl,
userTrades.commission, income FUNDING_FEE) hesaplanan NET rakam — backtest R'ı değil.

⚠️ BEST-EFFORT: bu modüldeki HİÇBİR hata emir yönetimini etkilemez. `report_close`
her şeyi yutar (try/except) ve None döner. matplotlib yoksa sessizce no-op olur.
Bu yüzden gerçek-para executor'lerinden güvenle çağrılabilir.

Kullanım (executor'den, kapanış DB'ye yazıldıktan SONRA):
    import trade_report
    trade_report.report_close(client, cfg, pos, reason="cap", exit_px=64120.0,
                              realized_r=4.0, tag="OPUS · d30so8f3h7")
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))   # sync/ -> trade_sync_common
import trade_sync_common as tsc              # noqa: E402

# Renkler — uygulamanın koyu temasıyla aynı palet.
_BG = "#0b0e11"
_PANEL = "#12161c"
_TEXT = "#e8eaed"
_MUTED = "#848E9C"
_UP = "#0ECB81"
_DOWN = "#F6465D"
_GOLD = "#F5B942"
_BLUE = "#5C93FF"


def _enabled() -> bool:
    """EXEC_CLOSE_REPORT=false ile kapatılabilir (varsayılan AÇIK)."""
    env = tsc._read_env()
    v = str(env.get("EXEC_CLOSE_REPORT", os.environ.get("EXEC_CLOSE_REPORT", "true"))).strip().lower()
    return v not in ("0", "false", "no", "off")


# ------------------------------------------------------------------ Binance: gerçek para
def net_pnl(client, symbol: str, start_ms: int) -> dict:
    """Pozisyonun girişinden bu yana Binance'in kendi kayıtlarından NET sonuç.

    realized  : userTrades.realizedPnl toplamı (brüt, komisyon hariç)
    commission: userTrades.commission toplamı (POZİTİF = maliyet); USDT-dışı varlıkla
                ödendiyse (BNB indirimi) ayrıca `comm_other` altında raporlanır.
    funding   : income FUNDING_FEE toplamı (İŞARETLİ: <0 biz ödedik, >0 bize ödendi)
    net       = realized − commission(USDT) + funding
    """
    realized = commission = 0.0
    comm_other: dict[str, float] = {}
    for t in client.user_trades(symbol, limit=1000, start_ms=start_ms):
        realized += float(t.get("realizedPnl") or 0)
        c = float(t.get("commission") or 0)
        asset = str(t.get("commissionAsset") or "USDT").upper()
        if asset in ("USDT", "USDC"):
            commission += c
        elif c:
            comm_other[asset] = comm_other.get(asset, 0.0) + c

    funding = 0.0
    try:
        for r in client.income(symbol=symbol, income_type="FUNDING_FEE", start_ms=start_ms):
            funding += float(r.get("income") or 0)
    except Exception:  # noqa: BLE001 — funding en iyi çabadır; PnL'i bloklamasın
        pass

    return {"realized": realized, "commission": commission, "funding": funding,
            "net": realized - commission + funding, "comm_other": comm_other}


# ------------------------------------------------------------------ mumlar
def _interval_for(minutes: float) -> str:
    """İşlem süresine göre okunur bir mum aralığı (~60-400 mum hedefi)."""
    if minutes <= 6 * 60:
        return "1m"
    if minutes <= 48 * 60:
        return "5m"
    if minutes <= 10 * 24 * 60:
        return "15m"
    return "1h"


def _klines(symbol: str, t0: pd.Timestamp, t1: pd.Timestamp) -> pd.DataFrame:
    """İşlem penceresi + iki yana ~%18 dolgu. Boş DataFrame dönebilir (çağıran kontrol eder)."""
    span = max((t1 - t0).total_seconds() / 60.0, 5.0)
    pad = pd.Timedelta(minutes=max(span * 0.18, 3.0))
    a, b = t0 - pad, t1 + pad
    return tsc.fetch_klines(symbol, _interval_for(span),
                            int(a.timestamp() * 1000), int(b.timestamp() * 1000))


# ------------------------------------------------------------------ grafik
def render_chart(df: pd.DataFrame, pos: dict, *, reason: str, exit_px: float,
                 entry_t: pd.Timestamp, exit_t: pd.Timestamp, title: str) -> bytes:
    """Mum grafiği + seviye çizgileri + giriş/çıkış işaretleri -> PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")                       # headless — DISPLAY yok
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    long = str(pos["direction"]).lower() == "long"
    fig, ax = plt.subplots(figsize=(10.5, 5.6), dpi=110)
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_PANEL)

    # --- mumlar (gövde = bar, fitil = ince çizgi)
    x = mdates.date2num(df.index.to_pydatetime())
    w = (x[1] - x[0]) * 0.62 if len(x) > 1 else 0.0005
    for xi, (_, r) in zip(x, df.iterrows()):
        up = r["close"] >= r["open"]
        col = _UP if up else _DOWN
        ax.vlines(xi, r["low"], r["high"], color=col, linewidth=0.7, alpha=0.9)
        lo, hi = (r["open"], r["close"]) if up else (r["close"], r["open"])
        ax.add_patch(plt.Rectangle((xi - w / 2, lo), w, max(hi - lo, 1e-12),
                                   facecolor=col, edgecolor=col, linewidth=0.5))

    # --- seviye çizgileri (sadece mevcut olanlar)
    def _f(k):
        v = pos.get(k)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    entry_px = _f("eff_entry") or _f("entry_fill_px") or _f("signal_entry")
    sl_px = _f("eff_sl") or _f("signal_sl")
    levels = [
        ("Giriş", entry_px, _TEXT, "--"),
        ("SL", sl_px, _DOWN, "-"),
        ("TP1", _f("eff_tp1"), _UP, "-"),
        ("BE", _f("eff_be"), _MUTED, ":"),
        ("Cap", _f("eff_cap") or _f("signal_cap"), _UP, "--"),
    ]

    # y-aralığı MUMLARA (+ giriş/SL/çıkış) göre kurulur: uzaktaki cap (+8R) grafiği ezmesin.
    anchors = [df["low"].min(), df["high"].max()] + [p for p in (entry_px, sl_px, exit_px) if p]
    lo, hi = min(anchors), max(anchors)
    pad = max((hi - lo) * 0.08, hi * 1e-6)
    ylo, yhi = lo - pad, hi + pad
    ax.set_ylim(ylo, yhi)

    # Aynı fiyata düşen etiketleri birleştir (OPUS'ta BE == Giriş olur → üst üste binerdi).
    tol = (yhi - ylo) * 0.012
    merged: list[list] = []      # [price, [labels], color, linestyle]
    for label, price, col, ls in levels:
        if price is None:
            continue
        hit = next((m for m in merged if abs(m[0] - price) <= tol), None)
        if hit:
            hit[1].append(label)
        else:
            merged.append([price, [label], col, ls])

    for price, labels, col, ls in merged:
        text = f"{'·'.join(labels)} {price:g}"
        if ylo <= price <= yhi:
            ax.axhline(price, color=col, linestyle=ls, linewidth=1.0, alpha=0.85)
            ax.annotate(text, xy=(1.002, price), xycoords=("axes fraction", "data"),
                        color=col, fontsize=8, va="center", ha="left")
        else:
            # görünür aralığın dışında — kenarda ok ile belirt, ekseni bozma
            edge, arrow, va = (yhi, "↑", "top") if price > yhi else (ylo, "↓", "bottom")
            ax.annotate(f"{text} {arrow}", xy=(1.002, edge), xycoords=("axes fraction", "data"),
                        color=col, fontsize=8, va=va, ha="left", alpha=0.75)

    # --- giriş / çıkış işaretleri
    ex, xx = mdates.date2num(entry_t.to_pydatetime()), mdates.date2num(exit_t.to_pydatetime())
    epx = _f("entry_fill_px") or _f("eff_entry") or _f("signal_entry")
    if epx:
        ax.plot(ex, epx, marker="^" if long else "v", color=_GOLD, markersize=11,
                markeredgecolor=_BG, zorder=5)
    ax.plot(xx, exit_px, marker="X", color=_BLUE, markersize=12, markeredgecolor=_BG, zorder=5)

    # --- kozmetik
    ax.set_title(title, color=_TEXT, fontsize=11, fontweight="bold", pad=10, loc="left")
    ax.grid(color="#2a2f3a", linewidth=0.4, alpha=0.6)
    for s in ax.spines.values():
        s.set_color("#2a2f3a")
    ax.tick_params(colors=_MUTED, labelsize=8)
    # kısa işlemde tarih her tick'te tekrarlanmasın — gün bilgisi x-etiketinde
    span_days = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M" if span_days < 2 else "%d %b\n%H:%M"))
    if span_days < 2:
        d0, d1 = df.index[0], df.index[-1]
        rng = d0.strftime("%d %b %Y") if d0.date() == d1.date() else \
            f"{d0.strftime('%d %b')} → {d1.strftime('%d %b %Y')}"
        ax.set_xlabel(f"{rng} · UTC", color=_MUTED, fontsize=8)
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.subplots_adjust(left=0.06, right=0.88, top=0.91, bottom=0.12)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=_BG)
    plt.close(fig)
    return buf.getvalue()


# ------------------------------------------------------------------ paylaşım kartı
def _reticle(ax, cx, cy, r, color, alpha, aspect):
    """PUSU nişangâhı — iç içe halkalar + dört çeyrek çizgisi (marka motifi).

    Eksen kare DEĞİL (0..1 x 0..1, 1008×567 px), bu yüzden daire çizmek için y-yarıçapı
    `aspect` (= genişlik/yükseklik) ile ölçeklenir; yoksa elips gibi ezilir."""
    from matplotlib.patches import Ellipse
    for k, lw in ((1.0, 1.1), (0.66, 0.8), (0.30, 0.8)):
        ax.add_patch(Ellipse((cx, cy), width=2 * r * k, height=2 * r * k * aspect,
                             fill=False, ec=color, alpha=alpha, lw=lw))
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ax.plot([cx + dx * r * 0.78, cx + dx * r * 1.25],
                [cy + dy * r * 0.78 * aspect, cy + dy * r * 1.25 * aspect],
                color=color, alpha=alpha, lw=1.1, solid_capstyle="round")


def _sparkline(fig, df, pos, exit_px: float, acc: str):
    """İşlemin kendi fiyat yolu — kartın sağında, eksensiz mini grafik."""
    sax = fig.add_axes([0.575, 0.415, 0.38, 0.245])
    sax.set_axis_off()
    sax.patch.set_alpha(0)
    y = df["close"].to_numpy()
    x = range(len(y))
    epx = float(pos.get("entry_fill_px") or pos.get("eff_entry") or pos["signal_entry"])
    sax.axhline(epx, color=_MUTED, lw=0.7, ls="--", alpha=0.55)
    sax.plot(x, y, color=acc, lw=1.5, solid_capstyle="round")
    sax.fill_between(x, y, y.min(), color=acc, alpha=0.10)
    sax.plot(0, y[0], marker="o", ms=4.5, color=_GOLD, mec=_BG, mew=0.8)
    sax.plot(len(y) - 1, exit_px, marker="X", ms=7, color=_BLUE, mec=_BG, mew=0.8)
    pad = (y.max() - y.min()) * 0.18 or 1e-9
    sax.set_ylim(min(y.min(), epx, exit_px) - pad, max(y.max(), epx, exit_px) + pad)
    sax.set_xlim(-len(y) * 0.03, (len(y) - 1) * 1.03)   # uçtaki işaretler kırpılmasın


def render_card(pos: dict, *, reason: str, exit_px: float, realized_r, pnl: dict,
                roi, margin: float, entry_t: pd.Timestamp, exit_t: pd.Timestamp,
                tag: str, df: pd.DataFrame | None = None) -> bytes:
    """PUSU'ya özgün paylaşım kartı: taktik ızgara + nişangâh motifi, dev NET ROI,
    işlemin kendi fiyat yolu (sparkline) ve WAIT · TRAP · EXECUTE imzası.

    Not: NET ROI komisyon + funding düşülmüş cüzdan gerçeğidir (borsaların paylaşım
    kartlarındaki ROE brüttür)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    win = pnl["net"] >= 0
    acc = _UP if win else _DOWN
    long = str(pos["direction"]).lower() == "long"
    sym = pos["symbol"]
    epx = float(pos.get("entry_fill_px") or pos.get("eff_entry") or pos["signal_entry"])
    lev = int(pos.get("leverage") or 1) or 1

    fig = plt.figure(figsize=(7.2, 4.05), dpi=140)
    fig.patch.set_facecolor(_BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    # taktik ızgara (çok soluk altın) + sonuç parıltısı + nişangâh
    ASPECT = 7.2 / 4.05          # eksen kare değil — daireler bununla düzeltilir
    for i in range(1, 16):
        ax.axvline(i / 16, color=_GOLD, alpha=0.028, lw=0.6)
    for i in range(1, 10):
        ax.axhline(i / 10, color=_GOLD, alpha=0.028, lw=0.6)
    from matplotlib.patches import Ellipse
    for rr, aa in ((0.30, 0.045), (0.20, 0.04), (0.11, 0.035)):
        ax.add_patch(Ellipse((0.245, 0.545), width=2 * rr, height=2 * rr * ASPECT,
                             color=acc, alpha=aa, lw=0))
    _reticle(ax, 0.245, 0.545, 0.175, _GOLD, 0.085, ASPECT)

    # çerçeve + üst altın şerit
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, fill=False, ec="#2a2f3a", lw=1.4))
    ax.add_patch(plt.Rectangle((0, 0.986), 1, 0.014, color=_GOLD, lw=0))

    # marka
    ax.text(0.045, 0.895, "P U S U", color=_GOLD, fontsize=17, fontweight="bold", va="center")
    ax.text(0.047, 0.822, "L İ K İ D İ T E   A V I", color=_MUTED, fontsize=6.8, va="center")

    # sembol + yön/kaldıraç rozeti
    ax.text(0.955, 0.895, sym, color=_TEXT, fontsize=15, fontweight="bold", ha="right", va="center")
    bcol = _UP if long else _DOWN
    ax.text(0.955, 0.820, f"{'LONG' if long else 'SHORT'}  ·  {lev}x", color=bcol, fontsize=10,
            fontweight="bold", ha="right", va="center")

    # kahraman: NET ROI (sol) + net $ (sol alt)
    roi_txt = f"{roi:+.1f}%" if roi is not None else "—"
    ax.text(0.045, 0.605, roi_txt, color=acc, fontsize=50, fontweight="bold", va="center")
    ax.text(0.048, 0.455, f"{pnl['net']:+.2f}$", color=acc, fontsize=19, fontweight="bold",
            va="center", family="monospace")
    ax.text(0.185, 0.452, f"· marj {margin:.2f}$", color=_MUTED, fontsize=8.5, va="center")
    ax.text(0.048, 0.383, "NET ROI  ·  komisyon + funding dahil", color=_MUTED, fontsize=7.5,
            va="center")

    # işlemin fiyat yolu (sağ)
    if df is not None and not df.empty:
        try:
            _sparkline(fig, df, pos, exit_px, acc)
        except Exception:  # noqa: BLE001 — sparkline kozmetiktir, kartı düşürmesin
            pass

    ax.plot([0.045, 0.955], [0.322, 0.322], color="#2a2f3a", lw=1)

    # alt satır: giriş / çıkış / süre / sonuç
    cells = [
        ("GİRİŞ", f"{epx:g}"),
        ("ÇIKIŞ", f"{exit_px:g}"),
        ("SÜRE", _fmt_dur(exit_t - entry_t)),
        ("SONUÇ", f"{float(realized_r):+.2f}R" if realized_r is not None else reason),
    ]
    step = (0.955 - 0.045) / len(cells)
    for i, (lab, val) in enumerate(cells):
        x = 0.045 + i * step
        ax.text(x, 0.232, lab, color=_MUTED, fontsize=7.5, va="center")
        ax.text(x, 0.152, val, color=_TEXT, fontsize=12, fontweight="bold", va="center",
                family="monospace")

    # imza satırı
    foot = f"{reason} · {exit_t:%d.%m.%Y %H:%M} UTC" + (f"  —  {tag}" if tag else "")
    ax.text(0.045, 0.055, foot, color=_MUTED, fontsize=7.5, va="center")
    ax.text(0.955, 0.055, "WAIT · TRAP · EXECUTE", color=_GOLD, fontsize=7.5, alpha=0.75,
            fontweight="bold", ha="right", va="center")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=_BG)
    plt.close(fig)
    return buf.getvalue()


# ------------------------------------------------------------------ Telegram
def send_photo(png: bytes, caption: str, *, chat_id: str = "") -> bool:
    env = tsc._read_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat = chat_id or env.get("TELEGRAM_EXEC_CHAT_ID") or env.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print(f"  [report] telegram skipped (token/chat yok): {caption[:60]}")
        return False
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data={"chat_id": chat, "caption": caption[:1024], "parse_mode": "HTML"},
        files={"photo": ("trade.png", png, "image/png")}, timeout=30)
    if not r.ok:
        print(f"  [report] telegram sendPhoto error: {r.text[:180]}")
    return r.ok


def send_media_group(images: list[tuple[str, bytes]], caption: str, *, chat_id: str = "") -> bool:
    """Birden çok görseli TEK bildirimde yolla (caption ilk görselde). Başarısız olursa
    sırayla sendPhoto'ya düşer — kart yine de gider."""
    env = tsc._read_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat = chat_id or env.get("TELEGRAM_EXEC_CHAT_ID") or env.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print(f"  [report] telegram skipped (token/chat yok): {caption[:60]}")
        return False

    media, files = [], {}
    for i, (name, data) in enumerate(images):
        key = f"photo{i}"
        files[key] = (f"{name}.png", data, "image/png")
        item = {"type": "photo", "media": f"attach://{key}"}
        if i == 0:
            item["caption"] = caption[:1024]
            item["parse_mode"] = "HTML"
        media.append(item)

    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMediaGroup",
                          data={"chat_id": chat, "media": json.dumps(media)},
                          files=files, timeout=40)
        if r.ok:
            return True
        print(f"  [report] sendMediaGroup error: {r.text[:180]} — tek tek deneniyor")
    except Exception as e:  # noqa: BLE001
        print(f"  [report] sendMediaGroup exception: {e} — tek tek deneniyor")

    ok = False
    for i, (_, data) in enumerate(images):
        ok = send_photo(data, caption if i == 0 else "", chat_id=chat_id) or ok
    return ok


# ------------------------------------------------------------------ metin
def _fmt_dur(td: pd.Timedelta) -> str:
    m = int(td.total_seconds() // 60)
    d, m = divmod(m, 1440)
    h, m = divmod(m, 60)
    return (f"{d}g " if d else "") + (f"{h}s " if (h or d) else "") + f"{m}dk"


def roi_margin(pos: dict, pnl: dict) -> tuple[float, float | None]:
    """(başlangıç marjı, NET ROI %). Marj = giriş × qty / kaldıraç."""
    epx = float(pos.get("entry_fill_px") or pos.get("eff_entry") or pos["signal_entry"])
    qty = float(pos.get("qty") or 0)
    lev = int(pos.get("leverage") or 1) or 1
    margin = (epx * qty / lev) if (epx and qty) else 0.0
    return margin, ((pnl["net"] / margin * 100.0) if margin else None)


def build_caption(pos: dict, *, reason: str, exit_px: float, realized_r, pnl: dict,
                  entry_t: pd.Timestamp, exit_t: pd.Timestamp, tag: str) -> str:
    sym, direction = pos["symbol"], str(pos["direction"]).upper()
    epx = float(pos.get("entry_fill_px") or pos.get("eff_entry") or pos["signal_entry"])
    lev = int(pos.get("leverage") or 1) or 1
    margin, roi = roi_margin(pos, pnl)

    win = pnl["net"] >= 0
    emoji = "🟢" if win else "🔴"
    r_txt = f"{float(realized_r):+.2f}R" if realized_r is not None else "—"
    roi_txt = f"{roi:+.1f}%" if roi is not None else "—"

    lines = [
        f"{emoji} <b>KAPANDI</b> · <b>{sym}</b> {direction} #{pos.get('id', '?')}",
        f"Sebep: <b>{reason}</b> · Giriş {epx:g} → Çıkış {exit_px:g} ({_fmt_dur(exit_t - entry_t)})",
        f"Net: <b>{pnl['net']:+.2f}$</b> · ROI <b>{roi_txt}</b> · {r_txt}",
        f"<i>brüt {pnl['realized']:+.2f}$ · komisyon −{pnl['commission']:.2f}$ "
        f"· funding {pnl['funding']:+.2f}$</i>",
    ]
    if pnl["comm_other"]:
        extra = " · ".join(f"−{v:g} {a}" for a, v in pnl["comm_other"].items())
        lines.append(f"<i>komisyon (diğer varlık): {extra}</i>")
    lines.append(f"<i>marj {margin:.2f}$ · {lev}x</i>")
    if tag:
        lines.append(f"— {tag}")
    return "\n".join(lines)


# ------------------------------------------------------------------ giriş noktası
def report_close(client, cfg, pos: dict, *, reason: str, exit_px: float,
                 realized_r=None, tag: str = "", force: bool = False) -> bool:
    """Kapanış raporunu (grafik + net ROI) Telegram'a gönder. ASLA exception fırlatmaz.

    force=True: dry_run/kapalı bayrak kontrollerini atla (test scripti için).
    Döner: gönderildiyse True, aksi halde False.
    """
    try:
        if not force:
            if not _enabled():
                return False
            if getattr(cfg, "dry_run", False):
                return False   # dry-run'da gerçek dolum yok, ROI anlamsız

        exit_t = pd.Timestamp(pos.get("exit_time") or pd.Timestamp.now(tz="UTC"))
        entry_t = pd.Timestamp(pos.get("entry_fill_time") or pos.get("signal_time") or exit_t)
        if entry_t.tzinfo is None:
            entry_t = entry_t.tz_localize("UTC")
        if exit_t.tzinfo is None:
            exit_t = exit_t.tz_localize("UTC")
        if exit_t <= entry_t:
            exit_t = entry_t + pd.Timedelta(minutes=1)

        sym = pos["symbol"]
        # Binance'in kendi kayıtları — girişten 1dk öncesinden tara (dolum sınırı yuvarlaması)
        since_ms = int((entry_t - pd.Timedelta(minutes=1)).timestamp() * 1000)
        pnl = net_pnl(client, sym, since_ms)
        # MARKET kapanışının fill'i userTrades'e düşmemiş olabilir — bir kez daha dene.
        if pnl["realized"] == 0.0 and float(pos.get("qty") or 0) > 0:
            time.sleep(2.0)
            pnl = net_pnl(client, sym, since_ms)

        caption = build_caption(pos, reason=reason, exit_px=float(exit_px), realized_r=realized_r,
                                pnl=pnl, entry_t=entry_t, exit_t=exit_t, tag=tag)
        margin, roi = roi_margin(pos, pnl)
        chat = getattr(cfg, "telegram_chat_id", "")

        df = _klines(sym, entry_t, exit_t)
        has_bars = df is not None and not df.empty

        # 1) paylaşılabilir PUSU kartı (sparkline için mumları da alır)
        images: list[tuple[str, bytes]] = [
            ("pusu-sonuc", render_card(pos, reason=reason, exit_px=float(exit_px),
                                       realized_r=realized_r, pnl=pnl, roi=roi, margin=margin,
                                       entry_t=entry_t, exit_t=exit_t, tag=tag,
                                       df=df if has_bars else None)),
        ]
        # 2) seviye/fiyat grafiği — mum verisi yoksa yalnız kart gider
        if has_bars:
            title = (f"{tag or 'PUSU'} · {sym} {str(pos['direction']).upper()} "
                     f"#{pos.get('id', '?')} — {reason}")
            images.append(("grafik", render_chart(df, pos, reason=reason, exit_px=float(exit_px),
                                                  entry_t=entry_t, exit_t=exit_t, title=title)))
        else:
            print(f"  [report] {sym}: mum verisi yok — yalnız paylaşım kartı gönderiliyor")

        if len(images) == 1:
            return send_photo(images[0][1], caption, chat_id=chat)
        return send_media_group(images, caption, chat_id=chat)
    except Exception as e:  # noqa: BLE001 — rapor ASLA emir yönetimini bozmaz
        print(f"  [report] kapanış raporu atlandı ({pos.get('symbol', '?')}): {e}")
        return False
