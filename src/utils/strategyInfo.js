// Per-strategy intro-card content, bilingual (tr / en). Rendered at the top of the
// dashboard by StrategyIntro.jsx. Keep each card short: tagline + 2-3 bullets + an
// optional caveat (shown for the in-sample-selected blends).

export const STRATEGY_INFO = {
  main: {
    icon: '🎯', accent: '#F5B942',
    tr: {
      title: 'MAIN', tagline: 'ICT ana strateji seti (v1)',
      bullets: [
        'Strateji B/C/D/E: likidite süpürme + CHoCH, OB/FVG konfluansı, Silver Bullet killzone’ları.',
        'Tek çıkış: pozisyon hedefe (TP1) kadar tek parça taşınır.',
        '1 saatlik sinyal, 4 saatlik HTF yönü; tüm üretim sembolleri.',
      ],
    },
    en: {
      title: 'MAIN', tagline: 'Core ICT strategy set (v1)',
      bullets: [
        'Strategies B/C/D/E: liquidity sweep + CHoCH, OB/FVG confluence, Silver Bullet killzones.',
        'Single exit: the position rides in one piece to its target (TP1).',
        '1h signals, 4h HTF bias; full production universe.',
      ],
    },
  },
  impulse: {
    icon: '⚡', accent: '#5C93FF',
    tr: {
      title: 'IMPULSE', tagline: 'MAIN’in rafine hali (v2)',
      bullets: [
        'Strateji E atıldı (2026’da 0 sinyal); Silver Bullet (D) zayıf sembollerde (ADA/XAU/ETH) kapatıldı.',
        'Daha az ama daha temiz sinyal — işlem başına beklenti daha yüksek.',
        'Aynı motor, çıkış ve risk; sadece set + sembol kapsamı daralır.',
      ],
    },
    en: {
      title: 'IMPULSE', tagline: 'Refined MAIN (v2)',
      bullets: [
        'Strategy E dropped (0 signals in 2026); Silver Bullet (D) disabled on weak symbols (ADA/XAU/ETH).',
        'Fewer but cleaner signals — higher expectancy per trade.',
        'Same engine, exit and risk; only the set + symbol scope narrows.',
      ],
    },
  },
  main_half: {
    icon: '🎯', accent: '#F5B942',
    tr: {
      title: 'MAIN ½TP', tagline: 'MAIN + kısmi kâr / başa-baş',
      bullets: [
        'Yolun yarısında pozisyonun %50’si kapatılır, stop girişe (başa-baş) çekilir.',
        'Kalan yarısı TP1’e kadar risksiz taşınır.',
        'Win rate artar, toplam R düşer — kazanç büyük runner’larda kalır.',
      ],
    },
    en: {
      title: 'MAIN ½TP', tagline: 'MAIN + partial take-profit / breakeven',
      bullets: [
        'At half the distance to target, 50% is closed and the stop moves to entry (breakeven).',
        'The remaining half rides risk-free to TP1.',
        'Win rate rises, total R falls — the upside lives in the big runners.',
      ],
    },
  },
  impulse_half: {
    icon: '⚡', accent: '#5C93FF',
    tr: {
      title: 'IMPULSE ½TP', tagline: 'IMPULSE + kısmi kâr / başa-baş',
      bullets: [
        'IMPULSE sinyalleri, MAIN ½TP ile aynı kısmi-TP + başa-baş çıkış modeliyle.',
        'Yarıda %50 kapat, stop’u girişe çek, kalanı hedefe taşı.',
        'Daha yüksek isabet, daha düşük toplam R.',
      ],
    },
    en: {
      title: 'IMPULSE ½TP', tagline: 'IMPULSE + partial take-profit / breakeven',
      bullets: [
        'IMPULSE signals under the same partial-TP + breakeven exit as MAIN ½TP.',
        'Close 50% at half-distance, pull the stop to entry, ride the rest to target.',
        'Higher hit-rate, lower total R.',
      ],
    },
  },
  karma: {
    icon: '🜲', accent: '#A78BFA',
    tr: {
      title: 'KARMA', tagline: 'Sembol başına en iyi hücre',
      bullets: [
        'Her sembol için {MAIN / IMPULSE} × {Tam TP / ½TP} matrisinin en kârlı hücresi seçilir.',
        'Sinyal kaynağı ve çıkış modeli sembole özel — tek beden değil.',
        'Canlıda her sembol kendi seçili akımından beslenir.',
      ],
      caveat: 'Seçim 2026 verisi üzerinde yapıldı (in-sample) — gerçek beklenti daha düşüktür.',
    },
    en: {
      title: 'KARMA', tagline: 'Per-symbol best cell',
      bullets: [
        'For each symbol, the most profitable cell of {MAIN / IMPULSE} × {full TP / ½TP} is picked.',
        'Signal source AND exit model are per-symbol — not one-size-fits-all.',
        'Live, each symbol is fed by its selected stream.',
      ],
      caveat: 'Selection was made on 2026 data (in-sample) — expect less out-of-sample.',
    },
  },
  karma_half: {
    icon: '🜲', accent: '#A78BFA',
    tr: {
      title: 'KARMA ½TP', tagline: 'KARMA seti, her zaman ½TP',
      bullets: [
        'Her sembol KARMA’da seçtiği kaynak seti (MAIN/IMPULSE) korur.',
        'Ama çıkış her sembolde kısmi-TP + başa-baş’a sabitlenir.',
        'KARMA’ya göre daha yüksek isabet, daha düşük toplam R.',
      ],
      caveat: 'Kaynak seçimi in-sample (2026); yalnızca çıkış modeli zorlanır.',
    },
    en: {
      title: 'KARMA ½TP', tagline: 'KARMA set, always ½TP',
      bullets: [
        'Each symbol keeps its KARMA-chosen source set (MAIN/IMPULSE).',
        'But the exit is forced to partial-TP + breakeven on every symbol.',
        'Higher hit-rate, lower total R than KARMA.',
      ],
      caveat: 'Source selection is in-sample (2026); only the exit is forced.',
    },
  },
  opus: {
    icon: '🕐', accent: '#0ECB81',
    tr: {
      title: 'OPUS', tagline: 'Sembole özel NY seans penceresi',
      bullets: [
        'MAIN sinyalleri, ama her sembol sadece edge taşıdığı NY seansında işlenir.',
        'NY-AM 09:00–12:00 ET ve NY-PM 12:00–16:00 ET (DST-duyarlı).',
        '16 seçili sembol; ADA/PLTR/XAU/TSLA gibi yapısal negatifler tamamen elenir.',
      ],
      caveat: 'Saat × sembol seçimi 2026 üzerinde (in-sample) — out-of-sample doğrulanmalı.',
    },
    en: {
      title: 'OPUS', tagline: 'Per-symbol NY-session window',
      bullets: [
        'MAIN signals, but each symbol trades only in the NY session where it has an edge.',
        'NY-AM 09:00–12:00 ET and NY-PM 12:00–16:00 ET (DST-aware).',
        '16 chosen symbols; structural losers (ADA/PLTR/XAU/TSLA…) are dropped entirely.',
      ],
      caveat: 'Hour × symbol selection is in-sample (2026) — validate out-of-sample.',
    },
  },
};

export const infoFor = (strategy, lang) => {
  const e = STRATEGY_INFO[strategy];
  if (!e) return null;
  return { icon: e.icon, accent: e.accent, ...(e[lang] || e.tr) };
};
