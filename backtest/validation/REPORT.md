# BTC/ETH Canlı Sinyal → Backtest Doğrulama Raporu

**Tarih:** 2026-06-04  ·  **Kapsam:** `ict_trade.signals` (canlı Supabase) — yalnız BTCUSDT & ETHUSDT
**Toplam satır:** 307 (BTC 157, ETH 150)  ·  **Sinyal tarih aralığı:** 2026-02-07 → 2026-05-23

---

## 0. Yöntem (özet)

- **Veri:** Binance Futures klines yeniden çekildi (1h: parite, 15m: TP/SL sonucu). Geçmiş OHLCV değişmez, bu yüzden sinyal anındaki veriyle birebir.
- **Parite ("backtest'te de oluşuyor mu?"):** Her sinyal için DAG'ın yaptığının aynısı — sinyal barında biten 6000 barlık pencerede backtest motoru ([B,C,D,E] üretim seti) yeniden çalıştırıldı. Yön + entry/SL/TP rel. tol. 1e-4 ile eşleşiyorsa **reproduced**.
- **TP/SL sonucu:** 15m bar üzerinde ileri yürüyüş. Limit entry 180 dk içinde dolmazsa `expired`; entry dolmadan TP/SL'e değerse `invalidated`; dolduktan sonra TP→`tp_hit`, SL→`sl_hit`. Aynı barda ikisi de → SL (temkinli).
- **Çapraz kontrol:** 15m sonuç simülasyonu, motorun kendi 1h backtester'ı ile karşılaştırıldı (aşağıda).

---

## 1. ⚠️ Kritik bulgu: tablo karışık kökenli

`ict_trade.signals` tek bir sistemin çıktısı değil — BTC/ETH için **4 farklı pipeline kuşağı** var. "Backtest'te de oluşuyor mu" sorusu yalnızca mevcut motorun yazdığı satırlar için anlamlı.

| mode | adet | tarih | timeframe | saat-başı ts | strateji alanı | parite |
|---|---|---|---|---|---|---|
| **live** | **37** | 09–23 May | **1h / 4h** | 37/37 ✅ | dolu ✅ | **uygulanabilir** |
| Weekday | 85 | 23 Şub–08 May | 30m / 2h | 0/85 | boş | yok (farklı TF) |
| Weekend | 61 | 22 Şub–09 May | 15m / 4h | 0/61 | boş | yok (farklı TF) |
| (NULL) | 124 | 07–22 Şub | — | 0/124 | boş | yok (eski sistem) |

- Yalnız **37 `mode='live'`** satır mevcut `dag/dag.py` motorundan (backtest motorunun birebir aynası).
- Diğer 270 satır eski/farklı timeframe'li (15m/30m) pipeline'lardan; `signal_time` bar sınırı değil insert duvar-saati, `strategy/confluence` boş, fiyatlar farklı SL/TP mantığı. 1h backtest bunları **üretmez (ve üretmemeli)** — 0/270 çıkması beklenen sonuç, motor hatası değil.

> Not: `.env`'deki ayrı **BACKTESTING** Supabase projesi (`fytkftgyxjhnndwiiioq` / `ict_trade.trading_signals`) artık erişilemiyor ("tenant/user not found" — duraklatılmış/silinmiş). Bu yüzden doğrulama, depodaki backtest motoru geçmiş veride yeniden koşturularak yapıldı.

---

## 2. Parite sonucu — "backtest'te de oluşuyor mu?"

Mevcut motorun yazdığı 37 sinyalin **tamamı** backtest'te birebir oluşuyor:

| | BTC | ETH | Toplam |
|---|---|---|---|
| `live` sinyal | 21 | 16 | 37 |
| backtest'te yeniden üretildi (entry/SL/TP birebir) | 21 | 16 | **37** |
| parite oranı | %100 | %100 | **%100** |

