# FX / XAUUSD 1m İntraday Bot — Strateji Araştırması ve Önerilen Model

**Tarih:** 2026-06-30 · **Kapsam:** mevcut çalışmalardan (Donchian/ICT/OPUS/FABLE) **bağımsız**, sıfırdan
araştırma. Sadece **XAUUSDT**, **1m** veri, **anlık aç-kapa (intraday, gecelik pozisyon yok)**, **2026**,
**sadece piyasa-açık saatlerde**.

---

## 1. Özet (TL;DR)

Literatürdeki ana intraday FX/altın stratejilerini (ORB, VWAP, mean-reversion, seans-momentum) mekanikleştirip
2026-H1 XAUUSDT 1m üzerinde gerçekçi maliyetle test ettim. **Kazanan tek sağlam model:**

> ### 🏆 VWAP-Trend Pullback + ATR Trailing Stop
> Trend yönünde (VWAP eğimi) **VWAP'a geri çekilmeyi** alıp, **sabit hedef koymadan** ATR-trailing
> stop ile koşturan, **gün-içi kapanan** bir momentum-devam stratejisi.

| Metrik | Değer |
|---|---|
| Toplam | **+115 R** (2026-H1, 6 ay) |
| Profit Factor | **1.32** |
| Win-rate | %35 (ort. kazanç +2.25R / ort. kayıp −0.90R) |
| Max Drawdown | **−34 R** |
| Sharpe (dürüst, 6-ay) | ~**2.5** (rapor edilen 3.2 aşırı-yıllıklandırma) |
| İşlem | 603 (~5/gün), medyan tutuş ~2 saat |
| In-Sample (Oca-Nis) | +53.7R (PF 1.21) |
| Out-of-Sample (May-Haz) | +61.2R (PF 1.61) |
| Long / Short | +41R / +74R (ikisi de pozitif) |
| Aylık | 5/6 ay yeşil (yalnız Şubat −6R) |

**Diğer her şey elendi:** mean-reversion/fade'ler (VWAP-band, Bollinger, RSI) ve sabit-RR ORB **maliyet
sonrası negatif** — bu repo'nun geçmiş bulgularıyla (fade'ler trendde ölür) ve literatürle birebir tutarlı.

⚠️ **En kritik uyarı:** Bu model **Binance taker komisyonunda (≈10 bps = ~$4/oz) ÖLÜR (−92R)**. Sadece
**dar-spread'li ECN FX/CFD altın hesabında** (round-trip ≤ ~$1/oz) veya Binance'te **maker (limit) emirle**
yaşar. Headline $0.50/oz round-trip varsayımı muhafazakâr bir ECN değeridir.

---

## 2. Veri ve "piyasa-açık" filtresi

- **Kaynak:** Binance Futures **XAUUSDT perpetual** (fiyat gerçek altını izliyor; 2026-H1'de ~$3950–5600).
  Geçmiş **2025-12-11**'de başlıyor → 2026-H1 tam kapsanıyor ama **2026 öncesi OOS yok** (kısıt).
- **2026-H1:** 259,581 adet 1m bar (1 Oca → 30 Haz).
- **FX altın piyasa saatleri** (zorunlu filtre — `America/New_York`, DST otomatik):
  açık = **Paz 18:00 ET → Cuma 17:00 ET**, her gün **17:00–18:00 ET rollover molası** hariç.
  → bar'ların %68.2'si açık. (Hafta-içi %95.8, Cuma %70.8, Cmt %0, Paz %25 — gerçek takvimle birebir.)
- ⚠️ **Sentetik-fiyat tuzağı (literatür uyarısı):** TradFi altın kapalıyken Binance XAUUSDT index'i
  donduruyor/EWMA'ya geçiyor. Bu yüzden kapalı bar'lar **sinyal üretiminden ÖNCE** dışlandı (sadece
  giriş anında değil). ATR'yi yalnızca açık-bar'lardan hesaplayınca sonuç değişmiyor (+110R) → etki yok.

---

## 3. Literatür araştırması (çok-ajanlı web taraması + şüpheci doğrulama)

5 aileyi paralel taradım; ana bulgular:

- **Altın TRENDLEYEN bir enstrüman** → momentum/breakout çalışır, **fade'ler ölür** (Neely-Weller, ve bu
  repodaki XAU RSI-fade / 4H-range / ict-sweep / supdem redleri ile aynı).
