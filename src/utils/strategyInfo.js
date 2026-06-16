// Per-strategy intro-card content, bilingual (tr / en). Rendered by StrategyIntro.jsx.
// Shape per language: { title, tagline, summary, sections:[{h,t}], caveat? }.
// Sections are short labelled blocks (Sinyal mantığı / Çıkış / Evren & Zaman / Risk).

export const STRATEGY_INFO = {
  main: {
    icon: '🎯', accent: '#F5B942',
    tr: {
      title: 'MAIN', tagline: 'ICT ana strateji seti (v1)',
      summary: 'Kurumsal likidite avına dayalı ICT konsept seti. Fiyatın likidite süpürüp yön değiştirdiği yerleri yakalar; 4 saatlik trend yönünde, 1 saatlik grafikte işler.',
      sections: [
        { h: 'Sinyal mantığı', t: '4 strateji birlikte tarar — B (Power of Three: Asya aralığı süpürme + CHoCH), C (Order Block + FVG konfluansı, trend yönlü), D (Silver Bullet: NY killzone’unda taze FVG), E (EQH/EQL likidite koşusu). 4h HTF yön filtresi ve konfluans skoru ile elenir.' },
        { h: 'Giriş', t: 'OB/FVG bölgesine limit emir. Emir 180 dakika içinde dolmazsa sinyal iptal (no-fill). Aynı bölgede 24 saat içinde tekrar sinyal bastırılır (dedup).' },
        { h: 'Çıkış', t: 'Tek seferde hedefe taşınır — TP1 = karşı taraftaki likidite; SL = süpürme ekstremi ± ATR tamponu (taban: max %0.15 / 0.5 ATR). Min R/R 2.0 (Silver Bullet için 3.0), TP en fazla 4 ATR.' },
        { h: 'Evren & zaman', t: '1 saatlik sinyal, 1 dakikalık çözümleme. Tüm üretim sembolleri: kripto + metal (XAU/XAG) + ABD hisse perp’leri. Komisyon (%0.05/yön) net R’ye dahil.' },
      ],
    },
    en: {
      title: 'MAIN', tagline: 'Core ICT strategy set (v1)',
      summary: 'An ICT concept set built on institutional liquidity hunts. It catches where price sweeps liquidity and reverses, trading the 1h chart in the direction of the 4h trend.',
      sections: [
        { h: 'Signal logic', t: 'Four strategies scan together — B (Power of Three: Asia-range sweep + CHoCH), C (Order Block + FVG confluence, trend-aligned), D (Silver Bullet: fresh FVG in the NY killzone), E (EQH/EQL liquidity run). Filtered by 4h HTF bias and a confluence score.' },
        { h: 'Entry', t: 'Limit order into the OB/FVG zone. If unfilled within 180 minutes the signal is cancelled (no-fill). Re-signals on the same zone within 24h are suppressed (dedup).' },
        { h: 'Exit', t: 'Rides to target in one piece — TP1 = opposite-side liquidity; SL = sweep extreme ± ATR buffer (floor: max 0.15% / 0.5 ATR). Min R/R 2.0 (3.0 for Silver Bullet), TP capped at 4 ATR.' },
        { h: 'Universe & time', t: '1h signals, 1m resolution. Full production universe: crypto + metals (XAU/XAG) + US-equity perps. Fees (0.05%/side) included in net R.' },
      ],
    },
  },
  impulse: {
    icon: '⚡', accent: '#5C93FF',
    tr: {
      title: 'IMPULSE', tagline: 'MAIN’in rafine alt-kümesi (v2)',
      summary: 'MAIN ile aynı motor, ama gürültüyü temizlenmiş hâli: ölü ve zarar eden bileşenler ayıklanır. Daha az sinyal, işlem başına daha yüksek beklenti.',
      sections: [
        { h: 'MAIN’den farkı', t: 'Strateji E tamamen atıldı (2026’da sıfır sinyal üretti). Silver Bullet (D) yapısal negatif olduğu sembollerde — ADA, XAU, ETH — kapatıldı; bu sembollerde B/C çalışmaya devam eder.' },
        { h: 'Sonuç', t: 'Set ve sembol kapsamı daralır; motor, giriş, çıkış, risk ve zaman dilimi MAIN ile birebir aynı. 2026 ablasyonda MAIN’den belirgin üstün (daha yüksek toplam R ve işlem başı beklenti).' },
        { h: 'Ne zaman', t: 'Aynı 1h / 4h HTF kurgusu, aynı killzone’lar. Trend rejiminde MAIN’e göre daha seçici.' },
      ],
    },
    en: {
      title: 'IMPULSE', tagline: 'Refined subset of MAIN (v2)',
      summary: 'Same engine as MAIN, noise-trimmed: dead and loss-making components are removed. Fewer signals, higher expectancy per trade.',
      sections: [
        { h: 'Diff vs MAIN', t: 'Strategy E dropped entirely (zero signals in 2026). Silver Bullet (D) disabled on the symbols where it was structurally negative — ADA, XAU, ETH; B/C keep running on them.' },
        { h: 'Result', t: 'Narrower set + symbol scope; engine, entry, exit, risk and timeframe identical to MAIN. In the 2026 ablation it clearly beats MAIN (higher total R and per-trade expectancy).' },
        { h: 'When', t: 'Same 1h / 4h HTF construct, same killzones. More selective than MAIN in trending regimes.' },
      ],
    },
  },
  karma: {
    icon: '🜲', accent: '#A78BFA',
    tr: {
      title: 'KARMA ½', tagline: 'Sembol başına en iyi hücre (7/40 sembol ½TP, gerisi tam)',
      summary: 'Tek beden değil: her sembol için en kârlı yapıyı seçer. {MAIN / IMPULSE} sinyal seti × {Tam TP / ½TP} çıkışı 2×2 matrisinin, o sembolde en yüksek R veren hücresi kullanılır.',
      sections: [
        { h: 'Nasıl seçer', t: 'Her sembolde 4 hücre 2026 boyunca koşulur, toplam R’ye göre kazanan seçilir. Örn. bir sembol IMPULSE/Tam, bir başkası MAIN/½TP altında işlenir. Seçimler sync/karma_map.py’de sabittir.' },
        { h: 'Canlı', t: 'Her sembol kendi seçili kaynağından beslenir (MAIN→mode=live, IMPULSE→mode=impulse) ve çıkışı seçilen modele göre takip edilir. Kendi tarayıcısı yoktur; mevcut canlı sinyalleri yeniden etiketler.' },
        { h: '2026 sonucu', t: 'En iyi tek saf akımın (IMPULSE/Tam) üzerinde toplam R üretir — sembol-bazlı uyarlama kazandırır.' },
      ],
      caveat: 'Hücre seçimi 2026 verisi üzerinde yapıldı (in-sample) — bu bir üst sınırdır, forward beklenti daha düşüktür.',
    },
    en: {
      title: 'KARMA ½', tagline: 'Per-symbol best-cell (7/40 symbols ½TP, rest full)',
      summary: 'Not one-size-fits-all: it picks the most profitable construct per symbol. The winning cell of the 2×2 matrix {MAIN / IMPULSE} signals × {full TP / ½TP} exit is used for each symbol.',
      sections: [
        { h: 'How it picks', t: 'For each symbol all 4 cells are run across 2026 and the highest-total-R winner is chosen. E.g. one symbol trades IMPULSE/full, another MAIN/½TP. Selections are frozen in sync/karma_map.py.' },
        { h: 'Live', t: 'Each symbol is fed by its chosen source (MAIN→mode=live, IMPULSE→mode=impulse) and tracked under the selected exit. It has no scanner of its own; it re-tags existing live signals.' },
        { h: '2026 result', t: 'Beats the best single pure stream (IMPULSE/full) on total R — per-symbol adaptation pays off.' },
      ],
      caveat: 'Cell selection was made on 2026 data (in-sample) — it is an upper bound; forward expectancy is lower.',
    },
  },
  opus: {
    icon: '🕐', accent: '#0ECB81',
    tr: {
      title: 'OPUS', tagline: 'Sembole özel NY seans penceresi',
      summary: 'Doğru sembolü doğru saatte: MAIN sinyallerini alır, ama her sembol yalnızca 2026’da edge taşıdığı NY borsa seansında işlenir. Sembol×saat analizinden türetildi.',
      sections: [
        { h: 'Seans kapısı', t: 'İki pencere (DST-duyarlı, NY saati): NY-AM 09:00–12:00 ET ve NY-PM 12:00–16:00 ET. Yalnızca hafta içi — US borsası kapalı olduğu için Cmt/Paz sinyalleri (kripto 7/24 üretse de) elenir. Bar bu pencereye düşmüyorsa atlanır.' },
        { h: 'Sembol başına', t: '18 seçili sembol. Çoğu yalnızca NY-AM (BTC, ETH, BNB, S, CRCL, ONDO, XAG, SUI, INTC); yalnızca NY-PM (WIF, PEPE, COIN, HOOD, LINK, DOGE); üçü her iki seans (ARB, FET, MSTR). 2026-06-13 eklenen kriptodan LINK/DOGE NY-PM edge’iyle girdi; XRP/AVAX (ve ADA/PLTR/XAU/TSLA) pozitif seansı olmadığı için elenir.' },
        { h: 'Çıkış & evren', t: 'MAIN ile aynı tam-TP çıkış ve risk; tek fark sinyal-emisyonundaki sembol+seans kapısı. 1h sinyal, 1m çözümleme.' },
        { h: '2026 sonucu', t: 'Hafta içi, in-sample ≈ +157R / işlem başına ≈ +0.73R (18 sembol) — yüksek seçicilik, MAIN’in geniş düşük-edge’li ortalamasının çok üstünde. Hafta sonu (US kapalı) işlemleri elenir.' },
      ],
      caveat: 'Saat × sembol seçimi 2026 üzerinde yapıldı (in-sample). COIN/HOOD örneklemleri küçük. Forward’da küçülmeyi bekle; split-half doğrulaması önerilir.',
    },
    en: {
      title: 'OPUS', tagline: 'Per-symbol NY-session window',
      summary: 'Right symbol, right hour: it takes MAIN signals, but each symbol trades only in the NY market session where it carried an edge in 2026. Derived from the symbol×hour analysis.',
      sections: [
        { h: 'Session gate', t: 'Two windows (DST-aware, NY time): NY-AM 09:00–12:00 ET and NY-PM 12:00–16:00 ET. Weekdays only — Sat/Sun signals are dropped (US market closed, even though 24/7 crypto produces them). Bars outside the window are skipped.' },
        { h: 'Per symbol', t: '18 chosen symbols. Most are NY-AM only (BTC, ETH, BNB, S, CRCL, ONDO, XAG, SUI, INTC); NY-PM only (WIF, PEPE, COIN, HOOD, LINK, DOGE); three trade both (ARB, FET, MSTR). Of the 2026-06-13 crypto re-adds, LINK/DOGE qualified on NY-PM; XRP/AVAX (and ADA/PLTR/XAU/TSLA) have no positive session and are dropped.' },
        { h: 'Exit & universe', t: 'Same full-TP exit and risk as MAIN; the only change is the per-symbol+session gate on emission. 1h signals, 1m resolution.' },
        { h: '2026 result', t: 'Weekdays only, in-sample ≈ +157R / ≈ +0.73R per trade (18 symbols) — highly selective, well above MAIN’s broad low-edge average. Weekend (US-closed) trades are dropped.' },
      ],
      caveat: 'Hour × symbol selection is in-sample (2026). COIN/HOOD samples are small. Expect shrinkage forward; a split-half validation is recommended.',
    },
  },
  donchian: {
    icon: '⛰️', accent: '#F0B90B',
    tr: {
      title: 'DONCHIAN', tagline: 'Donchian-55 breakout — güçlü trend (momentum tamamlayıcı)',
      summary: 'RANGE/MAIN’in tersi yönde bir trend-takip kaynağı. MAIN setimiz aslında bir RANGE stratejisi (R’sinin ~%85-90’ı light bantta, güçlü trendde başabaş–negatif). DONCHIAN tam da o boşluğu doldurur: fiyat son 55 barın ekstremini kırınca trende katılır ve YALNIZCA güçlü-trend rejiminde (Kaufman ER ≥ 0.35) ateşler — yani MAIN’in kaybettiği yerde kazanır (düşük örtüşme = gerçek çeşitlendirme).',
      sections: [
        { h: 'Sinyal mantığı', t: 'Taze Donchian(55) kırılımı (1h kapanış): close son 55 barın en yükseğini aşarsa LONG, en düşüğünü kırarsa SHORT. Sustained breakout’ta bir kez ateşler (her barda değil). Sebepsel: kanal current barı dışlar (shift(1)), look-ahead yok.' },
        { h: 'Rejim kapısı', t: 'Kaufman Efficiency Ratio (24 bar) ≥ 0.35 — yalnızca GÜÇLÜ trend. ER-kovası kanıtı: kazancın tamamı ER>0.35’te (+122R), chop/light bantta zarar — yani MAIN’in yaşadığı rejimde para basmaz, onun bıraktığını toplar.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2; hedef = sabit R/R = 4 (geniş hedef, trend-takip imzası). Tam-TP, kısmi yok. %0.1 round-trip ücret. Düşük WR (~%27) / büyük kazananlar — 4-5 ardışık kayıp normaldir.' },
        { h: '2026 sonucu', t: 'Tam 2026 (Oca–Haz), 1m çözümleme, 5 sembol: toplam +117.5R, WR %27, 448 işlem. XAU +43.6 / XAG +40.0 / BTC +14.1 / ETH +13.8 / SOL +5.9 — hepsi pozitif (metaller H1’de sert trend yaptı).' },
        { h: 'Evren', t: 'BTC, ETH, SOL, XAU, XAG (“temel” set). XAG DAHİL: eski −17R drag trailing-exit’e özgüydü; sabit-TP modelde nötr-pozitif. 2025 OOS sonrası genişletilebilir.' },
      ],
      caveat: 'In-sample (yalnız 2026) — size güvenmeden önce 2025 OOS şart (sync/donchian/backtest.py --start 2025-01-01 --end 2026-01-01). Parametreler (55/ER0.35/RR4) optimize edilmedi ama tek bir makul set; canlı yayın için VM’de cron aktive edilmeli.',
    },
    en: {
      title: 'DONCHIAN', tagline: 'Donchian-55 breakout — strong trend (momentum complement)',
      summary: 'A trend-following source that fires opposite to RANGE/MAIN. Our MAIN set is really a RANGE strategy (~85-90% of its R lives in the light band; it is break-even-to-negative in strong trends). DONCHIAN fills exactly that gap: it joins the trend when price breaks the 55-bar extreme and fires ONLY in the strong-trend regime (Kaufman ER ≥ 0.35) — i.e. it earns where MAIN loses (low overlap = true diversification).',
      sections: [
        { h: 'Signal logic', t: 'Fresh Donchian(55) breakout (1h close): LONG if close exceeds the prior 55-bar high, SHORT if it breaks the low. Fires once per sustained breakout (not every bar). Causal: the channel excludes the current bar (shift(1)), no look-ahead.' },
        { h: 'Regime gate', t: 'Kaufman Efficiency Ratio (24 bars) ≥ 0.35 — STRONG trend only. ER-bucket proof: all of the profit is in ER>0.35 (+122R) while it loses in the chop/light bands — so it does not compete with MAIN’s regime, it harvests what MAIN leaves.' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2; target = fixed R/R = 4 (wide target, the trend-follower signature). Full-TP, no partial. 0.1% round-trip fee. Low WR (~27%) / large winners — 4-5 consecutive losers is normal.' },
        { h: '2026 result', t: 'Full 2026 (Jan–Jun), 1m resolution, 5 symbols: total +117.5R, WR 27%, 448 trades. XAU +43.6 / XAG +40.0 / BTC +14.1 / ETH +13.8 / SOL +5.9 — all positive (metals trended hard in H1).' },
        { h: 'Universe', t: 'BTC, ETH, SOL, XAU, XAG (the “basic” set). XAG INCLUDED: the old −17R drag was trailing-exit specific; in the fixed-TP model it is neutral-positive. Extend after 2025 OOS.' },
      ],
      caveat: 'In-sample (2026 only) — run 2025 OOS before trusting size (sync/donchian/backtest.py --start 2025-01-01 --end 2026-01-01). Parameters (55/ER0.35/RR4) are unoptimised but a single sensible set; going live needs the VM cron activated.',
    },
  },
  range: {
    icon: '⬍', accent: '#2EC5C5',
    tr: {
      title: 'RANGE', tagline: 'Range-sapma fade (Burak PA) — yatay piyasa',
      summary: 'ICT setinden bağımsız bir mean-reversion kaynağı: bir yatay aralık (range) çizilir; fiyat sınırın dışına taşıp tekrar içeri kapanınca (deviation) bunu karşı uca doğru fade eder. Yatay/range piyasada çalışması için tasarlandı.',
      sections: [
        { h: 'Sinyal mantığı', t: '~4 günlük (96 bar) pencerede high/low/EQ ile bir range tanımlanır (genişlik 2.5–12 ATR arası olmalı). Fiyat sınırı ≥0.25 ATR aşıp içeri kapanırsa = sapma → ters yöne fade. SL sapma ekstreminin ötesi, TP karşı range ucu; R/R tabanı 1.5, tavanı 3 (uçuk hedef yok).' },
        { h: 'Rejim kapısı', t: 'Yalnızca 4h Efficiency Ratio ≥ 0.20 iken üretilen sinyaller tutulur — DERIN choppy (ER<0.20) elenir, çünkü orada range sürekli whipsaw yapar (2026: deep-chop −5R; light +25R, mid +15R).' },
        { h: 'Çıkış', t: 'TAM TP (kısmi-TP YOK): RANGE_DEV’de ½TP+başa-baş toplam R’yi batırıyor (+37R → −11R), o yüzden tek seferde hedefe taşınır.' },
        { h: '2026 sonucu', t: 'Tam-TP, ER≥0.20, 29 sembol: toplam +41.6R, WR %31, işlem başı +0.12R (light +25 / mid +15 / strong ~0). ICT sinyallerinden farklı bir mantık → light rejimini ikinci bir yoldan hasat eder (çeşitlendirme).' },
        { h: 'Evren', t: 'XRP/DOGE/LINK/AVAX HARİÇ — bu 4 sembolde range-fade çalışmıyor (2026 −35R; dump/trend ediyorlar, fade stop yiyor). Kalan 29 sembolde işler.' },
      ],
      caveat: 'Yalnızca backtest — canlı tarayıcı henüz yok (emisyon için ayrı bir DAG işi gerekir). Parametreler bizim Burak kodifikasyonumuz; eşik/band ve evren seçimi 2026 üzerinde (in-sample) — out-of-sample doğrulanmalı.',
    },
    en: {
      title: 'RANGE', tagline: 'Range-deviation fade (Burak PA) — sideways markets',
      summary: 'A mean-reversion source independent of the ICT set: draw a horizontal range; when price pokes outside a boundary and closes back inside (a deviation), fade it toward the opposite side. Built to work in sideways/ranging markets.',
      sections: [
        { h: 'Signal logic', t: 'A range (high/low/EQ) is established over ~4 days (96 bars); width must be 2.5–12 ATR. If price exceeds a boundary by ≥0.25 ATR and closes back inside = deviation → fade the other way. SL beyond the deviation extreme, TP the opposite range end; R/R floor 1.5, cap 3.' },
        { h: 'Regime gate', t: 'Keep only signals fired with 4h Efficiency Ratio ≥ 0.20 — DEEP chop (ER<0.20) is dropped because the range just whipsaws there (2026: deep-chop −5R; light +25R, mid +15R).' },
        { h: 'Exit', t: 'FULL TP (NO partial): on RANGE_DEV a ½TP+breakeven exit sinks total R (+37R → −11R), so it rides to target in one piece.' },
        { h: '2026 result', t: 'Full-TP, ER≥0.20, 29 symbols: total +41.6R, WR 31%, +0.12R/trade (light +25 / mid +15 / strong ~0). A different logic from the ICT signals → harvests the light regime by a second route (diversification).' },
        { h: 'Universe', t: 'EXCLUDES XRP/DOGE/LINK/AVAX — range-fade fails on those 4 (2026 −35R; they dump/trend, the fade gets stopped). Works on the other 29.' },
      ],
      caveat: 'Backtest only — no live scanner yet (emission would need a dedicated DAG job). Parameters are our codification of Burak; the threshold/band and universe choice are in-sample (2026) — validate out-of-sample.',
    },
  },
  range_q: {
    icon: '⬍', accent: '#0ECB81',
    tr: {
      title: 'RANGE+', tagline: 'Yüksek-konviksiyon RANGE (SL-paterni filtreli)',
      summary: 'RANGE ile AYNI range-sapma fade — ama SL analizinde bulduğumuz iki kaybeden özelliği eler: zayıf trend ve düşük ödül. Daha az ama belirgin daha yüksek-kaliteli işlem; OOS’ta daha sağlam.',
      sections: [
        { h: 'Ek kapı', t: 'RANGE’in ensemble-trend kapısına EK olarak: (1) ensemble skoru ≥ 0.30 (zayıf [0.20–0.30) trend bandı elenir — asıl SL kümesi orada), (2) ödül/risk ≥ 2.0 (RR<2 fade’ler matematiksel olarak −EV).' },
        { h: 'SL paterni', t: 'İki yılda da tutarlı kaybedenler: zayıf-trend [0.20–0.30) skor + RR<2 + çok dar stop (<%1). Confluence “swept” bonusu (conf9) ise 2026’da iyi ama 2025’te negatif → güvenilmez, gate yapılmadı.' },
        { h: 'Sonuç (analiz)', t: 'RR≥2 & skor≥0.30: 2026 +45.9R / işlem-başı +0.51 (RANGE: +0.32); 2025 OOS +15.8R / +0.16 (RANGE: +0.04 — ~4 kat). Toplam R düşer ama beklenti ve OOS sağlamlığı belirgin artar.' },
        { h: 'Geri kalan', t: 'Çıkış (tam-TP), evren (29 sembol, XRP/DOGE/LINK/AVAX hariç), çözümleme (1m) RANGE ile birebir. Sadece backtest.' },
      ],
      caveat: 'Eşikler (skor 0.30, RR 2.0) 2026 SL-analizinden seçildi; 2025’te de tuttu ama yine de çok-yıllı/walk-forward doğrulama şart. Yalnızca backtest — canlı tarayıcı yok.',
    },
    en: {
      title: 'RANGE+', tagline: 'High-conviction RANGE (SL-pattern filtered)',
      summary: 'The SAME range-deviation fade as RANGE — but it drops the two loser traits the SL study found: weak trend and low reward. Fewer but markedly higher-quality trades; more robust out-of-sample.',
      sections: [
        { h: 'Extra gate', t: 'On top of RANGE’s ensemble-trend gate: (1) ensemble score ≥ 0.30 (drops the weak [0.20–0.30) trend band — the main SL cluster), (2) reward/risk ≥ 2.0 (RR<2 fades are mathematically −EV).' },
        { h: 'SL pattern', t: 'Consistent losers both years: weak-trend [0.20–0.30) score + RR<2 + very tight stop (<1%). The confluence “swept” bonus (conf9) was good in 2026 but negative in 2025 → unreliable, not gated on.' },
        { h: 'Result (analysis)', t: 'RR≥2 & score≥0.30: 2026 +45.9R / +0.51 per trade (RANGE: +0.32); 2025 OOS +15.8R / +0.16 (RANGE: +0.04 — ~4×). Total R drops but expectancy and OOS robustness rise sharply.' },
        { h: 'Rest', t: 'Exit (full-TP), universe (29 symbols, ex-XRP/DOGE/LINK/AVAX), resolution (1m) identical to RANGE. Backtest only.' },
      ],
      caveat: 'Thresholds (score 0.30, RR 2.0) were chosen on the 2026 SL analysis; they held in 2025 too but still need multi-year / walk-forward validation. Backtest only — no live scanner.',
    },
  },
};

// LIGHT band-pass twins: keep only signals fired in the light-trend regime
// (4h ER 0.20-0.35), where the 2026 routing audit found our edge actually lives.
const LIGHT_SECTION = {
  tr: { h: 'Light-rejim filtresi', t: 'Ebeveyn akımla AYNI sinyaller — fakat YALNIZCA sembolün 4h Efficiency Ratio’su 0.20–0.35 (light trend) bandındayken üretilenler tutulur. 2026 rejim-yönlendirme analizi, ICT setimizin asıl edge’inin bu bantta olduğunu gösterdi (güçlü/orta trendde başabaş–negatif, orta bant MAIN’de zarar). İşlemlerin yalnızca ~%22’si kalır; işlem başı beklenti her akımda belirgin yükselir. Ekside olan ½TP akımlarını artıya çevirir (MAIN ½TP −39→+36R, IMPULSE ½TP −13→+40R, KARMA ½TP +0→+43R); MAIN’de toplam R’yi de yükseltir (+39→+55R). Zaten güçlü tam-TP akımlarda (IMPULSE +76→+59R, KARMA +109→+75R) işlem sayısı düştüğü için toplam R düşer ama beklenti çok artar.' },
  en: { h: 'Light-regime filter', t: 'SAME signals as the parent — but ONLY those fired while the symbol’s 4h Efficiency Ratio was in the 0.20–0.35 (light-trend) band. The 2026 regime-routing audit found this is where our ICT set’s edge actually lives (strong/mid trend is break-even-to-negative; the mid band loses on MAIN). Only ~22% of trades survive, but per-trade expectancy rises sharply on every stream. It flips the losing ½TP streams positive (MAIN ½TP −39→+36R, IMPULSE ½TP −13→+40R, KARMA ½TP +0→+43R) and lifts MAIN’s total R (+39→+55R). On the already-strong full-TP streams (IMPULSE +76→+59R, KARMA +109→+75R) total R is lower because volume drops, but expectancy is far higher.' },
};

// 1h-regime twins: same RANGE_DEV signals, but the ensemble gate is computed on 1h
// bars instead of 4h (window 150 1h ≈ 6 days vs 150 4h ≈ 25 days). Full RANGE universe.
const REGIME_1H_SECTION = {
  tr: { h: '1h rejim kapısı (deneysel)', t: 'Ebeveyn akımla AYNI RANGE_DEV sinyalleri — fakat rejim ensemble’i (6 dedektör) 4h yerine 1h barlar üzerinden hesaplanır (daha kısa, ~6 günlük pencere). 4h rejimiyle karşılaştırmak için tüm sembollerde, 2026. Sonuç: 1h, 4h’ten DAHA KÖTÜ — range·1h +42.0R (177 işlem) vs range 4h +60.7R; range+·1h +33.5R (111) vs range+ 4h +49.6R. 4h’in daha uzun (~25 gün) penceresi, deviation-fade’in karşı sınıra ulaşması için gereken geniş yönsel persistansı daha iyi yakalıyor; 1h penceresi gürültülü ve çok sinyali erken trend-DIŞı sayıyor. range·1h yine de net pozitif (kitabın ~%30 altında).' },
  en: { h: '1h regime gate (experimental)', t: 'SAME RANGE_DEV signals as the parent — but the 6-detector regime ensemble is computed on 1h bars instead of 4h (a ~6-day window vs ~25 days). Full universe, 2026, to compare against the 4h gate. Result: 1h is WORSE than 4h — range·1h +42.0R (177 trades) vs range 4h +60.7R; range+·1h +33.5R (111) vs range+ 4h +49.6R. The 4h’s longer (~25-day) window better captures the broad directional persistence a deviation-fade needs to reach the opposite boundary; the 1h window is noisier and tags many signals NON-trend too early. range·1h is still net-positive (~30% below the book).' },
};

export const infoFor = (strategy, lang) => {
  const isLight = strategy.endsWith('_light');
  const is1h = strategy.endsWith('_1h');
  const baseKey = isLight ? strategy.slice(0, -6) : is1h ? strategy.slice(0, -3) : strategy;
  const e = STRATEGY_INFO[baseKey];
  if (!e) return null;
  const info = { icon: e.icon, accent: e.accent, ...(e[lang] || e.tr) };
  if (isLight) {
    const ls = LIGHT_SECTION[lang] || LIGHT_SECTION.tr;
    return {
      ...info,
      title: `${info.title} · Light`,
      tagline: lang === 'en' ? `${info.tagline} + light-regime filter` : `${info.tagline} + light-rejim filtre`,
      sections: [ls, ...(info.sections || [])],
    };
  }
  if (is1h) {
    const rs = REGIME_1H_SECTION[lang] || REGIME_1H_SECTION.tr;
    return {
      ...info,
      title: `${info.title} · 1h`,
      tagline: lang === 'en' ? `${info.tagline} + 1h-regime gate` : `${info.tagline} + 1h-rejim kapısı`,
      sections: [rs, ...(info.sections || [])],
    };
  }
  return info;
};
