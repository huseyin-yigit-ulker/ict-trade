# DONCHIAN — Teknik Strateji Raporu

*Trend/momentum stream — RANGE/MAIN ICT kitabının tamamlayıcısı*
*Paket: `sync/donchian/` · version=`donchian` · mode=`donchian` · Hazırlık: 2026-06-16*

---

## 1. Özet (Executive Summary)

DONCHIAN, mevcut ICT setimizin (MAIN/RANGE) yapısal olarak **zayıf olduğu güçlü-trend rejiminde** çalışan bir **Donchian(55) breakout** trend-takip stratejisidir. MAIN aslında bir RANGE/mean-reversion sistemidir (R'sinin ~%85-90'ı light-trend bandında, güçlü trendde başabaş–negatif). Literatür, mean-reversion bir kitabın klasik tamamlayıcısının bir **trend-takipçisi** olduğunu söyler — getirileri düşük/negatif korelasyonludur çünkü **birbirini dışlayan rejimlerde** para kazanırlar.

**Sonuç (özet):**
| Pencere | Toplam R | İşlem | WR | Durum |
|---|---|---|---|---|
| 2026 (Oca–Haz, 40 sembol) | **+288.1R** | 2353 | %23 | tam, DB'de (in-sample) |
| 2025 OOS (40 sembol) | **+662.1R** | 3151 | %25 | tam (out-of-sample) |
| 2024 OOS (40 sembol) | *(devam ediyor)* | — | — | BTC +75.9R |

Edge **out-of-sample'da daha da güçlü** (2025 +662R, 2026'nın iki katı) → 2026'ya özgü bir overfit değil.

---

## 2. Stratejinin mantığı — 3 katman

Strateji her 1h bar kapanışında şu sırayla karar verir:

```
her bar i için:
  risk = 2 * ATR(14)
  EĞER risk > 0  VE  ER(24) >= 0.35:            # (1) rejim kapısı
      taze yukarı kırılım?  → LONG               # (2) tetik
      taze aşağı kırılım?   → SHORT
      entry=close[i], SL=±risk, TP=±4*risk        # (3) geometri
```

### (1) Rejim kapısı — Kaufman Efficiency Ratio ≥ 0.35

```
ER = |close[i] - close[i-24]|  /  Σ|close[k] - close[k-1]|   (k = i-23..i)
```
- ER ≈ 1 → temiz, tek-yönlü trend
- ER ≈ 0 → ileri-geri gürültü (chop)

**ER < 0.35 ise bar atlanır.** Bu, donchian'ı yalnızca güçlü-trend rejiminde ateşler — MAIN'in zarar ettiği yer. ER-kovası kanıtı (trailing varyant, 5 sembol): chop −43R, light −21R, **güçlü>0.35 +122R** → kazancın tamamı MAIN'in kaybettiği rejimde.

### (2) Tetik — taze Donchian(55) kırılımı

Önceki **55 barın** (bu bar HARİÇ) ekstremleri:
```python
hi[i] = max(high[i-55 .. i-1])     # rolling(55).max().shift(1)
lo[i] = min(low [i-55 .. i-1])
```
| Yön | Koşul (taze kırılım) |
|---|---|
| LONG | `close[i] > hi[i]` **ve** `close[i-1] <= hi[i-1]` |
| SHORT | `close[i] < lo[i]` **ve** `close[i-1] >= lo[i-1]` |

"Taze" şartı (`close[i-1]` henüz kırmamış olmalı) sürekli breakout'ta **bir kez** ateşler, her barda değil.

### (3) Geometri — market entry, ATR stop, RR4 hedef

`risk = 2 × ATR(14)`:
| | LONG | SHORT |
|---|---|---|
| Entry | close[i] (market) | close[i] |
| SL | entry − risk | entry + risk |
| TP | entry + 4×risk | entry − 4×risk |

Sabit **RR = 4** (geniş hedef — trend-takibin "kayıpları kes, kazananları koştur" matematiği). RR=4, parametre taramasında seçildi (RR 2/3/4/5 → +45/+63/**+85**/+70R; 4 hem zirve hem her sembolde pozitif). Düşük WR (~%25) + büyük kazananlar = trend-takipçi imzası.

---

## 3. Look-ahead yok (nedensellik kanıtı)

İki yerde sızıntı olabilir; ikisi de denetlendi:

**Sinyal üretimi:** Kanal `.shift(1)` ile bu barı dışlar; ER/ATR geriye-dönük. **Ampirik kesme-testi:** geleceği kestiğimizde (df'nin %60'ı) 50 geçmiş sinyalin **50'si de birebir aynı** çıktı, 0 uyuşmazlık → gelecek barlar geçmiş kararı değiştirmiyor.

**Sonuç çözümü** ([trade_sync_common.py](../trade_sync_common.py)): entry/TP/SL yarışı `close_ts = signal_ts + 1h` (bar **kapanışı**) noktasından başlar ve 1m'de **yalnızca ileri** taranır. Aynı barın kendi geleceğiyle "dolduruldu" denmez. Eşitlikte (aynı 1m barda hem TP hem SL) → SL (kötümser).

---

## 4. DEMO — Gerçek bir 2026 sinyali (XAU LONG)

Aşağıdaki işlem backtest DB'sinden (`version='donchian'`) birebir alınmış, göstergeler o bardaki 1h veriden yeniden hesaplanmıştır.

### Adım 1 — Bar ve bağlam
**Sembol:** XAUUSDT · **Sinyal barı:** 2026-04-13 22:00 UTC (1h)

| Gösterge | Değer | Kapı |
|---|---|---|
| `close[i]` | **4758.63** | — |
| `close[i-1]` | 4742.95 | — |
| Önceki 55-bar zirvesi `hi[i]` | 4753.59 | `close[i] > hi[i]` → **4758.63 > 4753.59 ✓** |
| `hi[i-1]` | 4753.59 | `close[i-1] ≤ hi[i-1]` → **4742.95 ≤ 4753.59 ✓ (taze)** |
| ER(24) | **0.452** | `≥ 0.35` → **✓ güçlü trend** |
| ATR(14) | 16.22 | — |

→ Üç koşul da sağlandı: **güçlü trend + taze 55-bar yukarı kırılımı → LONG sinyali.**

### Adım 2 — İşlem nasıl açıldı (geometri)
```
risk = 2 × ATR = 2 × 16.22 = 32.44
Entry = close[i]          = 4758.63   (bar kapanışında market)
SL    = entry − risk      = 4726.19   (−1R, 32.44$ aşağıda)
TP    = entry + 4 × risk  = 4888.37   (+4R, 129.74$ yukarıda)
```
DB satırındaki entry/SL/TP: **4758.63 / 4726.19 / 4888.37** — formülle birebir aynı ✓

### Adım 3 — Çözüm (1m, ileri yön)
| Olay | Zaman | Fiyat |
|---|---|---|
| Sinyal barı kapandı | 2026-04-13 23:00 | — |
| **Entry dolduldu** | 2026-04-13 23:01 | 4758.63 |
| **TP'ye ulaşıldı** | 2026-04-17 13:14 | 4888.37 |

**Sonuç: closed_tp = +4.00R** (≈3.7 günde). Entry, bar kapanışından 1 dk sonra doldu (look-ahead yok); fiyat 4 gün boyunca trendde kalıp +4R hedefe yürüdü — tam da ER=0.45 kapısının yakalamayı amaçladığı güçlü-trend hareketi.

> Bu işlem stratejinin ideal senaryosudur: güçlü trend (yüksek ER) → 55-bar kırılımı → geniş hedef trendi yakalar. Düşük WR'li sistemde bu tek +4R kazanan, ~4 küçük −1R kaybedeni öder.

---

## 5. Canlı + backtest mimarisi

İki aşamalı, her ikisi de **aynı** `generate_signals()`'ı çağırır (parity):

| Aşama | Modül | Cron (VM) | İş |
|---|---|---|---|
| **Emit** | [canli.py](canli.py) | `1 * * * *` (saatlik) | yeni kapanan barda kırılım+ER kontrolü → `ict_trade.signals` (mode='donchian') + **DONCHIAN etiketli Telegram** |
| **Resolve** | [sync_daily.py](../sync_daily.py) | `30 0 * * *` (gecelik) | live sinyalleri 1m'de çöz → `trading_signals` (version='donchian') |

- **Emit** yalnızca kapanmış barlarda ateşler (yarım mum atılır), 1.5h lookback (kaçan koşuya dayanıklılık), `(symbol,signal_time,direction,mode)` üzerinde idempotent dedup.
- **Resolve** `ACTIVE_STREAMS=['donchian']` ile `--stream all` içinde çalışır; "bir gün geri" mantığıyla son 3 günü yeniden değerlendirir.

---

## 6. Sonuçlar