**Çift yönlü kontrol (ters kapsama):** Canlı sistemin aktif olduğu pencerede (09–23 May) backtest motoru tam **21 BTC + 16 ETH = 37** sinyal üretti; canlı sistem de tam bu 37'yi yazmış → **0 kaçırılan, 0 fazladan**. Yani bu pencerede canlı ≡ backtest.

Eşleşmelerde maksimum göreli entry/SL/TP farkı `~1e-9` düzeyinde (kayan nokta) — değerler aynı.

---

## 3. TP/SL sonuçları

### 3a. Mevcut motor (`mode='live'`, 37 sinyal) — temiz örneklem

| segment | n | TP | SL | invalid | expired | kapanan | kazanma | toplam R | beklenti |
|---|---|---|---|---|---|---|---|---|---|
| BTC live | 21 | 0 | 5 | 8 | 8 | 5 | 0.0% | -5R | -1.000R |
| ETH live | 16 | 0 | 5 | 3 | 8 | 5 | 0.0% | -5R | -1.000R |
| **Tümü live** | 37 | 0 | 10 | 11 | 16 | 10 | 0.0% | -10R | -1.000R |

> Bu pencerede (sadece 2 hafta, 10 kapanan işlem) hiç TP gelmedi; çoğu sinyal ya hiç dolmadı (`expired`) ya da dolmadan geçti (`invalidated`). **Örneklem çok küçük — istatistiksel anlamı sınırlı.** Önemli olan: motorun kendi 1h backtester'ı da aynı sonucu veriyor (aşağı), yani bu bir simülasyon artefaktı değil, o 2 haftanın gerçek sonucu.

