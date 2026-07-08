# ML-XAU RAPORU — XAU Üzerinde ML/DL Sinyal Modeli: Literatür + İlk Deney (Meta-Labeling)

**Tarih:** 2026-07-08 · **Kapsam:** literatür taraması + Aday A (MIDAS meta-labeling, LightGBM) uçtan uca deney
**Karar: NO-SHIP** — model gerçek ve yıllar-arası taşınan bir sinyal öğreniyor (AUC ~0.57) ama ekonomik olarak, halihazırda canlıda olan tek-özellikli AFTER-LOSS kapısını GEÇEMİYOR. Detay §4.

---

## 1. Literatür karnesi — ne işe yarıyor, ne yaramıyor

### ✅ İşe yarayanlar (maliyet-sonrası, belgelenmiş)

| Yaklaşım | Kanıt | Bizim için anlamı |
|---|---|---|
| **Meta-labeling** (López de Prado, AFML; Hudson & Thames JFDS serisi) | OOS accuracy 48→55% (trend), 17→63% (mean-rev); bir uygulamada Sharpe 1.18→3.08, MaxDD −6.2→−4.1% | Piyasayı değil, MEVCUT stratejinin sinyalini tahmin et. Şart: birincil edge gerçek olmalı. MIDAS = birincil model; AFTER-LOSS kapısı zaten elle bulunmuş tek-özellikli meta-etiket |
| **Gradient boosting (LightGBM/XGB) + mühendislik özellikleri** | Karşılaştırmalı çalışmalarda tutarlı GBM ≥ LSTM/Transformer (özellikle <50k örnek) | İlk model her zaman ağaç-tabanlı; DL ancak artık-değer sorusu |
| **Triple-barrier etiket + purged K-fold/embargo** | AFML metodoloji standardı; CPCV overfit-tespitinde walk-forward'dan üstün | Etiket = gerçek işlem sonucu; örtüşen-etiket sızıntısı purge ile kesilir |
| **Günlük DL momentum** (DMN+changepoint, Momentum Transformer — Wood/Roberts/Zohren) | Vadeli portföyünde Sharpe +1/3 | Günlük frekans + portföy-çapı; 1m tek-enstrüman XAU'ya taşınmaz. Çok-varlık günlük akış istenirse referans |

### ❌ İşe yaramayanlar / tuzaklar

- **"LSTM ile altın tahmini" makale ailesi**: fiyat-SEVİYESİ regresyonu (naif-gecikme tuzağı — model dünü kopyalar, R² şişer), maliyetsiz, tek-dönem, lookahead'li. %85 WR iddiaları bundan. Kopyalamaya değmez.
- **DeepLOB/TransLOB mikroyapı DL**: tahmin gücü istatistiksel olarak gerçek, ama "predictability ≠ profit after costs"; LOB verisi + maker altyapısı ister — Binance %-taker XAU'da yapısal ölüm (MIDAS maker denemesi zaten red, bkz MIDAS.md).
- **RL / end-to-end ajanlar**: OOS politika istikrarsızlığı; FINSABER tipi geniş değerlendirmede avantaj çöküyor.
- **Makro sürücüler (DXY, reel faiz, VIX, gümüş)**: günlük ufukta güçlü özellikler, 1m intraday'de alakasız.

---

## 2. Deney tasarımı (Aday A: MIDAS meta-labeling)

