# ICT-Trade — Strateji Geçmişi, Sonuçları ve Yorum Raporu

**Tarih:** 2026-06-14
**Kapsam:** Bugüne kadar denenen, kaldırılan ve duran tüm strateji/akım (stream) ve varyantları; in-sample (2026) ve out-of-sample (2025) sonuçları; yorum ve dersler.

---

## 0. Yönetici Özeti

20'den fazla strateji/varyant denendi. **Tek ve en önemli bulgu:** in-sample (2026) sonuçlar neredeyse tüm stratejilerde pozitifti, ama **out-of-sample (2025) testi neredeyse hepsini eledi** — sadece **RANGE ailesi** OOS-pozitif kaldı.

> **Tek cümle:** ICT setimiz pratikte bir **range / ortalamaya-dönüş (mean-reversion)** sistemidir; edge **gerçek range rejimindedir**; trend/momentum tarafında kalıcı bir edge yoktur. Para kazandıran şey stratejinin karmaşıklığı değil, **doğru rejim filtresidir.**

**Bugünkü "hayatta kalan" set — OOS-pozitif "range kitabı" (3 stream):**

| Stream | 2026 (in-sample) | 2025 (OOS) | Karar |
|---|---|---|---|
| **range** (RANGE_DEV fade) | +60.7R | **+9.2R** | TUT |
| **range_q** (RANGE+) | +49.6R | **+26.2R** | TUT — üretim adayı |
| **v2_light_r** (ICT·Light·Range) | +30.0R | **+15.5R** | TUT |

Diğer her şey ya **kaldırıldı** (OOS-negatif, period-fit) ya da **test edilip reddedildi** (½TP, regime-sizing, breakout aileleri).

---

## 1. Metodoloji ve Değerlendirme Çerçevesi

