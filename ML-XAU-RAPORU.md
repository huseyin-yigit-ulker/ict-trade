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
- `scratchpad/fx_gold/ml/lookahead_check_ml.py` — truncation no-lookahead denetimi (PASS)
- `scratchpad/fx_gold/ml/dataset.pkl` — önbellek (2020 işlem; gitignore'lu pkl)
- Ortam: `.venv`'e scikit-learn 1.7.2 + lightgbm 4.6.0 + scipy kuruldu (requirements'a EKLENMEDİ — araştırma bağımlılığı)

Canlı koda, DB'ye, cron'a dokunulmadı — tamamı backtest-only araştırma.
