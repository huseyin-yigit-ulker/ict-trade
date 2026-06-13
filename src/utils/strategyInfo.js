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
};

// LIGHT band-pass twins: keep only signals fired in the light-trend regime
// (4h ER 0.20-0.35), where the 2026 routing audit found our edge actually lives.
const LIGHT_SECTION = {
  tr: { h: 'Light-rejim filtresi', t: 'Ebeveyn akımla AYNI sinyaller — fakat YALNIZCA sembolün 4h Efficiency Ratio’su 0.20–0.35 (light trend) bandındayken üretilenler tutulur. 2026 rejim-yönlendirme analizi, ICT setimizin asıl edge’inin bu bantta olduğunu gösterdi (güçlü/orta trendde başabaş–negatif, orta bant MAIN’de zarar). İşlemlerin yalnızca ~%22’si kalır; işlem başı beklenti her akımda belirgin yükselir. Ekside olan ½TP akımlarını artıya çevirir (MAIN ½TP −39→+36R, IMPULSE ½TP −13→+40R, KARMA ½TP +0→+43R); MAIN’de toplam R’yi de yükseltir (+39→+55R). Zaten güçlü tam-TP akımlarda (IMPULSE +76→+59R, KARMA +109→+75R) işlem sayısı düştüğü için toplam R düşer ama beklenti çok artar.' },
  en: { h: 'Light-regime filter', t: 'SAME signals as the parent — but ONLY those fired while the symbol’s 4h Efficiency Ratio was in the 0.20–0.35 (light-trend) band. The 2026 regime-routing audit found this is where our ICT set’s edge actually lives (strong/mid trend is break-even-to-negative; the mid band loses on MAIN). Only ~22% of trades survive, but per-trade expectancy rises sharply on every stream. It flips the losing ½TP streams positive (MAIN ½TP −39→+36R, IMPULSE ½TP −13→+40R, KARMA ½TP +0→+43R) and lifts MAIN’s total R (+39→+55R). On the already-strong full-TP streams (IMPULSE +76→+59R, KARMA +109→+75R) total R is lower because volume drops, but expectancy is far higher.' },
};

export const infoFor = (strategy, lang) => {
  const isLight = strategy.endsWith('_light');
  const baseKey = isLight ? strategy.slice(0, -6) : strategy;
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
  return info;
};