- **Backtest motoru:** sinyaller 1 dakikalık barlarda çözümlenir (komisyon dahil), giriş-limit zaman aşımı 180dk. Birim = **R** (risk birimi: 1R = SL mesafesi).
- **No-lookahead denetimi (PASS):** `backtest/validation/lookahead_check.py` — ay-sonu kesilmiş veriyle yeniden koşturma, tam koşunun sinyal setini birebir üretmeli. 2026 için 15/15, 2025 için 63/63 kesim temiz → gelecek-verisi sızıntısı yok. Yani OOS çöküşü **gerçek overfit**, kod hatası değil.
- **Asıl test = OOS (2025).** In-sample (2026) bir stratejinin "uydurulup uydurulmadığını" gösteremez; 2025 ayrı bir rejim yılı olarak gerçek genelleme testidir.
- **Metrikler:** `totR` (toplam R), `avgR` (işlem başı R), `WR` (isabet %).
- **Rejim ensemble'ı (gating aracı):** 6 bağımsız dedektör — Efficiency Ratio, ADX, Choppiness (teknik) + Hurst, Varyans Oranı, lag-1 otokorelasyon (istatistiksel) — her biri trend(+1) ↔ range(−1) ekseninde, ortalamaları konsensüs skoru; ≥0.15 trend, ≤−0.15 range, arası geçiş. Causal (look-ahead yok).
- **Anti-overfit imzası:** bir gate uygulandığında in-sample toplamın DÜŞÜP OOS toplamın YÜKSELMESİ — gerçek genelleme işareti (range_q'da görüldü).

---

## 2. Tüm Stratejiler — Kategoriye Göre Envanter

### A. Çekirdek ICT sinyal setleri

| Strateji | Tanım | 2026 | 2025 OOS | Durum |
|---|---|---|---|---|
| **MAIN (v1)** | Orijinal B/C/D/E sinyal seti, canlı (saatlik) | +30.3R | **−245.4R** | KALDIRILDI |
| **IMPULSE (v2)** | Rafine v2 (E atıldı, D bazı sembollerde kapalı), canlı | +67.8R | **−221.4R** | KALDIRILDI |

**Yorum:** Çekirdek ICT setleri 2026'da pozitif ama 2025'te yıkıcı negatif. Bunlar **trend-takipçisi** yapı taşları (yön ile hizalı işlem kazanıyor); 2025 temiz-trend yılı olmadığı için çöküyorlar. Kaldırma taramasında (`stream_rescue.py`) hiçbir alt-gate bunları OOS-pozitife çeviremedi → **kurtarılamaz, period-fit.**

### B. Erken denemeler (çoktan kaldırıldı)

| Strateji | Tanım | Sonuç | Durum |
|---|---|---|---|
| **RADAR (F)** | Breakout stratejisi | 2026 gate'lerini geçemedi | 2026-06-11 SİLİNDİ |
| **SQUEEZE (G)** | Funding-fade | 2026 gate'lerini geçemedi | 2026-06-11 SİLİNDİ |
| **PULSE** | 15dk akım | Edge yok | 2026-06-10 emekli |
| **RADAR_LEGACY** | Dinamik-sembol akımı | Edge yok | emekli |

**Yorum:** İlk eleme dalgası. Breakout (RADAR) özellikle önemli: literatür de saf "trading range break-out"un değişken-MA'dan zayıf olduğunu söylüyor; bizim sistemimiz bir fade motoru, breakout ona ters. Yeniden denenmeden önce gate'leri geçen bir redesign şart.

### C. Çıkış-modeli varyantları — ½TP (kısmi kâr + breakeven)

"Giriş→TP mesafesinin yarısında %50 kapat + stop'u girişe çek." Üç bağımsız testte **aynı sonuç:**

| Varyant | Full-TP | ½TP | Δ | 
|---|---|---|---|
| MAIN (v1→v3) | +133R | +71R | **−62R** |
| IMPULSE (v2→v4) | +123R | +51R | **−72R** |
| KARMA (→karma_half) | +168.9R | +66.9R | **−102R** |
| RANGE (→range_half) | +59.7R | +30.6R | **−29.1R (−49%)** |
| OPUS (→opus_half) | +156.7R | +93.7R | **−63R** |

**Yorum — evrensel kanun:** ½TP **WR'yi ~+10-15 puan yükseltir ama toplam R'yi ~yarıya indirir.** Edge büyük "runner"larda; breakeven stop + kapaklı kısmi onları geri veriyor. RANGE'de daha da kritik: RANGE_DEV'in edge'i karşı sınıra **follow-through**; ½TP tam o runner'ı kesiyor. **Karar:** hiçbir ½TP varyantı üretim default'u değil. Standalone ½TP stream'leri (v3/v4/karma_half/opus_half) 2026-06-13'te DB+UI'dan silindi. `[[range-half-tested-rejected]]`.

### D. Kompozit / seçim stratejileri

| Strateji | Tanım | 2026 | 2025 OOS | Durum |
|---|---|---|---|---|
| **KARMA** | Sembol başına {main,impulse}×{tam,½TP} en iyi hücre (2026 seçimi) | +100.6R | **−170.2R** | KALDIRILDI |
| **KARMA-8** | KARMA + 4 Burak kolu | +278.0R (in-sample) | — | sadece analiz |
| **OPUS** | MAIN sinyalleri, sembol başına en iyi NY-seansında | +156.7R | **−143.0R** | KALDIRILDI |

**Yorum:** KARMA ve OPUS **çift-katmanlı overfit**. Hücreler/seanslar 2026'da seçildi → 2025 saf OOS ve çöküyorlar. **Kritik ders: OPUS en çok uydurulmuş (in-sample avgR +0.725, hepsinin en yükseği) → OOS'ta en kötülerden (−143R).** "En iyi in-sample = en kötü OOS" kalıbı. KARMA'nın tüm-geçmiş net R'si aslında negatif (−56R); gördüğümüz +168R yalnız in-sample dilimdi. `[[regime-sizing-oos-fail]]`.

### E. Rejim-tabanlı varyantlar

| Varyant | Tanım | Sonuç | Durum |
|---|---|---|---|
| **Chop twins (8)** | Her stream'in ER<0.20 chop-filtresi | Light tarafından geçildi | 2026-06-13 SİLİNDİ |
| **LIGHT band-pass** (v2_light, kma_light) | Sadece 4h ER∈[0.20,0.35) sinyalleri | 2026 +56.6/+72.4R | **2025 OOS −59.9/−61.7R** → KALDIRILDI |
| **Regime-SIZING** (kma_regime) | Rejim skoruna göre pozisyon boyu 2×/1×/0.5× | 2026 +109→+128R ama **2025 −165→−197R** | REDDEDİLDİ (geri alındı) |

**Yorum:** LIGHT filtresi 2026'da beklentiyi yükseltti (edge'in ER 0.20–0.35 bandında yoğunlaştığını gösterdi — "ICT setimiz bir range stratejisi" tezinin ilk kanıtı) ama **tek başına OOS'u kurtaramadı.** Regime-sizing in-sample cazip, OOS'ta kaybı **büyüttü** — gating/sizing overlay'lerini shiplemeden önce OOS şart. **Rejim accuracy denetimi:** 4h-ER etiketi geçmiş pencereyi tanımlar ama **bir sonrakini öngörmede beceri göstermez** (ileriye uyum ~%51, baseline ~%59'un altında) → "şu an trend" bir tahmin değil, betimlemedir.

