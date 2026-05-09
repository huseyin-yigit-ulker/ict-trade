# ICT Sinyal Stratejileri — Bot Geliştirme Spesifikasyonu

**Versiyon:** 1.1
**Kapsam:** Sinyal üretim katmanı + referans Python implementasyonu (`backtest/`)
**Hariç:** Risk yönetimi, execution, portföy yönetimi, canlı altyapı

> **v1.1 değişiklikleri:** Python referans implementasyonu eklendi ([§10](#10-python-referans-implementasyonu)). Confluence eşik tablosu netleştirildi (CONFLUENCE_MIN_PUBLISH = 6, HIGH = 9, MAX = 12). OTE aralığı 0.62–0.79 olarak sabitlendi. Strategy C için OB+FVG örtüşme eşiği `0.5` olarak doğrulandı. SL ATR tamponu Strategy C dışında `0.2 × ATR`, Strategy C için `0.3 × ATR` (uzaktan tutmak için).

---

## 1. Genel Bakış

Bu doküman, ICT (Inner Circle Trader) metodolojisine dayalı bir trading bot'unun **sinyal üretim katmanını** tanımlar. Sistem, beş bağımsız stratejiyi paralel çalıştırır; her strateji kendi giriş, stop ve hedef kurallarını taşır. Stratejiler ortak bir **detector kütüphanesini** kullanır.

### Mimari Akış

```
Market Data (tick/1m)
        │
        ▼
┌───────────────────┐
│ Detector Library  │  ← Swing, BOS/CHoCH, Liquidity, OB, FVG, Killzone, P/D
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Strategy Engine   │  ← 5 paralel strateji
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Confluence Scorer │  ← Çok-strateji çakışmasında skor artışı
└─────────┬─────────┘
          │
          ▼
   Signal Output (JSON)
```

### Tasarım İlkeleri

- **Look-ahead bias yasağı:** Her detector ve strateji, yalnızca o anda kapanmış mum verisiyle karar verir. Henüz kapanmamış mum sadece "tetik kontrol" amaçlı kullanılır, sinyal teyidi için kapanış zorunludur.
- **Multi-timeframe (MTF):** HTF (4H/Daily) bias; ITF (15M/1H) yapı; LTF (1M/5M) tetik. Her strateji bu üç katmanı sırayla doğrular.
- **Deterministik:** Aynı veri girdisi her zaman aynı sinyali üretir. Stokastik bileşen yoktur.
- **Tek sorumluluk:** Sinyal katmanı yalnızca "AL/SAT/BEKLE" + entry/stop/target üretir. Pozisyon büyüklüğü, sermaye yönetimi, korelasyon kontrolleri bu katmanın dışında.

---

## 2. Önkoşul Detector'lar

Stratejiler bu detector'ların çıktılarını tüketir. Her detector saf fonksiyondur (input bar dizisi → output işaretli noktalar/bölgeler).

### 2.1 SwingDetector

Fractal yaklaşım: bir bar, sağındaki ve solundaki `N` bardan yüksek/düşük kapanırsa swing point.

**Parametreler:** `N = 3` (varsayılan, ITF için), `N = 5` (HTF için)

**Önemli:** Swing point ancak `N` bar sonra doğrulanır. Real-time tespit her zaman `N` bar gecikmelidir.

**Çıktı:**
```json
{
  "type": "swing_high" | "swing_low",
  "index": int,
  "timestamp": iso8601,
  "price": float,
  "confirmed_at": int  // hangi bar index'inde teyit edildi
}
```

### 2.2 StructureDetector (BOS / CHoCH)

Swing dizisini takip eder, yapısal kırılmaları tespit eder.

- **BOS (Break of Structure):** Trend yönünde son swing high/low'un kapanışla aşılması.
  - Uptrend BOS: kapanış > son onaylı swing high
  - Downtrend BOS: kapanış < son onaylı swing low
- **CHoCH (Change of Character):** Trende ters yöndeki ilk yapısal kırılma.
  - Uptrend → CHoCH: kapanış < son HL (higher low)
  - Downtrend → CHoCH: kapanış > son LH (lower high)

**Çıktı:**
```json
{
  "type": "BOS" | "CHoCH",
  "direction": "bullish" | "bearish",
  "broken_level": float,
  "broken_at": timestamp,
  "trend_before": "up" | "down" | "range",
  "trend_after": "up" | "down" | "range"
}
```

### 2.3 LiquidityDetector

Üç tip likidite havuzunu işaretler:

- **Önceki gün/hafta high-low (PDH, PDL, PWH, PWL):** Sürekli güncellenen kalıcı seviyeler.
- **Equal highs/lows:** İki swing point arasındaki mesafe `tolerance` içinde.
  - Tolerance: `max(0.05% × price, 0.3 × ATR(14))`
- **Liquidity sweep:** Wick bu seviyeyi aşmış ama kapanış geri dönmüş.

**Sweep onayı:**
```
sweep_confirmed = (bar.high > level) AND (bar.close < level)   // bullish sweep (BSL)
                  OR
                  (bar.low < level) AND (bar.close > level)    // bearish sweep (SSL)
```

**Çıktı:**
```json
{
  "type": "PDH" | "PDL" | "PWH" | "PWL" | "EQH" | "EQL",
  "level": float,
  "swept": bool,
  "swept_at": timestamp | null,
  "sweep_bar_index": int | null
}
```

### 2.4 OrderBlockDetector

**Tanım:** Güçlü impulse hareketinden hemen önceki son zıt yönlü mum.

**İmpulse tanımı:** Ardışık 3+ aynı yönlü mum **VEYA** N bar içinde ≥ 2×ATR(14) hareket.

**Algoritma:**
1. İmpulse'u tespit et.
2. İmpulse başlangıcından geriye git, son zıt yönlü mumu bul.
3. O mumun gövdesini (open–close) OB olarak işaretle. (Bazı versiyonlarda full body+wick kullanılır; ben gövde kullanırım, daha disipline.)
4. **Geçerlilik filtreleri:**
   - İmpulse, BOS yapmış olmalı.
   - OB henüz "mitigate" edilmemiş olmalı (fiyat OB içine girmemiş).
   - OB, HTF bias ile uyumlu tarafta olmalı (bullish OB → HTF uptrend veya discount zone).

**Çıktı:**
```json
{
  "type": "bullish_ob" | "bearish_ob",
  "top": float,
  "bottom": float,
  "created_at": timestamp,
  "impulse_size_atr": float,
  "mitigated": bool,
  "mitigation_index": int | null
}
```

### 2.5 FVGDetector

**Tanım:** Üç ardışık barda ortadaki barın gövdesi nedeniyle 1. ve 3. bar fitilleri arasında oluşan boşluk.

**Algoritma:**
```python
# Bullish FVG
if bar[i+1].low > bar[i-1].high:
    fvg = (bar[i-1].high, bar[i+1].low)

# Bearish FVG
if bar[i+1].high < bar[i-1].low:
    fvg = (bar[i+1].high, bar[i-1].low)
```

**Doluş takibi:** Sonraki barlardan biri FVG aralığına girerse "kısmi dolu", aralığın karşı kenarını geçerse "tam dolu" → sinyal değeri biter.

**Çıktı:**
```json
{
  "type": "bullish_fvg" | "bearish_fvg",
  "top": float,
  "bottom": float,
  "created_at": timestamp,
  "fill_status": "open" | "partial" | "filled",
  "fill_pct": float
}
```

### 2.6 KillzoneClock

Saat tabanlı boolean filtre (UTC, NY zaman dilimine göre çevrim yapılır):

| Killzone | NY Saati | Notlar |
|---|---|---|
| Asia Range | 19:00–00:00 | Accumulation; setup almaz, sadece range çiz |
| London Open | 02:00–05:00 | Yüksek volatilite; manipulation pencereleri |
| NY Open | 07:00–10:00 | Birincil setup penceresi |
| Silver Bullet AM | 10:00–11:00 | Dar pencere; özel strateji |
| London Close | 10:00–12:00 | İkincil setup; reversal |
| Silver Bullet PM | 14:00–15:00 | Dar pencere; özel strateji |

**Lockout pencereleri** (sinyal alınmaz): Major haber öncesi 30 dk + sonrası 15 dk (NFP, CPI, FOMC, ECB).

### 2.7 PremiumDiscountCalculator

Belirlenen leg veya range için:

- **Equilibrium (EQ):** `(high + low) / 2`
- **Premium zone:** EQ üstü
- **Discount zone:** EQ altı
- **OTE (Optimal Trade Entry):** Fibonacci %62–%79 retracement bölgesi

**Kullanım:** Long setup yalnızca discount tarafında, short setup yalnızca premium tarafında geçerli sayılır. OTE aralığı entry zone olarak öncelenir.

---

## 3. Sinyal Stratejileri

Beş bağımsız strateji. Her biri için: **mantık, önkoşul, tetik, giriş, stop, hedef, geçersizlik**.

---

### Strategy A — Liquidity Sweep Reversal

**Klasik ICT setup.** Likidite süpürmesi sonrası ters yönde yapısal değişimle giriş.

#### Mantık
Smart money'nin retail stop'larını topladıktan sonra ters yöne hareket ettiği varsayımı. Önceki kritik bir likidite seviyesinin (PDH/PDL/EQH/EQL) süpürülmesi + LTF CHoCH = kurumsal ters dönüş.

#### Önkoşullar (hepsi sağlanmalı)
1. **HTF bias:** 4H veya Daily trend yönü belirlenmiş olmalı (BOS dizisi).
2. **Likidite havuzu işaretli:** Aktif PDH/PDL/PWH/PWL veya EQH/EQL var.
3. **Killzone:** London Open veya NY Open içinde (Silver Bullet dahil).

#### Tetik (sıralı)
1. Fiyat işaretli likidite seviyesini süpürür (`LiquidityDetector.swept = true`).
2. Sweep'i takip eden 5 bar içinde LTF (5M/15M) **CHoCH** oluşur, yön HTF bias ile aynı.
3. CHoCH'u yapan impulse'un **Order Block'u** veya **FVG'si** işaretlenir.

#### Giriş
- **Entry zone:** OB'nin top/bottom (sweep yönüne göre) **VEYA** FVG'nin orta noktası.
- **Confluence:** Entry zone, sweep'i yapan leg'in OTE bölgesinde (62–79%) ise sinyal kalitesi yüksek.
- **Order tipi:** Limit order, entry zone'da bekler.

#### Stop
- **Long setup:** Sweep'in low'unun `0.2 × ATR(14)` altında.
- **Short setup:** Sweep'in high'ının `0.2 × ATR(14)` üstünde.

#### Hedef
- **TP1:** Karşı taraftaki ilk likidite havuzu (RR ≥ 1:2 olmalı, değilse setup atlanır).
- **TP2:** Karşı taraftaki ikinci kalıcı likidite (PDH/PDL).
- **Partial exit:** TP1'de %50 çık, kalanı break-even'a çek.

#### Geçersizlik
- Entry zone'a ulaşmadan ters yönde yeni CHoCH oluşursa setup iptal.
- Entry zone'a 12 bar (ITF) içinde ulaşılmazsa setup expire.
- HTF haber lockout penceresine girilirse setup iptal.

#### Pseudocode
```python
def strategy_a_signal(htf_bias, liquidity_pools, ltf_bars, killzone):
    if not killzone.is_active(["london_open", "ny_open", "silver_bullet"]):
        return None

    swept = next((p for p in liquidity_pools if p.swept_recently(bars=5)), None)
    if not swept:
        return None

    choch = detect_choch(ltf_bars, after=swept.swept_at)
    if not choch or choch.direction != htf_bias:
        return None

    impulse = choch.producing_impulse
    ob = detect_order_block(impulse)
    fvg = detect_fvg_in_impulse(impulse)
    entry_zone = ob or fvg
    if not entry_zone:
        return None

    if not in_ote_zone(entry_zone, leg=swept.sweep_leg):
        entry_zone.quality = "medium"
    else:
        entry_zone.quality = "high"

    return Signal(
        strategy="A_liquidity_sweep_reversal",
        direction=htf_bias,
        entry=entry_zone.midpoint,
        stop=swept.extreme + 0.2 * atr,
        tp1=next_opposite_liquidity(),
        tp2=next_persistent_liquidity(),
        quality=entry_zone.quality,
        expires_in_bars=12,
    )
```

---

### Strategy B — Power of Three (AMD)

**Accumulation → Manipulation → Distribution.** Seans bazlı manipülasyon-sonrası giriş.

#### Mantık
Bir günün üç fazda ilerlediği varsayımı: Asya seansında accumulation (sıkışma), Londra'da manipulation (range dışına fake-out), NY'de distribution (asıl yön). Manipulation'un yönü ile distribution genellikle terstir.

#### Önkoşullar
1. **Asya range tanımlı:** Asya seansındaki (NY 19:00–00:00) high ve low çizilmiş.
2. **Range darlığı:** Asya range < `1.5 × ATR(14)` olmalı; geniş range invalid.
3. **Killzone:** London Open veya NY Open.

#### Tetik
1. Londra Açılışında fiyat Asya range'inin **bir tarafını** süpürer (manipulation phase).
2. Süpürmeyi takiben aynı seans içinde range içine **kapanışla** geri döner (fake-out teyidi).
3. LTF'de süpürme yönüne ters CHoCH oluşur.

#### Giriş
- **Entry zone:** Manipulation leg'inin OB'si **veya** FVG'si.
- **Yön:** Manipulation yönüne ters (range yukarı süpürüldüyse short, aşağı süpürüldüyse long).
- **Order tipi:** Limit, entry zone'da.

#### Stop
- Manipulation extreme'inin `0.2 × ATR` ötesi.

#### Hedef
- **TP1:** Asya range'inin karşı tarafı.
- **TP2:** Asya range'inin karşı tarafından sonraki ilk likidite havuzu.
- **Min RR:** 1:2.

#### Geçersizlik
- Manipulation sonrası fiyat range içine geri dönmezse (kapanış manipulation tarafında kalırsa) setup iptal — bu durumda gerçek breakout olabilir.
- NY seansı sonuna (NY 16:00) kadar entry tetiklenmezse setup expire.
- Asya range > 1.5 × ATR ise setup başlamaz.

---

### Strategy C — FVG + Order Block Confluence

**HTF trend yönünde, ITF FVG ve OB çakışmasında giriş.** En düşük frekanslı, en yüksek olasılıklı setup.

#### Mantık
Trend yönündeki "verimsizlik" (FVG) ile arz/talep bölgesinin (OB) çakıştığı yer, fiyat geri döndüğünde reaksiyon olasılığı yüksek bölgedir.

#### Önkoşullar
1. **HTF trend:** 4H'de net BOS dizisi (en az 2 ardışık BOS aynı yönde).
2. **Çakışma:** ITF (15M/1H) FVG ve OB üst üste (en az %50 örtüşme).
3. **Discount/Premium:** Long → discount tarafında; short → premium tarafında olmalı.

#### Tetik
1. Çakışan FVG+OB bölgesi henüz mitigate edilmemiş.
2. Fiyat çakışma bölgesine yaklaşıyor (≤ `1 × ATR` mesafede).
3. LTF'de zone'a giren ilk barın **wick reaction** vermesi (gövde > %50 ters yönde).

#### Giriş
- **Entry:** Çakışma bölgesinin uzak kenarı (long → bottom, short → top) veya OTE seviyesi.
- **Order tipi:** Limit.
- **Alternatif giriş:** Wick reaction bar'ının kapanışında market entry (agresif).

#### Stop
- Çakışma bölgesinin uzak kenarının `0.3 × ATR` ötesi.

#### Hedef
- **TP1:** ITF'deki bir önceki swing high/low.
- **TP2:** HTF'deki bir sonraki kalıcı likidite havuzu.

#### Geçersizlik
- FVG kapanışla tamamen dolarsa setup iptal (mitigation tamamlandı).
- HTF'de CHoCH oluşursa (trend değişimi) setup iptal.

---

### Strategy D — Silver Bullet

**Çok dar pencere, çok özel filtre.** Yalnızca NY 10:00–11:00 ve 14:00–15:00 arasında çalışır.

#### Mantık
ICT'ye göre bu pencerelerde kurumsal "raid" hareketleri yoğun. Pencerede oluşan FVG, hızlı ters dönüşün başlangıcıdır.

#### Önkoşullar
1. **Killzone:** Sadece Silver Bullet pencereleri (NY 10:00–11:00 veya 14:00–15:00).
2. **Pencere öncesi sweep:** Pencere açılışından önceki 60 dk içinde bir likidite süpürmesi olmuş olmalı.
3. **HTF bias mevcut.**

#### Tetik
1. Silver Bullet penceresi içinde **yeni** bir FVG oluşur (3-bar pattern, 1M veya 5M).
2. FVG yönü = HTF bias yönü.
3. FVG, son sweep'in karşı yönündedir (sweep'i takip eden ters dönüşün ürünü).

#### Giriş
- **Entry:** FVG'nin orta noktası (50% retracement içine).
- **Order tipi:** Limit, FVG oluştuktan hemen sonra yerleştirilir.
- **Alternatif:** FVG'nin uzak kenarı (daha muhafazakar).

#### Stop
- FVG'nin uzak kenarının `0.2 × ATR` ötesi.

#### Hedef
- **TP1:** Silver Bullet penceresinden önceki swing high/low.
- **TP2:** Günün karşı likidite havuzu (PDH/PDL).
- **Min RR:** 1:3 (daha katı; düşük RR'lerde Silver Bullet geçilir).

#### Geçersizlik
- FVG, Silver Bullet penceresi bitmeden tam dolarsa iptal.
- Pencere bittiğinde entry tetiklenmediyse expire.

---

### Strategy E — Equal Highs/Lows Liquidity Run

**Eşit seviyeli iki swing point, sweep + reverse pattern'i ile giriş.**

#### Mantık
Eşit high/low'lar görünür "destek/direnç" gibi davranır ve retail trader'lar için stop magnet. Smart money bu seviyeleri süpürmeye gelir; sweep + ters dönüş yüksek olasılıklı setup'tır.

#### Önkoşullar
1. **EQH veya EQL tespit edilmiş** (LiquidityDetector çıktısı).
2. **HTF trend mevcut** (range içindeyse setup atlanır).
3. **Killzone:** London Open veya NY Open.

#### Tetik
1. Fiyat EQH/EQL seviyesini süpürür (sweep_confirmed = true).
2. Sweep barından sonraki 3 bar içinde kapanış sweep edilen seviyenin **diğer tarafına** geri döner.
3. LTF'de ters yöne CHoCH (Strategy A'ya benzer ama liquidity tipi spesifik).

#### Giriş
- **Entry:** Sweep barının OB'si veya FVG'si.
- **Order tipi:** Limit.

#### Stop
- Sweep extreme'inin `0.2 × ATR` ötesi.

#### Hedef
- **TP1:** Karşı yönde en yakın swing.
- **TP2:** Karşı yönde kalıcı likidite (PDH/PDL).

#### Geçersizlik
- Sweep sonrası 3 bar içinde geri dönüş olmazsa (gerçek breakout) setup iptal.
- Strategy A ile aynı pencerede tetiklenirse Strategy A önceliklidir (daha kapsamlı filtre).

---

## 4. Confluence Scoring

Birden fazla stratejinin aynı yönde sinyal verdiği durumlar yüksek olasılıklıdır. Skorlama tablosu:

| Faktör | Puan |
|---|---|
| HTF bias ile uyum | 3 |
| Likidite süpürmesi var | 2 |
| LTF CHoCH/BOS teyidi | 2 |
| Discount/Premium tarafı doğru | 1 |
| OTE bölgesinde entry | 1 |
| Killzone içinde | 1 |
| OB + FVG çakışması | 2 |
| EQH/EQL süpürmesi | 1 |
| Silver Bullet penceresi | 2 |
| Power of Three teyidi | 2 |
| Birden fazla strateji aynı yönde tetikledi | 3 |

**Eşikler:**
- **Skor < 6:** Sinyal üretilmez.
- **Skor 6–8:** "Medium" kalitede sinyal.
- **Skor ≥ 9:** "High" kalitede sinyal.

> ⚠ Eşik değerleri ve ağırlıklar walk-forward optimization ile öğrenilmelidir; burada verilen değerler başlangıç noktasıdır.

---

## 5. Sinyal Çıktı Şeması

Her sinyal aşağıdaki standart JSON yapısında üretilir:

```json
{
  "signal_id": "uuid",
  "timestamp": "2026-05-09T14:35:00Z",
  "strategy": "A_liquidity_sweep_reversal",
  "symbol": "EURUSD",
  "direction": "long" | "short",
  "entry": 1.08423,
  "entry_type": "limit" | "market",
  "stop_loss": 1.08312,
  "take_profit_1": 1.08712,
  "take_profit_2": 1.08945,
  "risk_reward_1": 2.6,
  "risk_reward_2": 4.7,
  "confluence_score": 8,
  "quality": "high" | "medium",
  "context": {
    "htf_bias": "bullish",
    "swept_liquidity": "PDL",
    "ote_zone": true,
    "killzone": "ny_open",
    "ob_id": "ob_2026_05_09_1430",
    "fvg_id": "fvg_2026_05_09_1432"
  },
  "expires_at": "2026-05-09T15:35:00Z",
  "invalidation": {
    "type": "opposite_choch" | "fvg_filled" | "expiry",
    "level": float | null
  }
}
```

---

## 6. Strateji Önceliklendirme ve Çakışma

İki veya daha fazla strateji aynı anda aynı sembolde sinyal üretirse:

1. **Aynı yönde:** Confluence skoru toplanır (üst limit 12). Tek sinyal olarak yayımlanır, `strategy` alanı `"composite"` olur ve `composing_strategies` listesi eklenir.
2. **Ters yönde:** Yüksek skorlu sinyal kazanır, diğeri loglanır ama yayımlanmaz. Skor eşitse her ikisi de iptal edilir (ambiguous market).
3. **Aynı strateji, ardışık sinyaller:** Önceki sinyal aktifken aynı stratejiden yeni sinyal geldiğinde:
   - Aynı yön → güncelleme (entry zone genişletilebilir).
   - Ters yön → önceki sinyal iptal edilir.

---

## 7. Sinyal Yaşam Döngüsü

```
PENDING → ACTIVE → (FILLED | EXPIRED | INVALIDATED)
                        │
                        ▼
                  (TP_HIT | SL_HIT | MANUAL_CLOSE)
```

**Durum geçişleri:**
- **PENDING:** Üretildi, entry tetiklenmedi.
- **ACTIVE:** Entry tetiklendi, pozisyon açık.
- **FILLED:** Pozisyon açıldı.
- **EXPIRED:** Belirtilen bar sayısı içinde entry tetiklenmedi.
- **INVALIDATED:** Geçersizlik koşulu oluştu (CHoCH ters yöne, FVG dolu, vb.).

Her durum geçişi event olarak loglanır; analiz için hayatidir.

---

## 8. Test Edilebilirlik Notları

Sinyal katmanının her bileşeni izole edilmiş test edilebilir:

- **Detector unit test'leri:** Sentetik bar dizileri ile beklenen swing/OB/FVG çıktıları.
- **Strategy unit test'leri:** Mock detector çıktıları ile sinyal/no-sinyal beklentileri.
- **Replay test'leri:** Geçmiş veri tick-by-tick replay edilir; üretilen sinyaller deterministik olmalı.
- **Look-ahead testi:** Aynı veri tam ve kesilmiş şekilde verilir; kesilmiş veride üretilen sinyaller, tam veride aynı timestamp'te üretilen sinyallerle birebir aynı olmalı (yoksa look-ahead bias var).

---

## 9. Açık Problemler ve Sonraki Sürüm Notları

Bu spesifikasyonun bilinçli olarak çözmediği veya v2'ye bıraktığı konular:

- **OB tanımının subjektifliği:** Impulse eşiği (`2 × ATR`) sembol/timeframe bazında ayarlanmalı; tek sabit değer riskli.
- **Sweep tolerance:** "Wick aştı, kapanış geri döndü" tanımı bazı yumuşak sweep'leri kaçırır. Body bazlı ek bir sweep tipi tanımlanabilir.
- **Mitigation block / breaker block:** İleri kavramlar; ilk sürümde dahil edilmedi.
- **HTF bias değişimi:** Sinyal aktifken HTF'de CHoCH olursa ne olacağı her stratejide net tanımlı değil; v2'de unifiye edilecek.
- **Sembol bağımsızlığı:** Parametreler EURUSD/futures odaklı seçildi; kripto ve hisse için ayrı kalibrasyon gerekir.
- **News calendar:** Lockout penceresi için ekonomik takvim bağlantısı dış bağımlılık; provider seçimi sonraya bırakıldı.

---

## 10. Python Referans Implementasyonu

Bu spesifikasyonun executable karşılığı [`backtest/`](backtest/) altındadır:

| Modül | İçerik |
|---|---|
| [`backtest/ict/config.py`](backtest/ict/config.py) | Tüm parametreler (ATR çarpanları, killzone'lar, confluence ağırlıkları). Tek noktadan tunable. |
| [`backtest/ict/data.py`](backtest/ict/data.py) | Binance kline çekimi (futures + spot fallback), CSV yükleme, MTF resample. |
| [`backtest/ict/indicators.py`](backtest/ict/indicators.py) | ATR(14). |
| [`backtest/ict/detectors.py`](backtest/ict/detectors.py) | §2'deki 7 detector: `detect_swings`, `detect_structure` (BOS/CHoCH), `detect_persistent_liquidity` (PDH/PDL/PWH/PWL), `detect_equal_levels` (EQH/EQL), `mark_sweeps`, `detect_order_blocks`, `detect_fvgs`, `killzone_at`, `PDZone`. |
| [`backtest/ict/strategies.py`](backtest/ict/strategies.py) | §3'teki 5 strateji: `strategy_a`..`strategy_e`. Her biri `Signal` döndürür ya da `None`. |
| [`backtest/ict/confluence.py`](backtest/ict/confluence.py) | §4 + §6: aynı bar üzerindeki sinyalleri grupla, skorla, eşik altındakileri ele. |
| [`backtest/engine.py`](backtest/engine.py) | `run_engine(symbol, df)` → tek sembol için tam tarama. |
| [`backtest/backtester.py`](backtest/backtester.py) | Sinyal yaşam döngüsü (§7) simülasyonu, R-bazlı PnL ve metrik hesaplama. |
| [`backtest/run_backtest.py`](backtest/run_backtest.py) | CLI: Binance veya CSV girdisi, JSON çıktısı. |

### Hızlı Çalıştırma

```bash
cd backtest
pip install -r requirements.txt
python run_backtest.py --symbol BTCUSDT --interval 5m --days 60
```

Çıktı `./out/<symbol>_<interval>_<from>_<to>.json` dosyasına yazılır; iki anahtar içerir: `metrics` (özet + per-strateji kırılım) ve `trades` (her sinyalin yaşam döngüsü ve R cinsi PnL).

### Look-ahead Garantileri

- Tüm detector'lar `i` indeksindeki çıktıyı yalnızca `[0..i]` aralığından üretir.
- SwingDetector çıktıları `confirmed_at = i + N` ile etiketlenir; stratejiler swing'i ancak doğrulandıktan sonra okur.
- Backtester bir bar'a ait sinyali ancak bar kapandıktan sonra simüle eder; aynı bar içindeki TP+SL çakışmasında konservatif olarak SL kabul eder.

### Tuning Notları

- `CONFLUENCE_WEIGHTS` walk-forward ile öğrenilmelidir; mevcut değerler §4'teki başlangıç noktalarıdır.
- `IMPULSE_ATR_MULT = 2.0` kripto için makul; FX/futures'ta 1.5–1.8 daha verimli olabilir.
- `KILLZONES_NY` NY yerel saatine bağlıdır; DST otomatik olarak `pytz` tarafından handle edilir.

---

## 11. Sorumluluk Reddi

Bu spesifikasyon, ICT/SMC topluluğundaki yaygın kavramların algoritmik olarak ifade edilmesidir. **ICT yöntemlerinin hakem onaylı çalışmalarla ispatlanmış pozitif bir edge'i yoktur.** Bu doküman bir trading tavsiyesi değil, mühendislik referansıdır. Canlıya çıkmadan önce kapsamlı backtest, walk-forward validation ve paper trading şarttır.