- **Birincil model:** SHIP edilmiş MIDAS aynen (`sync/midas/strategy.py` signals()+walk(), $0.50 FX maliyeti). Değişiklik YOK.
- **Veri / kanonik kitaplar:** XAUUSDT 1m 2026 Oca-Tem (396 işlem, +143.1R ✓ kitapla uyumlu) + PAXGUSDT 2024 (860 işlem, −297.3R) + 2025 (764 işlem, +18.9R). Toplam **2020 işlem**, havuz WR %32.8.
- **Meta-etiket:** y = işlemin gerçek walk() R'ı > 0.
- **Özellikler (21):** sinyal-anı, tamamı bar-close bilgisi — VWAP mesafe/eğim (30/60/180), touch-derinliği, ATR bps + ATR-oranı (vol rejimi), bar body/range, gün-içi ER, gün-getirisi, gün-aralığı-pozisyonu, anchor'dan-dk, saat/DOW, hacim-z, önceki-işlem dizisi (prev_r_day/had_prev/n_today/cum_r_today = AFTER-LOSS genellemesi).
- **Model:** LightGBM, sabit muhafazakâr parametreler (7 yaprak, min_child 40, λ=5) — **hiperparametre araması YAPILMADI** (protokol-overfit riski).
- **Doğrulama:** purged 5-fold CV (kronolojik, 1 gün embargo) + çapraz-yıl transfer (24+25→26 ve 26→24+25) + etiket-shuffle null + çift maliyet rejimi ($0.50 FX ve 10bps taker, işlemin kendi fill'lerinden yeniden türetilmiş).

### No-lookahead denetimi (`lookahead_check_ml.py`) — PASS
Mekanik **kesme (truncation) testi**: 60 örneklenmiş sinyal barı için TÜM özellik çerçevesi yalnız [0..i] barlarıyla yeniden hesaplandı ve tam-veri hesabıyla karşılaştırıldı → **maksimum fark 0.00e+00 (bit-özdeş)**. Sıra-özellikleri: önceki-işlem referanslarının tamamı sinyal-bar kapanışından önce kapanmış (386/386). Ayrıca dataset kaynak etiketi (yıl/enstrüman) bilinçli olarak özelliklere DAHİL EDİLMEDİ (yıl-ezberi kaçağı).

---

## 3. Sonuçlar

**Sinyal var mı? Evet, zayıf ama gerçek ve taşınıyor:**
- Purged-CV OOF AUC **0.563**; etiket-shuffle null **0.511** (≈0.50 ✓ sızıntı yok).
- Transfer 24+25 → 26: AUC **0.572** — 2024-25 PAXG'de öğrenilen desen 2026 XAU'da tutuyor.
- En önemli özellikler (gain + permütasyon tutarlı): **mins_in** (seans olgunluğu), **dist_vwap**, **pos_in_range**, **atr_ratio** — ekonomik olarak anlamlı (MIDAS'ın kendi MATURE_MIN bulgusuyla tutarlı).

**Ekonomi (deploy yönü: 24+25'te eğit → 2026'da test):**

| Filtre | n | totR (FX) | PF | maxDD | takerR |
|---|---|---|---|---|---|
| Filtresiz | 396 | +143.1 | 1.67 | −20.8 | +22.9 |
| **AFTER-LOSS (canlıdaki kapı)** | **203** | **+114.8** | **2.10** | **−12.6** | **+55.7** |
| meta top-203 (eşit n) | 203 | +78.9 | 1.79 | −12.8 | +23.4 |
| meta p≥0.40 | 151 | +57.3 | 1.82 | −11.9 | +17.1 |
| AFTER-LOSS ∧ p≥0.45 | 50 | +25.3 | 2.21 | −4.1 | +12.9 |
| AFTER-LOSS ∨ p≥0.60 | 211 | +117.0 | 2.11 | −12.6 | +56.0 |

- Eşit işlem sayısında meta (+78.9R) < AFTER-LOSS (+114.8R). Kombinasyonlar kapıyı ancak yakalıyor, geçemiyor (+117.0 vs +114.8 ≈ gürültü).
- 2026 prob-kantillerinde getiri MONOTON DEĞİL (en yüksek kantil avg_r 0.204 < orta 0.593) → sıralama sinyali var ama kalibrasyon rejimler arası kaymış; eşik-seçimi güvenilmez.
- Ters yön (26'da eğit → 24+25 test): kanamayı yumuşatıyor (−278 → −53R @p≥0.50, 509 işlem) ve bunu AFTER-LOSS'tan (−206R) belirgin iyi yapıyor, ama pozitife ÇEVİREMİYOR (avgR −0.105). Yani meta da **rejim kalkanı değil** — AFTER-LOSS notundaki uyarının aynısı.

---

## 4. Karar ve yorum

**NO-SHIP.** Plan'daki kill-kriteri (a) tetiklendi: deploy yönünde model, canlıdaki tek-özellikli AFTER-LOSS kapısını ne tek başına ne kombinasyonla geçebildi. 21 özellikli LightGBM'in tüm katma değeri, zaten elle bulunmuş 1-bit'lik bilgiye ("önceki işlem zarar mıydı") + MIDAS'ın zaten ship'li seans-olgunluk filtresine indirgeniyor. Bu, literatürle de uyumlu: meta-labeling ancak birincil modelin SÜZÜLMEMİŞ, bariz false-positive'leri varsa büyük katkı verir; MIDAS'ın girişleri zaten 3 katmanlı süzgeçten (London-skip, MATURE_MIN, AFTER-LOSS) geçiyor.

**Pozitif çıktılar:** (1) repo artık çalışan, denetlenmiş bir ML altyapısına sahip (purged-CV + truncation-audit + çift-maliyet değerlendirme şablonu); (2) AUC'nin yıllar/enstrümanlar arası taşınması, sinyal-anı özelliklerde gerçek yapı olduğunu gösteriyor — daha zayıf süzgeçli bir birincil stratejide (ör. KELT075 adayı) meta-labeling denemeye değer; (3) kötü-yıl kanaması −278→−53R'a inebiliyor: ileride "belirsiz rejimde boyut küçült" tarzı bir kullanım aday.

## 4b. Ek deney (2026-07-08): büyük-frekans REJİM KAPISI — ÇALIŞMIYOR

Soru: işlem-bazı meta yerine, daha büyük frekansta bir model "MIDAS bugün/bu saatlerde hiç işlem açsın mı?" kapısı olabilir mi? (`gate_midas.py`, 2026-only, 3-model ensemble: logistic+RF+LightGBM prob-ortalaması, purged-CV.)

- **V1 fx-günü kapısı** — karar anı = anchor+120dk (MATURE_MIN sayesinde ilk girişten ÖNCE biten kaçaksız pencere); özellikler = ilk-2saat davranışı + önceki gün fiyat/kitap + 3-gün bağlam + DOW; etiket = günün MIDAS R toplamı>0. **131 işlemli gün, OOF AUC 0.475 (yazı-tura ALTINDA; null 0.530), corr(p, günR)=−0.085, kantiller monoton değil, her eşik totR kaybettiriyor** (p≥0.40: 143→131R). Oracle tavanı büyük (+239R FX / +179R taker) ama ulaşılamıyor.
- **V2 işlem-anı, YALNIZ yüksek-TF bağlam** (2h/6h/24h ER, çok-saatlik getiri/aralık, vol rejimi, gün-içi konum, önceki-gün/gün-içi kitap R; sinyal-barı mikro özellikleri bilinçli dışarıda) — AUC 0.531 ≈ gürültü; tüm eşikler hem filtresizden hem AFTER-LOSS'tan kötü.

**Yorum:** 2026-07-07 rejim incelemesinin ("edge trend günlerinde ama sinyal-anı hiçbir rejim ölçüsü prediktif değil, |ρ|≤0.10") ML-ensemble ile gün-frekansına genellenmiş teyidi: MIDAS'ın gün-tipi ex-ante ÖNGÖRÜLEMİYOR — ne günün ilk 2 saatinden, ne önceki günden. Çalışan tek kapı (AFTER-LOSS) bir rejim sinyali değil, gün-İÇİ dizi etkisi. Oracle-gerçek makası, edge'in "trend günü yakalama" değil "her gün küçük maliyetle deneyip trend gününde koşma" yapısında olduğunu doğruluyor — kapı arayışı bu yapıya ters. n=131 gün küçük (istatistiksel güç sınırlı) ama yön (AUC<0.5) hiçbir cesaret vermiyor; PAXG ile örnek büyütme ancak özellikle istenirse.

## 4c. Ek deney (2026-07-08): BAĞIMSIZ ML sinyal üretimi — literatür aileleri 2026'da yarıştı; TEK pozitif = triple-barrier LightGBM

Soru: kapıyı bırak, ML doğrudan sinyal üretsin; literatürdeki diğer yaklaşımları da 2026 özelinde değerlendir. (`ml_signal_xau.py` + `analyze_tb.py`; 15m barlar, aylık GENİŞLEYEN walk-forward Mar-Tem OOS, 1-gün purge, eşik = eğitim-olasılık kantili q90/q97 "selective classification", denetlenmiş engine ile ekonomi, random-giriş null bandı, çift maliyet.)

| Model (literatür ailesi) | OOS AUC | q97 ekonomi (Mar-Tem, FX) | Yorum |
|---|---|---|---|
| **TB-LGBM** (triple-barrier + LightGBM, AFML) | **0.651** (aylar: 0.57→0.72 ↑) | **83tr +27.8R PF1.57 DD−10.3, taker +3.1** (null −5±8R ⇒ ~4σ) | TEK gerçek pozitif |
| TB-LOGIT (linear baseline) | 0.625 | 146tr −6.7R | AUC var, para yok — sıralama ucu bozuk |
| TB-MLP (özellik-girdili NN) | 0.606 | 150tr −18.5R | LGBM'in gerisinde |
| FH-LGBM (sabit-ufuk yön = klasik makale hedefi) | 0.510 | 136tr −6.8R | yazı-tura — "ML altın yönü tahmin eder" ailesinin 2026 ampirik çürütmesi |
| SEQ-MLP (ham gecikme-dizisi = "LSTM diyeti") | 0.504 | 271tr −36.2R | fiyat-geçmişi-tek-girdi NN hiçbir şey öğrenmiyor |
| ENSEMBLE (3 TB modeli) | 0.634 | 38tr +12.8R PF1.57 | LGBM'i geçemiyor |

**TB-LGBM derin analiz:** eşik platosu sağlıklı (q93-q98 hepsi +16..+28R; q99 ölüyor). Kırılımlar: kârın %77'si Mayıs'ta (+21.5R); short-taraf +23.2R vs long +4.6R; exit'ler 32 target / 47 stop / 3 time. Top özellikler: mins_in (0.22), atr_ratio, utc_hour, day_ret, dow — model büyük ölçüde SEANS YAPISI + vol rejimini yeniden keşfediyor, üstüne bir short-cebi ekliyor. MIDAS ile örtüşme: 83 işlemin 55'i açık bir MIDAS işlemine denk geliyor (34 aynı yön) ama günlük-R korelasyonu 0.247 (düşük) → kısmen bağımsız; Mar-Tem birleşik +129.7R vs MIDAS-yalnız +102.0R.

**Yorumlar (kendi değerlendirmem):**
1. **Etiket > model.** Aynı özellikler, aynı LightGBM: sabit-ufuk etiketle AUC 0.510, triple-barrier etiketle 0.651. Literatürün asıl dersi bu — modele değil, etiketin işlem-gerçekliğine yatırım yap (AFML tezinin 2026 doğrulaması).
2. **"LSTM altın tahmini" ailesi 2026'da da boş.** Ham fiyat-geçmişi dizisi (SEQ-MLP) 0.504 + her eşikte negatif. Makalelerdeki parlak sonuçlar seviye-regresyon artefaktı/maliyetsizlik; sinyal fiyat-dizisinde değil, BAĞLAM özelliklerinde (seans, vol-rejim).
3. **AUC ≠ para.** TB-LOGIT 0.625 AUC'ye rağmen para kaybediyor — dağılımın ucundaki seçim kalitesi ayrı bir şey; ekonomiyi her zaman engine ile ölç.
4. **AUC ay geçtikçe yükseliyor** (0.57→0.72): model veri biriktikçe öğreniyor → PAXG 2024-25 ile eğitim büyütme doğal sonraki adım; ama meta-deneyde görülen rejim-kayması riski aynen geçerli (2024-25'in MIDAS-negatif rejimi TB dağılımını da kaydırabilir).
5. **Ship çıtasının neresinde?** Tek yılın 5 OOS ayı; kâr Mayıs-yoğun; taker'da ≈0 (yine FX-cost akışı olur); n=83. Repo standardına göre henüz ship-grade DEĞİL — ama 30+ el-yapımı ailenin çoğundan iyi bir ilk-geçiş ve MIDAS'a düşük-korelasyonlu ek olma potansiyeli var. Sonraki kapı: PAXG çok-yıl OOS + parametre platosu (SL/TP/H geometrisi) + canlı-paper izleme.

## 4d. Ek deney (2026-07-08): STACKING — tüm stratejiler özellik olarak ML harmanına + yeni özellikler

Soru: XAU'da çalışan tüm stratejileri (repo + literatür) birleştirip sinyallerini ML ile harmanlasak + üstüne yeni özellikler eklesek? (`stack_xau.py`; §4c harness'ı birebir: TB etiketi, aylık genişleyen WF, engine-ekonomi, null bandı.)

**Özellik grupları:** 12 kural-strateji sinyali 1m→15m (shipped MIDAS, TALOS-KELT075, Keltner-mid, EMA200/KAMA pullback, Supertrend flip+pull, Donchian-120, önceki-gün H/L, Asya-kutusu, PSAR, seans-TSMOM) + 4 durum özelliği (supertrend/PSAR yönü, Donchian pozisyonu, Keltner-z) + 6 çapraz-varlık YENİ özellik (gümüş ret4/16/96, altın/gümüş oranı z, BTC/SPY ret16).

| Set | OOS AUC | q97 (Mar-Tem, FX) | q95 |
|---|---|---|---|
| BASE (yalnız piyasa özellikleri, §4c) | 0.640 | **83tr +27.8R PF1.57** | 156tr +26.9R |
| STRAT (yalnız strateji sinyalleri) | **0.503** | 213tr −2.5R | 304tr +6.1R |
| BASE+STRAT | 0.644 | 83tr +11.1R | 158tr +22.0R |
| HEPSİ (+çapraz-varlık) | 0.633 | 71tr +12.6R | 138tr +20.0R |

Gain payı: piyasa %69, strateji sinyalleri **%6**, çapraz-varlık %25 (ama ekonomiye çevrilmiyor; SPY/BTC/XAG pikleri 30-Haz'da bitiyor, Temmuz NaN).

**Yorumlar:**
1. **Strateji sinyalleri tek başına bilgisiz: AUC 0.503.** Kural stratejilerinin giriş-anları, TB sonucu hakkında piyasa özelliklerinin zaten kodlamadığı EK bilgi taşımıyor. Bu stratejiler değersiz demek değil — MIDAS/TALOS parayı ÇIKIŞ motoruyla (trailing runner) kazanıyor; giriş anının kendisi bilgi kaynağı değil. Donchian kitabındaki "kaldıraç exit'te, giriş-filtrelemede değil" bulgusunun ML-aynası.
2. **Harman BASE'i geçemiyor, hatta q97'de sulandırıyor** (+27.8→+11.1R): n≈11k örnekte 36-42 boyut, en-uç kantil seçimini bozuyor (boyut laneti). Özellik eklemek bedava değil.
3. **Doğru birleştirme seviyesi PORTFÖY, özellik değil:** ML-TB (83tr +27.8R) MIDAS'a düşük-korelasyonlu (günlük 0.247, §4c) → Mar-Tem MIDAS+ML birleşik +129.7R. KELT075 portföy bulgusuyla (+230R MIDAS+KELT) aynı ders: düşük-korelasyonlu KİTAPLARI yan yana koy, sinyalleri aynı modele karıştırma.
4. Çapraz-varlık özellikler importance kapıyor ama OOS ekonomi üretmiyor — tipik "önemli görünen ama para etmeyen" özellik; ayrıca veri Temmuz'da kesik. Tam-tarihli gümüş verisiyle tekrar bakılabilir ama öncelik değil.

## 4e. Ek deney (2026-07-08): ML'siz — trader-tipi KOMPLEKS HİBRİT (confluence checklist) mekanizasyonu

Soru: ML'yi bırak; trader'ların kullandığı kompleks hibrit stratejilerden bir sistem kur. (`scratchpad/fx_gold/hybrid_xau.py`)

**Mimari (gerçek trader checklist'i, mekanize):** C1 HTF hiza (1h EMA50 eğim + 4h EMA20 tarafı) · C2 gün-içi trend (MIDAS VWAP tanımı) · C3 bölge (VWAP ∪ 15m Keltner bandı 0.75 ∪ önceki-gün H/L'ye 0.25×ATR dokunuş) · C4 tetik mumu (yön + üst-yarı kapanış) · C5 hacim onayı (z>0) · SEANS (shipped disiplin, her zaman). Giriş = seans + k-of-5; çıkış = denetlenmiş MIDAS motoru (1.5×ATR stop, 3.5×ATR trail, 8h) ve karşılaştırma için sabit-2R "trader hedefi". Ek klasik: kırılım+retest (önceki-gün H/L kır → 2h içinde retest tut → gir).

| Sistem | n | totR | PF | DD | IS/OOS | taker |
|---|---|---|---|---|---|---|
| CONF k≥5 (tam checklist, trail) | 334 | **+101.4** | 1.59 | −15.3 | +59.5 / +41.9, **her ay yeşil** | +3.1 |
| CONF k≥4 (trail) | 653 | +87.6 | 1.23 | −22.2 | +47.2 / +40.4 | −104 |
| CONF k≥2 (trail) | 748 | +172.8 | 1.39 | −27.0 | Oca +111 tek-ay artefaktı | −243 |
| aynıları sabit-2R hedefle | — | hepsi trail'den kötü (PF/OOS) | | | | |
| KIRILIM-RETEST | 175 | +13.1 | 1.13 | −17.2 | OOS **−1.4** | −33 |
| **MIDAS (benchmark)** | 396 | **+143.1** | 1.67 | −20.8 | +85 / +58 | +22.9 |

**Ablasyon (k5'ten tek katman çıkar):** −C4 tetik → **+117.3R (İYİLEŞİYOR)**; −C1 HTF → +107.7; −C5 hacim → +97.3 (≈nötr); −C3 bölge → +56.7 (ÇÖKÜYOR). Yani 5 katmandan yalnız 2'si bilgi taşıyor: **gün-içi trend (C2) + bölge dokunuşu (C3)** — ki bu MIDAS'ın kendisidir. Nitekim CONF-k5, MIDAS kitabıyla 256/334 işlem örtüşüyor, günlük-R korelasyonu **0.732** → bağımsız kitap DEĞİL, MIDAS'ın süzülmüş bir varyantı; MIDAS'tan da az kazanıyor (+101 vs +143).

**Yorumlar:**
1. "Confluence" ritüelinin mekanize gerçeği: HTF hizası, tetik mumu ve hacim onayı — üç popüler katman — XAU 1m'de ya nötr ya ZARARLI. Trader checklist'inin çalışan çekirdeği trend+lokasyon; gerisi işlem sayısını (ve R'ı) kırpan dekor. MIDAS entry-filtre taramasının (hepsi red) üçüncü bağımsız teyidi.
2. Sabit-2R hedef her k'da trail'den kötü — "altında çıkış dogması" (trailing dokunulmaz) bir kez daha doğrulandı.
3. Kırılım+retest 2026'da ölü (OOS −1.4) — repo'nun kırılım-fade tarihçesiyle tutarlı.
4. Pratik sonuç: kompleks hibrit YENİ kitap üretmedi; eldeki en iyi yapı hâlâ MIDAS + TALOS (+ belki ML-TB, §4c) düşük-korelasyonlu portföyü. Karmaşıklık başlı başına değer değil.

## 5. Sonraki adımlar (bu turda YAPILMADI)
- **Aday B:** bağımsız 15m triple-barrier yön modeli (kill: OOS PF<1.1). Etiketleyici hazır (`labels.triple_barrier`).
- **Aday C:** ancak bir aday pozitifse, aynı etiketlerde küçük GRU/TCN artık-değer testi (tek deney).
- **Alternatif meta hedefi:** KELT075 (SHIP edilmemiş Keltner adayı) sinyallerinde aynı pipeline — birincil süzgeci zayıf, meta katkı alanı daha geniş.

## 6. Dosyalar
- `scratchpad/fx_gold/ml/features.py` — sinyal-anı özellik çerçevesi (yan-ayarlı, NaN'lar LightGBM'e bırakılır)
- `scratchpad/fx_gold/ml/labels.py` — meta-etiket + dizi-özellikleri + (Aday B için) triple-barrier
- `scratchpad/fx_gold/ml/meta_midas.py` — ana pipeline (dataset + purged-CV + transfer + null + importance); `--rebuild`
- `scratchpad/fx_gold/ml/combo_test.py` — AFTER-LOSS karşılaştırma/kombinasyon testi
- `scratchpad/fx_gold/ml/gate_midas.py` — büyük-frekans rejim-kapısı deneyi (V1 gün / V2 yüksek-TF, ensemble; §4b)
- `scratchpad/fx_gold/ml/ml_signal_xau.py` — bağımsız ML sinyal harness'ı (5 aile + ensemble, aylık WF; §4c)
- `scratchpad/fx_gold/ml/analyze_tb.py` — TB-LGBM derin analizi (plato/kırılım/MIDAS-örtüşme/önem; §4c)
- `scratchpad/fx_gold/ml/stack_xau.py` — stacking harmanı (12 strateji + durum + çapraz-varlık özellikleri; §4d)
- `scratchpad/fx_gold/ml/lookahead_check_ml.py` — truncation no-lookahead denetimi (PASS)
- `scratchpad/fx_gold/ml/dataset.pkl` — önbellek (2020 işlem; gitignore'lu pkl)
- Ortam: `.venv`'e scikit-learn 1.7.2 + lightgbm 4.6.0 + scipy kuruldu (requirements'a EKLENMEDİ — araştırma bağımlılığı)

Canlı koda, DB'ye, cron'a dokunulmadı — tamamı backtest-only araştırma.