### F. BURAK price-action ailesi (deneysel, çoğu CSV-only)

YouTube trader "Eth Burak" metodu (range+deviation fade, OB pullback, indecision candle, trend FVG):

| Varyant | Sonuç (2026) | Yorum |
|---|---|---|
| Full paket (4 teknik) | NEGATIF (−12 ½TP / +7 full) | OB/IC/FVG kayıp |
| **RANGE_DEV tek başına** | **+36.6R, n=448, 19/29 sembol +** | Tek sağlam pozitif hücre |
| MTF (4h→1h→15m) | Ana edge'i bozdu (+7.6→−2.0R) | 4h range çok büyük |
| HYBRID (1h range, 15m trigger) | +14.7R | Sadece 7/24 likit kriptoya uyuyor |

**Yorum:** Burak full paketi canlanabilir değil, AMA **RANGE_DEV-tek-başına-full-TP** sağlam pozitif çıktı — bu, bugünkü **RANGE stream'inin tohumu** oldu. XAU'da bile pozitif (ICT impulse'ın başarısız olduğu yerde). ½TP yine R'yi yarıladı (3. bağımsız doğrulama).

### G. Diğer denemeler

| Strateji | Sonuç | Durum |
|---|---|---|
| **st-rsi-fastapi RSI** | Chop'ta net-negatif (SL'li veya SL'siz) | REDDEDİLDİ |

### H. RANGE kitabı — HAYATTA KALAN set (OOS-pozitif)

| Stream | Gate (rejim filtresi) | 2026 | 2025 OOS | avgR(26) | WR(26) |
|---|---|---|---|---|---|
| **range** | 4h · ensemble TREND verdict (score≥0.15) | +60.7R / 192 | **+9.2R** / 254 | 0.316 | 35% |
| **range_q** | 4h · trend + skor [0.20,0.30) at + RR≥2 | +49.6R / 116 | **+26.2R** / 157 | 0.428 | 37% |
| **v2_light_r** | 4h · ICT·Light + ensemble RANGE verdict (score≤−0.15) | +30.0R / 27 | **+15.5R** / 52 | 1.111 | 33% |
| range_1h | 1h · ensemble TREND verdict | +42.0R / 177 | *(yok)* | 0.237 | 33% |
| rangeq_1h | 1h · trend + bant + RR≥2 | +33.5R / 111 | *(yok)* | 0.302 | 34% |

**Yorum:** Bunlar tek OOS-pozitif aile. Üçü de aynı tezde birleşiyor: edge gerçek range/chop rejiminde.
- **range** = Burak RANGE_DEV deviation-fade'i, full-TP, ensemble-TREND'e kapılı. Tek-ER gate'inden (eski +41.6R/2026, −54.8R/2025) 6-dedektör ensemble TREND verdict'ine geçince OOS −54.8R → **+9.2R**'ye döndü (ilk OOS-pozitif config).
- **range_q (RANGE+)** = range'in yüksek-konviksiyon alt kümesi; kaybeden kümeyi (mild-trend skor bandı [0.20,0.30) + RR<2) atıyor. **OOS ~3× (+9.2→+26.2R), in-sample toplam düşerken → anti-overfit imzası.** Üretim adayı.
- **v2_light_r** = ICT·Light sinyalleri ensemble-RANGE verdict'inde — `stream_rescue` taramasının bulduğu tek kurtarılabilir ICT alt kümesi; en yüksek işlem-başı beklenti (avgR 1.111) ama örneklem ince.

---

## 3. Rejim Filtreleme — Detaylı Analiz

Rejim filtresi (6-dedektör ensemble) bu projenin asıl "modeli"; her stream = aynı sinyaller + farklı rejim-gate'i. Deney üç eksende çözüldü:

**(1) Gate timeframe'i: 4h > 1h (net).** Aynı evren, aynı RANGE_DEV sinyalleri — sadece rejimin hangi barda okunduğu:
- range: 4h **+60.7R (avgR 0.316)** vs 1h **+42.0R (0.237)** → 4h %44 daha çok R.
- range_q: 4h +49.6 (0.428) vs 1h +33.5 (0.302).
- Seçicilik neredeyse aynı (192 vs 177 işlem) → 4h *daha çok değil daha iyi* işlem seçiyor. 4h penceresi (~25 gün) rejimi temiz okur; 1h (~6 gün) gürültülü → daha çok whipsaw fade. **Rejim yavaş bir özelliktir; hızlı okuma bozuyor.** 1h varyantları her metrikte 4h'nin altında **ve henüz OOS yok** → gate timeframe'i olarak 4h'yi doğrulayan negatif kontrol.

**(2) Verdict yönü (hangi rejimde işlem) — stratejiye bağlı, sezgiye değil:**
- **RANGE_DEV (sınır fade'i) → TREND verdict'inde** kazanır (karşı sınıra follow-through gerekir). Ensemble-RANGE verdict'inde RANGE_DEV KAYBEDER (−20R).
- **ICT-yapı (v2_light) → RANGE verdict'inde** kazanır (gerçek chop). 
- "Sezgisel" eşleştirme (range'de fade) kaybediyor → filtre, "doğru stratejiyi doğru rejime yönlendirmekle" başarılı.

**(3) Skor kalite-rafinmanı (skor [0.20,0.30) bandını at + RR≥2):** her iki timeframe'de de toplamsal — 4h avgR 0.316→0.428, 1h 0.237→0.302. Mild-trend orta bandı + düşük-RR **evrensel kaybeden küme**, gate okuması ne olursa olsun → sağlam, timeframe'den bağımsız.

---

## 4. Ana Bulgular ve Dersler

1. **OOS her şeyi eledi.** v1/v2/karma/opus + light ikilisi 2026'da +30…+157R, 2025'te −60…−245R. Lookahead temiz → gerçek overfit. **In-sample sonuçlara asla güvenme.**
2. **ICT setimiz aslında bir RANGE stratejisi.** R'nin %85-90'ı ER 0.20–0.35 light bandında; strong/mid trend break-even-to-negatif. Trend tarafında edge yok.
3. **½TP evrensel olarak R'yi yarılar** (WR'yi yükseltse de). 5 bağımsız testte aynı. Edge runner'larda.
4. **"En iyi in-sample = en kötü OOS"** (OPUS, KARMA). Karmaşık seçim/optimizasyon = overfit motoru.
5. **Tek kazanan mekanizma = rejim filtresi.** Doğru uygulandığında (4h oku, stratejiyi doğru verdict'e yönlendir, orta-bandı at) OOS-pozitif stream üretiyor — başka hiçbir şey üretmedi.
6. **Anti-overfit imzası işe yarıyor:** range_q'da in-sample toplam düşerken OOS yükseldi → gerçek genelleme.
7. **Açık boşluk:** strong/mid trend rejimi için edge'imiz yok. Gerçek bir momentum stratejisi (literatürün işaret ettiği değişken-MA/VMA, saf breakout değil) buraya ait olurdu — henüz yok, yüksek overfit riski.

---

## 5. Mevcut Durum (DB + UI)

**`ict_trade.trading_signals` güncel (2026-06-14):**

| version | 2026 | 2025 OOS | Not |
|---|---|---|---|
| range | +60.7R | +9.2R | TUT |
| range_q | +49.6R | +26.2R | TUT |
| v2_light_r | +30.0R | +15.5R | TUT |
| range_1h | +42.0R | — | 1h deneyi (4h'den zayıf) |
| rangeq_1h | +33.5R | — | 1h deneyi (4h'den zayıf) |
| ⚠️ opus | +156.7R | (−143.0R*) | **GERİ GELMİŞ** — silinmişti |
| ⚠️ opus_half | +93.7R | — | **YENİ/GERİ GELMİŞ** |

*opus 2025 OOS değeri silinmeden önceki kayıttan (−143.0R).

**⚠️ Veri-hijyeni uyarısı:** `opus` ve `opus_half` (686'şar satır, 2026) DB'de **geri gelmiş** — 2026-06-14'te `opus` 6 OOS-negatif stream'le birlikte silinmişti. Muhtemel sebep: (a) VM cron'u henüz yeni `sync_daily.py`'yi (ACTIVE_STREAMS boş) çalıştırmadı ve gece `--stream all` eski kodla opus'u yeniden çözdü, ya da (b) elle bir opus backfill'i koşturuldu. OOS verdict'ine göre opus **period-fit/başarısız** → VM yeni kodla deploy edilince yeniden silinmeli.

**UI durumu:** Sidebar/streamStats/IntroPage yalnız range kitabını + 1h deneylerini gösteriyor; default rota `/range/backtest`. Tüm kalan stream'ler **backtest-only** (canlı scanner yok). Canlı pipeline durduruldu (sync_daily ACTIVE_STREAMS boş) — VM'de cron'lar durdurulup yeni kod çekildiğinde kalıcı olur.

**Canlı yayın:** Şu an hiçbir strateji canlı/üretim değil — hepsi araştırma/backtest. (dag.py main/impulse cron'ları VM'de durdurulacak.)

---

## 6. Sonuç ve Öneriler

**Üretim adayı:** **range_q** — en iyi OOS toplam (+26.2R) + güçlü in-sample avgR (0.428) + anti-overfit imza. **v2_light_r** çeşitlendirme sağlar (farklı rejim yönü, en yüksek işlem-başı beklenti).

**Yapılacaklar (sermaye öncesi):**
1. **Forward/paper doğrulama** — range_q + v2_light_r için canlı paper-monitor (emekli `halftp_monitor` gibi).
2. **2024 OOS** uzatması (DB'de yok; ağır parent backfill gerekir, Binance 418-ban riskli).
3. **opus/opus_half temizliği** — VM yeni kodla deploy + cron'lar durunca yeniden sil.
4. **v2_light_r evren temizliği** — dışlanan-4 (XRP/DOGE/LINK/AVAX) −7.4R drag taşıyor; ama aynı veride elemek in-sample optimizasyon olur, forward'da değerlendir.

**Yapılmayacaklar (kanıtlanmış çıkmazlar):**
- ½TP varyantı eklemek (her zaman R'yi yarılar).
- Regime-sizing/gating overlay'i KARMA'ya (OOS'ta kaybı büyüttü).
- Silinen period-fit stream'leri (v1/v2/karma/opus + light) geri getirmek.
- Saf breakout/TRB (fade motoruna ters; literatür de VMA<TRB demiyor — VMA>TRB).

**Olası ileri yön (yüksek risk):** strong/mid trend boşluğu için değişken-uzunluklu MA (VMA) tabanlı bir momentum stream'i — ama 1 ve 2'den sonra, tam OOS disipliniyle.

---

## Ek: İlgili dosyalar / araçlar

- **Backfill/promote:** `sync/backfill_range.py`, `sync/promote_range_q.py`, `sync/promote_light_range.py`, `sync/backfill_range_1h.py`
- **Analiz:** `sync/range_sl_analysis.py` (loser-cluster), `sync/stream_rescue.py` (gate taraması), `sync/validate_light_range.py` (stabilite), `sync/regime_route_analysis.py`, `sync/regime_accuracy.py`, `sync/regime_sizing_analysis.py`
- **Rejim ensemble:** `sync/regime_ensemble.py` (Python) ↔ `src/utils/regimeDetectors.js` (frontend, birebir port)
- **Backtest motoru / denetim:** `backtest/`, `backtest/validation/lookahead_check.py`
- **Deneysel (CSV-only):** `backtest/burak_strategy.py`, `backtest/burak_mtf.py`