**Çapraz kontrol (15m sim ↔ motorun 1h backtester'ı, 37 live sinyal):**

| | expired | invalidated | sl_hit | tp_hit |
|---|---|---|---|---|
| 15m simülasyonum | 16 | 11 | 10 | 0 |
| motorun 1h backtester'ı | 16 | 10 | 11 | 0 |

Fark tek bir sinyalde (15m vs 1h çözünürlükte entry'nin SL'den önce dolup dolmaması) — yöntem tutarlı.

### 3b. Eski pipeline satırları (270) — yalnız bilgi amaçlı, YAKLAŞIK

Bu satırlar farklı timeframe/farklı sistemden; orijinal entry-expiry semantiği bilinmiyor, 15m üzerinde ortak kuralla yaklaşık simüle edildi. Parite uygulanamaz.

| segment | n | TP | SL | invalid | expired | kapanan | kazanma | toplam R | beklenti |
|---|---|---|---|---|---|---|---|---|---|
| mode=Weekday | 85 | 19 | 44 | 16 | 6 | 63 | 30.2% | -6R | -0.095R |
| mode=Weekend | 61 | 14 | 31 | 14 | 2 | 45 | 31.1% | -3R | -0.067R |
| mode=<null> | 124 | 28 | 49 | 40 | 7 | 77 | 36.4% | +7R | +0.091R |
| **Tüm eski** | 270 | 61 | 124 | 70 | 15 | 185 | 33.0% | -2R | -0.011R |

### 3c. Sembol geneli (307 satırın tamamı, karışık köken)

| segment | n | TP | SL | invalid | expired | kapanan | kazanma | toplam R | beklenti |
|---|---|---|---|---|---|---|---|---|---|
| BTC (tüm) | 157 | 34 | 66 | 41 | 16 | 100 | 34.0% | +2R | +0.020R |
| ETH (tüm) | 150 | 27 | 68 | 40 | 15 | 95 | 28.4% | -14R | -0.147R |
| **BTC+ETH** | 307 | 61 | 134 | 81 | 31 | 195 | 31.3% | -12R | -0.062R |

---

## 4. 37 canlı sinyalin tek tek dökümü

| # | sembol | zaman (UTC) | yön | strateji | entry | SL | TP | parite | sonuç | R |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | BTC | 2026-05-09 18:00 | long | D_silver_bullet | 80571.05 | 80520.90 | 81472.96 | ✅ üretildi | expired | — |
| 2 | BTC | 2026-05-10 14:00 | long | D_silver_bullet | 80417.50 | 80362.05 | 80630.55 | ✅ üretildi | invalidated | — |
| 3 | BTC | 2026-05-10 18:00 | long | D_silver_bullet | 81065.50 | 80933.98 | 81680.60 | ✅ üretildi | sl_hit | -1.00 |
| 4 | BTC | 2026-05-11 18:00 | long | D_silver_bullet | 81259.25 | 81137.77 | 82460.50 | ✅ üretildi | expired | — |
| 5 | BTC | 2026-05-12 18:00 | short | D_silver_bullet | 80955.25 | 81056.08 | 79429.56 | ✅ üretildi | expired | — |
| 6 | BTC | 2026-05-13 12:00 | short | B_power_of_three | 81208.20 | 81337.67 | 80364.50 | ✅ üretildi | invalidated | — |
| 7 | BTC | 2026-05-13 13:00 | short | B_power_of_three | 81208.20 | 81344.69 | 80364.50 | ✅ üretildi | invalidated | — |
| 8 | BTC | 2026-05-13 14:00 | short | D_silver_bullet | 80380.30 | 80519.42 | 79801.00 | ✅ üretildi | invalidated | — |
| 9 | BTC | 2026-05-13 18:00 | short | D_silver_bullet | 80380.30 | 80533.39 | 79801.00 | ✅ üretildi | invalidated | — |
| 10 | BTC | 2026-05-14 14:00 | short | D_silver_bullet | 80951.85 | 81189.93 | 79033.34 | ✅ üretildi | sl_hit | -1.00 |
| 11 | BTC | 2026-05-16 14:00 | short | D_silver_bullet | 78750.00 | 78953.32 | 77477.69 | ✅ üretildi | expired | — |
| 12 | BTC | 2026-05-16 18:00 | short | D_silver_bullet | 78750.00 | 78954.22 | 77459.66 | ✅ üretildi | expired | — |
| 13 | BTC | 2026-05-17 14:00 | short | D_silver_bullet | 78228.95 | 78328.86 | 77638.60 | ✅ üretildi | expired | — |
| 14 | BTC | 2026-05-17 18:00 | short | D_silver_bullet | 78228.95 | 78326.76 | 77638.60 | ✅ üretildi | sl_hit | -1.00 |
| 15 | BTC | 2026-05-18 14:00 | short | composite | 77084.50 | 77331.39 | 75286.70 | ✅ üretildi | expired | — |
| 16 | BTC | 2026-05-18 18:00 | short | composite | 77084.50 | 77335.23 | 75273.50 | ✅ üretildi | sl_hit | -1.00 |
| 17 | BTC | 2026-05-21 14:00 | short | D_silver_bullet | 77466.40 | 77663.26 | 76485.00 | ✅ üretildi | sl_hit | -1.00 |
| 18 | BTC | 2026-05-22 14:00 | short | D_silver_bullet | 77304.55 | 77405.98 | 76696.70 | ✅ üretildi | invalidated | — |
| 19 | BTC | 2026-05-22 18:00 | short | D_silver_bullet | 77040.20 | 77152.06 | 76014.20 | ✅ üretildi | invalidated | — |
| 20 | BTC | 2026-05-23 14:00 | short | D_silver_bullet | 75869.00 | 75946.66 | 74695.83 | ✅ üretildi | expired | — |
| 21 | BTC | 2026-05-23 18:00 | short | D_silver_bullet | 76634.15 | 76781.97 | 76014.20 | ✅ üretildi | invalidated | — |
| 22 | ETH | 2026-05-09 18:00 | long | D_silver_bullet | 2325.98 | 2322.62 | 2351.29 | ✅ üretildi | sl_hit | -1.00 |
| 23 | ETH | 2026-05-10 14:00 | long | D_silver_bullet | 2325.08 | 2323.01 | 2337.79 | ✅ üretildi | invalidated | — |
| 24 | ETH | 2026-05-10 18:00 | long | D_silver_bullet | 2353.07 | 2348.59 | 2390.41 | ✅ üretildi | sl_hit | -1.00 |
| 25 | ETH | 2026-05-12 18:00 | short | D_silver_bullet | 2298.26 | 2303.89 | 2240.95 | ✅ üretildi | expired | — |
| 26 | ETH | 2026-05-13 13:00 | short | B_power_of_three | 2317.89 | 2309.72 | 2271.60 | ✅ üretildi | invalidated | — |
| 27 | ETH | 2026-05-13 14:00 | short | D_silver_bullet | 2292.77 | 2301.16 | 2230.10 | ✅ üretildi | expired | — |
| 28 | ETH | 2026-05-13 18:00 | short | D_silver_bullet | 2292.77 | 2301.52 | 2230.10 | ✅ üretildi | expired | — |
| 29 | ETH | 2026-05-14 14:00 | short | D_silver_bullet | 2292.77 | 2301.20 | 2235.03 | ✅ üretildi | sl_hit | -1.00 |
| 30 | ETH | 2026-05-17 14:00 | short | D_silver_bullet | 2202.03 | 2209.74 | 2167.83 | ✅ üretildi | expired | — |
| 31 | ETH | 2026-05-17 18:00 | short | D_silver_bullet | 2202.03 | 2209.62 | 2169.69 | ✅ üretildi | expired | — |
| 32 | ETH | 2026-05-18 14:00 | short | D_silver_bullet | 2131.58 | 2136.09 | 2085.00 | ✅ üretildi | expired | — |
| 33 | ETH | 2026-05-18 18:00 | short | D_silver_bullet | 2114.38 | 2122.07 | 2085.00 | ✅ üretildi | invalidated | — |
| 34 | ETH | 2026-05-19 14:00 | short | D_silver_bullet | 2125.55 | 2132.63 | 2074.26 | ✅ üretildi | expired | — |
| 35 | ETH | 2026-05-19 18:00 | short | D_silver_bullet | 2125.55 | 2132.55 | 2074.26 | ✅ üretildi | expired | — |
| 36 | ETH | 2026-05-21 14:00 | short | D_silver_bullet | 2122.68 | 2129.06 | 2101.79 | ✅ üretildi | sl_hit | -1.00 |
| 37 | ETH | 2026-05-23 14:00 | short | D_silver_bullet | 2067.03 | 2069.39 | 2020.52 | ✅ üretildi | sl_hit | -1.00 |

---

## 5. Sonuç

1. **Parite kanıtlandı.** Mevcut canlı motorun yazdığı 37 BTC/ETH sinyalinin %100'ü backtest'te birebir (entry/SL/TP) oluşuyor; ters yönde de backtest'in o penceredeki tüm sinyalleri canlıda mevcut. Canlı motor ≡ backtest motoru, gerçek kayıtlı sinyaller üzerinde doğrulandı.
2. **Veri hijyeni sorunu.** Tablodaki 307 satırın 270'i eski/farklı-timeframe pipeline'lardan; bunları mevcut backtest ile karşılaştırmak elma-armut. İleride canlı sinyalleri sürüm/`mode` ile ayırmak (ya da ayrı tablo) doğrulamayı temiz tutar.
3. **TP/SL.** Temiz örneklemde (37 live) 2 haftada kazanç yok ama örneklem çok küçük; motorun kendi backtester'ı aynı sonucu doğruluyor. Karışık 307'lik kümede kazanma ~%31, beklenti ~ -0.06R (yaklaşık, eski satırlar dahil).

**Üretilen dosyalar:** `out/btc_eth_signal_validation.csv` (307 satır, sinyal-bazında tüm alanlar), `analyze.py`, `check.py`.