- **ORB (Opening Range Breakout)** literatürün en OOS-sağlam ailesi (Zarattini-Aziz 2023; Holmberg; Tsai)
  **ama çoğu kanıt HİSSE'de** (açılış-ihalesi dinamiği). Altın FX'te açılış-ihalesi yok → literatürün
  kendi sentezi bile ORB'u **"sınırda/şüpheli"** işaretledi. **Benim testimde altın 2026'da ORB negatif.**
- **Sabit kâr-hedefi MOMENTUM ailesinde ZARARLI** (Zarattini, Wu 2020): trend günlerini kesip düşük
  win-rate'i finanse eden sağ-kuyruğu öldürüyor → **hedefsiz + trailing + gün-sonu çıkış** doğru tasarım.
- **Maliyet bağlayıcı kısıt:** Binance taker round-trip ~10 bps ($4/oz @ $4000); ECN FX ~2–6 bps
  ($0.10–0.25/oz). Min. uygulanabilir kâr ≥ ~4× maliyet → mikro-scalp **aritmetik olarak ölü**; sadece
  çok-R'lik koşan (runner) tasarımların şansı var.

**Sonuç:** literatürün *mekanizması* (momentum-devam + hedefsiz + trailing + maliyet/likidite-bilinçli)
benim ampirik kazananımla birebir örtüşüyor — sadece *giriş tetiği* farklı (ORB-breakout yerine
**VWAP'a pullback**, ki ters-seçilimi azaltıp altında ORB'u yendi).

---

## 4. Test edilen tüm adaylar (2026-H1, market-hours, $0.50 round-trip)

| Strateji ailesi | Sonuç | Yorum |
|---|---|---|
| **VWAP-trend pullback + trailing** | **+115R / PF 1.32** | ✅ KAZANAN |
| VWAP-trend (sabit RR2) | +23R / PF 1.06 | trailing olmadan zayıf |
| ORB (NY/Londra, 15/30/60m, RR2 / trailing) | −5 … −65R | ❌ altında çalışmıyor |
| Momentum breakout (N-bar high + EMA) | −60 … −104R | ❌ chop'ta maliyet yiyor |
| VWAP-band fade (mean-reversion) | −178R | ❌ trendde ölüyor |
| Bollinger fade (Asya seansı) | −84R | ❌ |
| Buy & Hold (referans) | −7.7% | altın net düştü |

---

## 5. Önerilen model — tam mekanik kurallar

**İsim:** VWAP-Trend Pullback (XAUUSD 1m intraday)

**Göstergeler (hepsi sızıntısız — bar *kapanışında* karar, *sonraki* bar açılışında giriş):**
- **Anchored VWAP**, her FX-gününde 18:00 ET'de sıfırlanır; bant için VWAP'tan sapmanın kümülatif std'i.
- **Trend filtresi:** VWAP'ın son **60 bar** eğimi (`vwap[i] − vwap[i−60]`).
- **ATR(15m, 14)** → 1m'e ffill (stop ölçeği için).

