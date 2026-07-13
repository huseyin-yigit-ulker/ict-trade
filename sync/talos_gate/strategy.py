"""TALOS·4H ve TALOS-ICHI·4H — TALOS + YAVAŞ TREND-YÖNÜ KAPISI (XAUUSDT 1m).

BACKTEST-ONLY araştırma akışları (executor YOK, canlı emit YOK).

FİKİR. Araştırma (2026-07-13, scratchpad/gold_confluence/) "OPUS ve TALOS aynı yönde sinyal
verdiğinde işlem aç" konfluans sorusuyla başladı ve şuraya vardı: OPUS'un kattığı bilgi
zamanlama değil, YAVAŞ YÖN. Ve o yönü OPUS'un makinesinden (ER kapısı + 4h confirm +
confirm-fill) çok daha temiz taşıyan sade bir ölçü var:

    4h Donchian(55) ORTA-ÇİZGİSİNİN hangi tarafındayız?
      close > mid  ->  yalnız LONG'a izin
      close < mid  ->  yalnız SHORT'a izin

TALOS derin Keltner-bandı çekilmesiyle girer; bu bazen büyük trende karşı "düşen bıçak"
yakalamak demektir. Kapı tam olarak o popülasyonu eler.

İKİ AKIŞ:
  talos_dg   TALOS + 4h kapı                  — toplam R şampiyonu (daha çok işlem, daha çok R)
  talos_kdg  TALOS + Kumo ∧ 4h kapı (İKİSİ)  — kalite/hayatta-kalma şampiyonu (aday)

NO-LOOKAHEAD. Kapı 4h barlarından türer: label='right'/closed='right' (değer ancak bar KAPANINCA
doğar), Donchian orta-çizgisi .shift(1) ile CARİ barı dışlar, 1m'ye yalnız ffill ile taşınır
(gelecek bar asla geçmişe sızmaz). Sinyal kararı 1m bar KAPANIŞINDA, dolum SONRAKİ bar açılışında.

SEMANTİK NOTU (kritik — bkz. scratchpad/gold_confluence/kumo_diff.py). Bir filtreyi bu motora
uygulamanın İKİ yolu var:
  PRE  = `side` dizisini maskele, walk'ı koş        <- CANLI KOD BUNU YAPAR (canli.py + executor)
  POST = TALOS'un hazır kitabından uymayanı at      <- talos_ichi'nin ship gerekçesi bunu ölçmüştü
Motor TEK-POZİSYONLU olduğu için ikisi AYNI ŞEY DEĞİL: PRE'de elenen sinyal motoru boş bırakır ve
TALOS'un hiç girmediği "doğan" işlemler kitaba girer. Bu modül canlı-sadık olsun diye PRE kullanır
(XAU'da iki semantik pratikte aynı: 4h kapı POST +75.5R / PRE +106.7R, Kumo∧4h POST +101.5R /
PRE +105.2R — kapıda işaret değişmiyor; Kumo'da değişiyordu).
"""
from __future__ import annotations
import sys
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))                 # sync/ -> trade_sync_common

# TALOS-ICHI'yi (o da TALOS'u, o da MIDAS motorunu) benzersiz adla yükle — her paketin dosyası
# strategy.py; statik import yanlış modülü yakalar.
_spec = importlib.util.spec_from_file_location(
    "talos_ichi_strategy_g", _HERE.parents[1] / "talos_ichi" / "strategy.py")
TI = importlib.util.module_from_spec(_spec)
sys.modules["talos_ichi_strategy_g"] = TI                 # dataclass modülün kayıtlı olmasını ister
_spec.loader.exec_module(TI)
T = TI.T                                                  # TALOS (Keltner) yüzeyi
MS = TI.MS                                                # MIDAS motoru (walk / atr / seans)

SYMBOL = T.SYMBOL                                         # XAUUSDT

# ---- TALOS konfigürasyonu birebir devralınır ----
COST_RT = T.COST_RT
TRAIL_MULT = T.TRAIL_MULT
MAX_HOLD_MIN = T.MAX_HOLD_MIN
TP_REF_MULT = T.TP_REF_MULT
ATR_INIT_MULT = T.ATR_INIT_MULT