### 6.1 — 2026 tam evren (in-sample), 40 sembol
| Sınıf | İşlem | Net R | WR |
|---|---|---|---|
| Crypto (18) | 1386 | **+235.2** | %24 |
| Metal (XAU/XAG) | 208 | **+83.7** | %30 |
| Stock-perp (20) | 759 | **−30.8** | %20 |
| **TOPLAM** | 2353 | **+288.1** | %23 |

Trend edge'i crypto+metallerde güçlü; hisse-perp'lerde zayıf (gap-driven mikroyapı + küçük örneklem).

### 6.2 — 2025 OOS (out-of-sample), tam: **+662.1R** / 3151 işlem / WR %25
En güçlüler: ARB +93.9, NEAR +88.3, FET +67.7, ETH +57.4, AVAX +49.6, SOL +46.7, LINK +43.6, S +35.8, ADA +24.5, BTC +20.3. Negatifler: ONDO −36.0, ORDI −3.0, BNB −0.6. (DOGE +115.7 — yıla bağlı.)

### 6.3 — Sembol bazında iki-yıl tutarlılığı (2025 & 2026)
- **✓ Her iki yıl pozitif (14):** BTC, ETH, SOL, PEPE, WIF, SUI, NEAR, FET, ADA, S, ARB, XRP, AVAX, XAU → **güvenli çekirdek evren**
- **✗ Her iki yıl negatif (2):** ORDI (−3/−3), ONDO (−36/−10) → **budama adayı**
- **~ Karışık (3):** DOGE (+116/−6), LINK (+44/−4), BNB (−1/+4)

*(2024 OOS devam ediyor — BTC +75.9R ile üç-yıl pozitif; tamamlanınca tablo güncellenecek.)*

---

## 7. Reddedilen deney — donchian_ict (SL/TP'yi ICT'den almak)

"Sinyali Donchian'la üret, geometriyi başka algoritmayla seç" fikri test edildi (Donchian tetik + market entry sabit; SL/TP değişti):
- **B = swing SL + likidite TP:** likidite hedefi momentum'u boğuyor (~0.6 avgRR, WR %71/düşük R). Breakout yeni zirvede girdiği için "ters likidite" ya silinmiş ya çok yakın.
- **C = swing SL + RR4 TP:** 4-sembolde baseline'ı geçti (+68.7 vs +55.7) **ama tam 40 sembolde tersine döndü** (A +188.7R vs C **−81.1R**). Geniş swing-stop → çok uzak hedef → ulaşılamaz.

**Verdict:** baseline ATR2/RR4 doğru; donchian_ict shiplenmedi. **Ders:** bir geometri/gate'i tam evren + OOS olmadan asla shipleme — 4-sembol kazancı ölçekte −270R'ye dönebiliyor. (Script: [../../backtest/donchian_ict_bt.py](../../backtest/donchian_ict_bt.py))

---

## 8. Riskler ve uyarılar (lookahead DEĞİL)

1. **In-sample overfit:** parametreler (RR4/ER0.35/N55) kısmen 2026'ya bakılarak seçildi → 2025+2024 OOS bu riski test eder (şimdiye dek geçti).
2. **Slippage modellenmiyor:** entry = bar kapanış fiyatı; 1m resolver dolumu fiyat değmesine bağlar (hayali dolum yok) ama kayma yok → canlı R backtest'in biraz altında olur.
3. **Araştırma scriptleri 1h-çözümlü** (aynı barda TP+SL belirsizliği, tie→SL); shiplenen DB sayıları 1m (doğru).
4. **Hisse-perp'ler:** çoğu 2026 listelendi (küçük örneklem) + net negatif → budanmalı.

---

## 9. Parametreler ve dosyalar

| Parametre | Değer | Kaynak |
|---|---|---|
| Kanal | Donchian 55 (taze kırılım) | Turtle "slow" sistemi |
| Rejim kapısı | Kaufman ER(24) ≥ 0.35 | ER-kovası analizi |
| Stop | ATR(14) × 2 | — |
| Hedef | RR = 4 (sabit) | RR taraması (2/3/4/5) |
| Ücret | %0.1 round-trip | — |
| Evren | 40 sembol (çekirdek 5: BTC/ETH/SOL/XAU/XAG) | sync_daily.STATIC_SYMBOLS |

**Dosyalar:** `strategy.py` (ortak üreteç) · `backtest.py` (backfill→DB) · `canli.py` (live+Telegram) · `../../backtest/complement_bt.py` & `donchian_ict_bt.py` (araştırma)