**LONG girişi** (bar i'de doğru → i+1 açılışta fill):
1. `close > VWAP` (trend yukarı tarafta)
2. `VWAP eğimi > 0` (yükselen VWAP)
3. `low ≤ VWAP + 0.25×ATR` (bu bar VWAP'a geri-çekilip dokundu)
4. `close > open` (boğa geri-alış barı)

**SHORT girişi:** simetrik (`close<VWAP`, eğim<0, `high ≥ VWAP−0.25×ATR`, `close<open`).

**Risk / çıkış:**
- Başlangıç stop = giriş ∓ **1.5×ATR(15m)** (1R = bu mesafe).
- **Sabit kâr hedefi YOK.** Çıkış = **3.5×ATR trailing stop** (chandelier, koşan tepe/dipten) **veya**
  **8 saat** max tutuş **veya** seans-sonu zorunlu düz (Cuma 17:00 ET / günlük mola / hafta sonu) —
  hangisi önce.
- Aynı anda **tek pozisyon**. Sadece piyasa-açık saatlerde giriş.

**Parametre platosu (overfit değil — geniş bir bölge pozitif):** slope_n ∈ {20–90}, trail ∈ {2.0–3.5},
init-stop ∈ {1.0–2.0}×ATR hepsi pozitif. Seçilen hücre: slope_n=60, init 1.5×ATR, trail 3.5×ATR.

**Maliyet duyarlılığı:** $0.20→+105R, $0.50→+115R, $0.80→+71R, $1.50→+33R (PF 1.08, hâlâ +),
**Binance taker $3.74→ −92R** (kullanma).

---

## 6. Sağlamlık doğrulaması (neden buna güveniyorum)

1. **Plato, tepe değil:** parametre komşuluğunun tamamı pozitif (şanslı tek hücre değil).
2. **Dürüst OOS:** parametreyi **sadece In-Sample (Oca-Nis)** ile seçip dondurdum → IS-en-iyi config
   donmuş OOS'ta **+61R (PF 1.61)**; IS-top-5 ortalama OOS +44R. In-sample kenar OOS'a taşınıyor.
3. **Random-entry null testi:** aynı sayıda/aynı yön dağılımında **rastgele girişler** aynı trailing+EOD
   mekaniğiyle ortalama **−16R**; 200 denemenin **hiçbiri** gerçeğe ulaşmadı (p<0.005). → Kenar **VWAP
   giriş zamanlamasından** geliyor, trailing/sürüklenmeden değil.
4. **Likit-saat (Neely-Weller) testi:** Londra-NY overlap'ine (13–17 UTC) kısıtlayınca **daha güçlü**
   (+62R, PF **1.79**). Edge ince/illikit saatlerden gelmiyor.
5. **Konsantrasyon:** en iyi işlemi at → +98R; en iyi 3 günü at → +69R. Runner'lar (>3R) **her ay 7–11**
   adet (10/11/7/8/10/10) → tek-olay değil, **dağılmış**. Günlük bootstrap: ortalama +113R, 5. persentil
   **+37R**, P(zarar)≈%0.7.
6. **Bağımsız sıfırdan tekrar-kodlama (ayrı ajan, ayrı kod):** n=603, +115.0R, PF 1.32, IS+53.7/OOS+61.2
   — **virgülüne kadar** aynı. Lookahead/fill audit'leri (3 bağımsız) temiz.

---

## 7. Dürüst uyarılar (deploy öncesi MUTLAKA oku)

1. **Magnitüd üst-sınırdır, beklenti değil.** Kenar sağ-kuyrukta (işlemlerin ~%9'u). Dürüst beklenti =
   bootstrap **alt sınırı ~+20–25R**, +115R değil. Canlı slipaj / kaçan bir runner sonucu orantısız bozar.
2. **Sadece 6 ay veri** (2026-H1). t≈2.26 (p≈0.012) — toplam ~150 config denendi; çoklu-test düzeltmesi
   altında *tek* config sınırda kalır. **Başka yıl/enstrümanla (GC futures, XAUUSD spot) doğrulanmalı.**
3. **Long/Short ayrımı 2026 patikasına bağlı** (altın önce çıktı sonra düştü); ayrı bir "short edge"
   garanti değil.
4. **Komisyon ölümcül:** Binance taker'da çalışmaz. Dar-spread ECN FX/CFD veya maker-fill şart. Haber
   barlarında (NFP/CPI/FOMC, 13:30 UTC) spread patlar → o seansları dışla veya maliyeti 3–5× al.
5. Sharpe'ı **~2.5** olarak oku (rapor edilen 3.2 aşırı-yıllıklandırma hatası; R/PF figürleri sağlam).

---

## 8. Sonraki adımlar (istersen)

- [ ] 2025/2024 **GC futures veya XAUUSD spot 1m** ile çok-yıllı OOS doğrulama (en önemli eksik).
- [ ] Haber-barı filtresi + likit-saat (13–17 UTC) kısıtıyla "konservatif" varyant (PF 1.79).
- [ ] Maker-fill simülasyonu (limit emir doluş olasılığı) Binance'te yaşar mı?
- [ ] Canlıya almak istersen: paper/demo monitör (mevcut FABLE paper hattına benzer), **gerçek-para
      executor'a DOKUNMADAN**.

**Kod:** `scratchpad/fx_gold/` — `data.py` (veri+saat), `fxstrat.py` (stratejiler), `engine.py`
(sızıntısız backtest motoru), `run*.py` (testler), `canonical_trades.csv` (işlem listesi).
