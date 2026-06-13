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
  main_half: {
    icon: '🎯', accent: '#F5B942',
    tr: {
      title: 'MAIN ½TP', tagline: 'MAIN + kısmi kâr / başa-baş çıkış',
      summary: 'MAIN ile aynı sinyaller, farklı çıkış disiplini: hızlı kısmi kâr al, kalanı risksiz bırak. Sermayeyi koruma odaklı (prop-firm mantığı).',
      sections: [
        { h: 'Çıkış modeli', t: 'Giriş→TP1 mesafesinin yarısında pozisyonun %50’si kapatılır ve stop girişe (başa-baş) çekilir. Kalan %50 TP1’e kadar taşınır. Kısmi alımdan sonra işlem tam zarara dönemez.' },
        { h: 'Etki', t: 'İsabet oranı belirgin artar (~+10 puan), ama toplam R düşer — çünkü edge büyük “runner”larda yaşıyor ve başa-baş stop onları erken kesiyor. Harmanlanmış maksimum ≈ 0.75×R/R.' },
        { h: 'Aynı kalanlar', t: 'Giriş, SL, TP geometrisi ve sembol evreni MAIN ile aynı; sadece çıkış davranışı değişir. MAIN ↔ MAIN ½TP temiz bir A/B.' },
      ],
    },
    en: {
      title: 'MAIN ½TP', tagline: 'MAIN + partial take-profit / breakeven',
      summary: 'Same signals as MAIN, different exit discipline: bank partial profit fast, leave the rest risk-free. Capital-preservation focused (prop-firm logic).',
      sections: [
        { h: 'Exit model', t: 'At half the entry→TP1 distance, 50% is closed and the stop moves to entry (breakeven). The remaining 50% rides to TP1. After the partial, the trade can no longer become a full loss.' },
        { h: 'Effect', t: 'Win rate rises markedly (~+10 pts) but total R falls — the edge lives in the big runners and the breakeven stop cuts them early. Blended max ≈ 0.75×R/R.' },
        { h: 'Unchanged', t: 'Entry, SL, TP geometry and symbol universe identical to MAIN; only exit behaviour differs. MAIN ↔ MAIN ½TP is a clean A/B.' },
      ],
    },
  },
  impulse_half: {
    icon: '⚡', accent: '#5C93FF',
    tr: {
      title: 'IMPULSE ½TP', tagline: 'IMPULSE + kısmi kâr / başa-baş çıkış',
      summary: 'IMPULSE’in rafine sinyalleri, MAIN ½TP ile aynı kısmi-TP + başa-baş çıkış modeli altında.',
      sections: [
        { h: 'Çıkış modeli', t: 'Yolun yarısında %50 kapat, stop’u girişe çek, kalanı TP1’e taşı. Kısmi sonrası tam zarar yok.' },
        { h: 'Etki', t: 'IMPULSE’e göre daha yüksek isabet, daha düşük toplam R. ½TP, trende bağımlı (yalın) IMPULSE’i biraz daha sert vurur.' },
        { h: 'Aynı kalanlar', t: 'IMPULSE sinyalleri ve evreni birebir; yalnızca çıkış değişir.' },
      ],
    },
    en: {
      title: 'IMPULSE ½TP', tagline: 'IMPULSE + partial take-profit / breakeven',
      summary: 'IMPULSE’s refined signals under the same partial-TP + breakeven exit as MAIN ½TP.',
      sections: [
        { h: 'Exit model', t: 'Close 50% at half-distance, pull the stop to entry, ride the rest to TP1. No full loss after the partial.' },
        { h: 'Effect', t: 'Higher hit-rate, lower total R than IMPULSE. ½TP hits the leaner, more trend-dependent IMPULSE a bit harder.' },
        { h: 'Unchanged', t: 'IMPULSE signals and universe identical; only the exit changes.' },
      ],
    },
  },
  karma: {
    icon: '🜲', accent: '#A78BFA',
    tr: {
      title: 'KARMA', tagline: 'Sembol başına en iyi hücre seçimi',
      summary: 'Tek beden değil: her sembol için en kârlı yapıyı seçer. {MAIN / IMPULSE} sinyal seti × {Tam TP / ½TP} çıkışı 2×2 matrisinin, o sembolde en yüksek R veren hücresi kullanılır.',
      sections: [
        { h: 'Nasıl seçer', t: 'Her sembolde 4 hücre 2026 boyunca koşulur, toplam R’ye göre kazanan seçilir. Örn. bir sembol IMPULSE/Tam, bir başkası MAIN/½TP altında işlenir. Seçimler sync/karma_map.py’de sabittir.' },
        { h: 'Canlı', t: 'Her sembol kendi seçili kaynağından beslenir (MAIN→mode=live, IMPULSE→mode=impulse) ve çıkışı seçilen modele göre takip edilir. Kendi tarayıcısı yoktur; mevcut canlı sinyalleri yeniden etiketler.' },
        { h: '2026 sonucu', t: 'En iyi tek saf akımın (IMPULSE/Tam) üzerinde toplam R üretir — sembol-bazlı uyarlama kazandırır.' },
      ],
      caveat: 'Hücre seçimi 2026 verisi üzerinde yapıldı (in-sample) — bu bir üst sınırdır, forward beklenti daha düşüktür.',
    },
    en: {
      title: 'KARMA', tagline: 'Per-symbol best-cell selection',
      summary: 'Not one-size-fits-all: it picks the most profitable construct per symbol. The winning cell of the 2×2 matrix {MAIN / IMPULSE} signals × {full TP / ½TP} exit is used for each symbol.',
      sections: [
        { h: 'How it picks', t: 'For each symbol all 4 cells are run across 2026 and the highest-total-R winner is chosen. E.g. one symbol trades IMPULSE/full, another MAIN/½TP. Selections are frozen in sync/karma_map.py.' },
        { h: 'Live', t: 'Each symbol is fed by its chosen source (MAIN→mode=live, IMPULSE→mode=impulse) and tracked under the selected exit. It has no scanner of its own; it re-tags existing live signals.' },
        { h: '2026 result', t: 'Beats the best single pure stream (IMPULSE/full) on total R — per-symbol adaptation pays off.' },
      ],
      caveat: 'Cell selection was made on 2026 data (in-sample) — it is an upper bound; forward expectancy is lower.',
    },
  },
  karma_half: {
    icon: '🜲', accent: '#A78BFA',
    tr: {
      title: 'KARMA ½TP', tagline: 'KARMA seti, her zaman ½TP çıkış',
      summary: 'KARMA’nın sembol-bazlı kaynak seçimini korur, ama çıkışı her sembolde kısmi-TP + başa-baş’a sabitler. MAIN→MAIN ½TP, IMPULSE→IMPULSE ½TP ilişkisinin KARMA karşılığı.',
      sections: [
        { h: 'Mantık', t: 'Her sembol KARMA’da seçtiği kaynak seti (MAIN ya da IMPULSE) kullanır; fakat exit modeli serbest bırakılmaz — daima yarıda %50 al + başa-baş.' },
        { h: 'Etki', t: 'KARMA’ya göre daha yüksek isabet, daha düşük toplam R (evrensel ½TP takası). Sermaye koruma önceliğinde tercih edilir.' },
      ],
      caveat: 'Kaynak seçimi in-sample (2026); yalnızca çıkış modeli zorlanır.',
    },
    en: {
      title: 'KARMA ½TP', tagline: 'KARMA set, always ½TP exit',
      summary: 'Keeps KARMA’s per-symbol source selection but forces the exit to partial-TP + breakeven on every symbol. The KARMA analog of MAIN→MAIN ½TP and IMPULSE→IMPULSE ½TP.',
      sections: [
        { h: 'Logic', t: 'Each symbol uses its KARMA-chosen source set (MAIN or IMPULSE); the exit is no longer free — always 50% at half-distance + breakeven.' },
        { h: 'Effect', t: 'Higher hit-rate, lower total R than KARMA (the universal ½TP trade-off). Preferred when capital preservation comes first.' },
      ],
      caveat: 'Source selection is in-sample (2026); only the exit is forced.',
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
  opus_half: {
    icon: '🕐', accent: '#0ECB81',
    tr: {
      title: 'OPUS ½TP', tagline: 'OPUS kapısı + kısmi kâr / başa-baş',
      summary: 'OPUS ile birebir aynı sinyaller (MAIN seti + sembol-bazlı hafta-içi NY seans kapısı), ama çıkış kısmi-TP + başa-baş’a sabit. OPUS’un MAIN ½TP / KARMA ½TP karşılığı.',
      sections: [
        { h: 'Çıkış modeli', t: 'Giriş→TP1 yarısında %50 kapat, stop’u girişe çek; kalan yarı TP1’e taşınır. Kısmi sonrası tam zarar yok.' },
        { h: 'Kapı', t: 'OPUS ile aynı: yalnızca hafta içi NY-AM (09:00–12:00 ET) / NY-PM (12:00–16:00 ET), sembol-bazlı allowlist. Cmt/Paz elenir.' },
        { h: 'Etki', t: 'OPUS’a göre daha yüksek isabet, daha düşük toplam R — diğer ½TP akımlarındaki evrensel takasla aynı. Sermaye koruma önceliğinde.' },
      ],
      caveat: 'Saat × sembol seçimi in-sample (2026); yalnızca çıkış modeli zorlanır.',
    },
    en: {
      title: 'OPUS ½TP', tagline: 'OPUS gate + partial take-profit / breakeven',
      summary: 'Exactly the same signals as OPUS (MAIN set + per-symbol weekday NY-session gate), but the exit is fixed to partial-TP + breakeven. The OPUS analog of MAIN ½TP / KARMA ½TP.',
      sections: [
        { h: 'Exit model', t: 'Close 50% at half the entry→TP1 distance, pull the stop to entry; the rest rides to TP1. No full loss after the partial.' },
        { h: 'Gate', t: 'Same as OPUS: weekdays only, NY-AM (09:00–12:00 ET) / NY-PM (12:00–16:00 ET), per-symbol allowlist. Sat/Sun dropped.' },
        { h: 'Effect', t: 'Higher hit-rate, lower total R than OPUS — the same universal trade-off as the other ½TP streams. For capital-preservation priority.' },
      ],
      caveat: 'Hour × symbol selection is in-sample (2026); only the exit is forced.',
    },
  },
};

export const infoFor = (strategy, lang) => {
  const e = STRATEGY_INFO[strategy];
  if (!e) return null;
  return { icon: e.icon, accent: e.accent, ...(e[lang] || e.tr) };
};