# ---- yavaş trend kapısı ----
GATE_TF = "4h"        # plato: 2h/4h/8h hepsi çalışır (bkz. karne); 4h ortada
GATE_N = 55           # plato: 30..90 hepsi çalışır; 55 OPUS'tan miras (a-priori seçim)

# Paylaşılan motor yüzeyi (MIDAS/TALOS ile birebir aynı semantik)
load_1m = MS.load_1m
add_market_open = MS.add_market_open
atr_tf = MS.atr_tf
Trade = MS.Trade
walk = MS.walk


def trend_gate(df: pd.DataFrame, tf: str = GATE_TF, n: int = GATE_N) -> np.ndarray:
    """4h Donchian(n) orta-çizgisinin hangi tarafındayız: +1 (yalnız LONG) / -1 (yalnız SHORT) / 0.

    No-lookahead: label='right'+closed='right' => bir 4h barın değeri ancak KAPANDIKTAN sonra
    görünür; orta-çizgi .shift(1) ile cari barı dışlar; 1m'ye taşıma yalnız ffill (geçmişe bakar).
    """
    g = df.resample(tf, label="right", closed="right").agg(
        {"high": "max", "low": "min", "close": "last"}).dropna()
    mid = ((g["high"].rolling(n).max() + g["low"].rolling(n).min()) / 2).shift(1)
    d = np.sign(g["close"] - mid)
    return d.reindex(df.index, method="ffill").fillna(0).to_numpy()


def kumo_gate(df: pd.DataFrame) -> np.ndarray:
    """Ichimoku Kumo rengini yön kapısına çevir: yeşil bulut=+1 (yalnız LONG), kırmızı=-1, yok=0."""
    sa, sb = TI.ichimoku_kumo(df)
    sa, sb = sa.to_numpy(), sb.to_numpy()
    d = np.zeros(len(sa))
    ok = np.isfinite(sa) & np.isfinite(sb)
    d[ok & (sa > sb)] = 1.0
    d[ok & (sa < sb)] = -1.0
    return d


def signals(df: pd.DataFrame, atr: pd.Series | None = None, *, mode: str = "dg"):
    """TALOS (side, stop) + yön kapısı maskesi (PRE semantiği — canlı kodun yaptığı).

    mode='dg'  -> yalnız 4h trend kapısı
    mode='kdg' -> Kumo ∧ 4h kapı (İKİSİ de aynı yönü göstermeli; biri 0/uyumsuzsa sinyal düşer)
    """
    if atr is None:
        atr = atr_tf(df)
    side, stop = T.signals(df, atr)                       # ham TALOS Keltner sinyalleri
    g = trend_gate(df)
    if mode == "kdg":
        gk = kumo_gate(df)
        agree = (gk != 0) & (gk == g)                     # fail-closed: bulut yoksa sinyal yok
        g = np.where(agree, g, 0.0)
    elif mode != "dg":
        raise ValueError(f"unknown mode: {mode!r}")
    drop = (g == 0) | (np.sign(side) != g)
    side = side.copy(); stop = stop.copy()
    side[drop] = 0
    stop[drop] = np.nan
    return side, stop


def generate_trades(start: pd.Timestamp, end: pd.Timestamp, *, mode: str = "dg", cost=COST_RT):
    """Uçtan uca: 1m çek, seans maskele, kapılı sinyalleri üret, MIDAS walk -> kapanmış işlemler."""
    # 14g warmup: 4h Donchian(55) = 55×4h ≈ 9.2 takvim günü (+shift(1)); Ichimoku 15m 52/26 çok daha
    # kısa. XAU vadeli verisi 2025-12-11'de başlar, backfill 2026-01-01'den => 21 gün pay var.
    df = load_1m(start - pd.Timedelta(days=14), end)
    if df.empty:
        return []
    df = add_market_open(df)
    atr = atr_tf(df)
    side, stop = signals(df, atr, mode=mode)
    trades = walk(df, side, stop, atr.to_numpy(), cost=cost, trail=TRAIL_MULT,
                  max_hold=MAX_HOLD_MIN)
    return [t for t in trades if t.entry_time >= start]
