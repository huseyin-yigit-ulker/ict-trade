// Per-strategy intro-card content, bilingual (tr / en). Rendered by StrategyIntro.jsx.
// Shape per language: { title, tagline, summary, sections:[{h,t}], caveat? }.
//
// 2026-06-16: pruned to a SINGLE stream — donchian. The MAIN/IMPULSE/KARMA/OPUS/RANGE/
// RANGE+ cards (and the Light / 1h-regime section twins) were removed with their streams;
// see sync/donchian/RETIRED_STREAMS_REPORT.md.

export const STRATEGY_INFO = {
  donchian: {
    icon: '⛰️', accent: '#F0B90B',
    tr: {
      title: 'DONCHIAN', tagline: 'Donchian-55 breakout — güçlü trend (momentum tamamlayıcı)',
      summary: 'Bir trend-takip stratejisi: fiyat son 55 barın ekstremini kırınca trende katılır ve YALNIZCA güçlü-trend rejiminde (Kaufman ER ≥ 0.35) ateşler. Mean-reversion sistemlerin yapısal tamamlayıcısı — getirileri düşük korelasyonlu, çünkü birbirini dışlayan rejimlerde para kazanır.',
      sections: [
        { h: 'Sinyal mantığı', t: 'Taze Donchian(55) kırılımı (1h kapanış): close son 55 barın en yükseğini aşarsa LONG, en düşüğünü kırarsa SHORT. Sustained breakout’ta bir kez ateşler (her barda değil). Sebepsel: kanal current barı dışlar (shift(1)), look-ahead yok.' },
        { h: 'Rejim kapısı', t: 'Kaufman Efficiency Ratio (24 bar) ≥ 0.35 — yalnızca GÜÇLÜ trend. ER-kovası kanıtı: kazancın tamamı ER>0.35’te, chop/light bantta zarar — yani güçlü-trend rejimini hasat eder.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2; hedef = sabit R/R = 4 (geniş hedef, trend-takip imzası). Tam-TP, kısmi yok. %0.1 round-trip ücret. Düşük WR (~%25) / büyük kazananlar — 4-5 ardışık kayıp normaldir.' },
        { h: 'Sonuçlar', t: '2026 (40 sembol, 1m): +288R, WR %23. OOS: 2025 +662R (3151 işlem), 2024 +102.5R (17 kripto, tam). Üç yılda da net pozitif — overfit değil.' },
        { h: 'Evren', t: '40 sembol (çekirdek: BTC/ETH/SOL/XAU/XAG). Trend edge’i crypto + metallerde güçlü; bazı hisse-perp’ler ve ORDI/ONDO tutarlı negatif (budama adayı).' },
      ],
      caveat: 'Parametreler (55 / ER0.35 / RR4) 2026’da seçildi; 2025+2024 OOS bu seçimi doğruladı. Slippage modellenmiyor → canlı R backtest’in biraz altında olur.',
    },
    en: {
      title: 'DONCHIAN', tagline: 'Donchian-55 breakout — strong trend (momentum complement)',
      summary: 'A trend-following strategy: it joins the trend when price breaks the 55-bar extreme and fires ONLY in the strong-trend regime (Kaufman ER ≥ 0.35). The structural complement to mean-reversion systems — returns are low-correlated because they earn in mutually exclusive regimes.',
      sections: [
        { h: 'Signal logic', t: 'Fresh Donchian(55) breakout (1h close): LONG if close exceeds the prior 55-bar high, SHORT if it breaks the low. Fires once per sustained breakout (not every bar). Causal: the channel excludes the current bar (shift(1)), no look-ahead.' },
        { h: 'Regime gate', t: 'Kaufman Efficiency Ratio (24 bars) ≥ 0.35 — STRONG trend only. ER-bucket proof: all profit is in ER>0.35 while it loses in the chop/light bands — it harvests the strong-trend regime.' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2; target = fixed R/R = 4 (wide target, the trend-follower signature). Full-TP, no partial. 0.1% round-trip fee. Low WR (~25%) / large winners — 4-5 consecutive losers is normal.' },
        { h: 'Results', t: '2026 (40 symbols, 1m): +288R, WR 23%. OOS: 2025 +662R (3151 trades), 2024 +102.5R (17 crypto, full). Net positive all three years — not overfit.' },
        { h: 'Universe', t: '40 symbols (core: BTC/ETH/SOL/XAU/XAG). The trend edge is strong on crypto + metals; some stock-perps and ORDI/ONDO are consistently negative (prune candidates).' },
      ],
      caveat: 'Parameters (55 / ER0.35 / RR4) were chosen on 2026; the 2025+2024 OOS validated that choice. Slippage is not modelled → live R will be somewhat below backtest.',
    },
  },
  dch30_4h: {
    icon: '⛰️', accent: '#F0B90B',
    tr: {
      title: 'DONCHIAN 30m+4h', tagline: 'Hybrid: 30m kırılım + 4h trend yön onayı',
      summary: 'Çok-zaman-dilimli (MTF) hibrit: 30m Donchian(55) kırılımı yalnızca 4h trendi AYNI yönü onayladığında işleme alınır (4h kapanış, 4h 55-bar Donchian orta çizgisinin trade yönünde tarafında). 2026 MTF-doğrulama panelinin kazananı — saf 30m’den belirgin üstün.',
      sections: [
        { h: 'Sinyal mantığı', t: '30m kapanış 55-bar ekstremini kırar (LONG/SHORT). Sinyal sadece 4h trend yönü teyit ederse alınır: long için 4h kapanış 4h Donchian orta çizgisinin üstünde, short için altında. Sebepsel: sinyal ateşleme anında SADECE kapanmış 4h barları kullanılır.' },
        { h: 'Neden yön, ER değil', t: 'Base sinyal zaten kendi TF’inde ER-gated. 4h ER kapısı eklemek edge’i yok ediyor (tükenmiş trendleri seçiyor); 4h YÖN hizası ise dominant trendle hizalayıp R/işlemi 2 katına çıkarıyor.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2; hedef = sabit R/R = 4. Tam-TP. %0.1 round-trip ücret.' },
        { h: 'Sonuçlar', t: '2026 (40 sembol, 1m): +349R (4h_dir), saf 30m +240R’ye karşı; R/işlem +0.058→+0.120 (2×), ~%30 daha az işlem (daha az komisyon). 2025+2024 OOS doğrulaması devam ediyor.' },
        { h: 'Evren', t: '40 sembol. Trend edge’i crypto + metallerde güçlü; ABD hisse-perp’leri negatif (budama adayı).' },
        { h: 'Seans / zaman', t: 'ABD hisse-perp’leri YALNIZCA pre-market + regular seansında (04:00–16:00 ET, hafta içi, NYSE tatilleri hariç) sinyal üretir — dışında dayanak işlem görmez, gürültüdür. Metaller ~24/5, kripto 7/24 (gate yok). Canlı durum: topbar’daki 🕑 Seanslar penceresi.' },
      ],
      caveat: '4h onayı işlem sayısını azaltır ama kaliteyi artırır. Parametre 2026’da seçildi; OOS doğrulaması bekleniyor. Canlı R backtest’in altında olur.',
    },
    en: {
      title: 'DONCHIAN 30m+4h', tagline: 'Hybrid: 30m breakout + 4h trend-direction confirm',
      summary: 'A multi-timeframe (MTF) hybrid: a 30m Donchian(55) breakout is taken only when the 4h trend confirms the SAME direction (4h close on the trade’s side of its 55-bar Donchian midline). The winner of the 2026 MTF-validation panel — clearly superior to plain 30m.',
      sections: [
        { h: 'Signal logic', t: '30m close breaks the 55-bar extreme (LONG/SHORT). Taken only if the 4h trend confirms: for long, 4h close above its 4h Donchian midline; for short, below. Causal: only 4h bars CLOSED by the signal’s fire time are consulted.' },
        { h: 'Direction, not ER', t: 'The base signal is already ER-gated on its own TF. Adding a 4h-ER gate destroys the edge (it selects exhausted trends); 4h DIRECTION alignment instead keeps trades with the dominant trend and doubles R/trade.' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2; target = fixed R/R = 4. Full-TP. 0.1% round-trip fee.' },
        { h: 'Results', t: '2026 (40 symbols, 1m): +349R (4h_dir) vs plain 30m +240R; R/trade +0.058→+0.120 (2×) on ~30% fewer trades (less fee drag). 2025+2024 OOS validation in progress.' },
        { h: 'Universe', t: '40 symbols. Trend edge is strong on crypto + metals; US stock-perps are negative (prune candidates).' },
        { h: 'Session / time', t: 'US stock-perps fire ONLY during pre-market + regular (04:00–16:00 ET, weekdays, ex-NYSE-holidays) — outside that the underlying doesn’t trade, so it is noise. Metals ~24/5, crypto 24/7 (no gate). Live status: the 🕑 Sessions window in the topbar.' },
      ],
      caveat: 'The 4h confirm cuts trade count but raises quality. Parameters chosen on 2026; OOS validation pending. Live R will be below backtest.',
    },
  },
  dch30_4h6: {
    icon: '⛰️', accent: '#F0B90B',
    tr: {
      title: 'DONCHIAN 30m+4h · 6R', tagline: 'Hibrit, geniş hedef: 1:6 R/R',
      summary: 'dch30_4h hibridiyle birebir AYNI giriş (30m kırılım + 4h yön onayı) ve AYNI −1R stop; tek fark hedef 6R. MFE analizi gösterdi ki kazananlar medyan ~+8R’ye gidiyor, kaybedenler doğruca stop’a (medyan +0R) — yani hedefi genişletmek kayıp tarafını değiştirmiyor, sadece kazananları daha çok yakalıyor.',
      sections: [
        { h: 'Neden 6R', t: 'RR-sweep’te R/işlem hedefle birlikte HER ÜÇ yılda da artıyor (2024/2025/2026); 6R, 4R’nin ~2 katı R/işlem veriyor. Tüm denenen filtreler içinde OOS’ta tutan TEK kaldıraç.' },
        { h: 'Asimetri', t: 'Kaybedenlerin sadece ~%38’i +1R’ye değiyor (medyan +0R) → doğruca stop. 4R TP’lerinin ~%51’i +4R DAHA gidiyor. Geniş hedef bu yapısal asimetriyi paraya çeviriyor.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2; hedef = sabit R/R = 6. Tam-TP. Çözülme hızlı: TP medyan ~1.4 gün, SL medyan ~6 saat.' },
        { h: 'Bedeli', t: 'WR %23 → ~%15. Equity eğrisi daha lumpy, drawdown’lar daha derin ama nadir. Nadir büyük kazanana daha bağımlı.' },
        { h: 'Seans / zaman', t: 'ABD hisse-perp’leri yalnızca pre-market + regular (04:00–16:00 ET, hafta içi, NYSE tatilleri hariç) sinyal üretir; metaller ~24/5, kripto 7/24. Canlı durum: topbar’daki 🕑 Seanslar.' },
      ],
      caveat: '6R, getiriyi artırır ama varyansı da. Daha düz eğri istersen 4R (dch30_4h) tercih et. Canlı R backtest’in altında olur.',
    },
    en: {
      title: 'DONCHIAN 30m+4h · 6R', tagline: 'Hybrid, wider target: 1:6 R/R',
      summary: 'Identical entry to the dch30_4h hybrid (30m breakout + 4h confirm) and the SAME −1R stop; only the target differs (6R). The MFE study found winners run to ~+8R median while losers go straight to stop (median +0R) — so widening the target does not change the loss side, it only captures more of the winners.',
      sections: [
        { h: 'Why 6R', t: 'In the RR-sweep, R/trade rises with the target in ALL THREE years (2024/2025/2026); 6R ~doubles R/trade vs 4R. The only lever that held up out-of-sample among everything tested.' },
        { h: 'Asymmetry', t: 'Only ~38% of losers reach +1R (median +0R) → straight to stop. ~51% of 4R TPs run +4R BEYOND. The wider target monetises this structural asymmetry.' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2; target = fixed R/R = 6. Full-TP. Resolves fast: TP median ~1.4d, SL median ~6h.' },
        { h: 'The cost', t: 'WR 23% → ~15%. Lumpier equity curve, deeper but rarer drawdowns, more dependent on rare big winners.' },
        { h: 'Session / time', t: 'US stock-perps fire only during pre-market + regular (04:00–16:00 ET, weekdays, ex-NYSE-holidays); metals ~24/5, crypto 24/7. Live status: the 🕑 Sessions window in the topbar.' },
      ],
      caveat: '6R lifts returns but also variance. For a smoother curve prefer 4R (dch30_4h). Live R will be below backtest.',
    },
  },
  d30_4h_so: {
    icon: '⛰️', accent: '#2ECC71',
    tr: {
      title: 'DONCHIAN 30m+4h · WR', tagline: 'Yüksek isabet: kademeli çıkış + breakeven runner',
      summary: 'dch30_4h ile birebir AYNI giriş (30m kırılım + 4h yön onayı) ve AYNI −1R stop; fark çıkış modeli. Aynı edge’in DÜŞÜK-R / YÜKSEK-WR ucu: trend kitabı (6R) ~%26 WR / büyük kazananlarken bu ~%78 WR’lik düzgün bir eğri verir. Win rate’i ilk hedef belirler; runner sadece R ekler.',
      sections: [
        { h: 'Kademeli çıkış', t: 'Pozisyonun %60’ı +1R’de kapanır (WR’yi bu belirler). Kalan %40 RUNNER: stop breakeven’a çekilir; runner şunlardan İLK olanında kapanır — +4R cap (= sinyalin kendi TP’si), breakeven (fiyat girişe dönerse 0R), veya 3-günlük zaman-çıkışı (mark-to-market).' },
        { h: 'Runner cap (4R / 3g)', t: '2024-2026 sweep: kapaksız/20g +2776R; runner’ı +4R’de ve 3 günde sınırlamak +2438R (−%12) ama süreyi ≤3 güne, işlem başına R’yi ≤2.2R’ye indirir. WR değişmez (ilk hedef belirler). Alternatifler: cap6/3g +2594R (daha fazla R), cap3/3g +2388R (daha sıkı). Kullanıcı tercihi: 4R/3g denge.' },
        { h: 'Frontier', t: 'WR↔R aynı madalyonun iki yüzü: hedef düştükçe WR artar, R azalır. Sadece hedefi 0.5R’ye düşürmek fee yüzünden negatife döner (%69 WR, −99R). Scale-out, ~%54 WR’yi koruyarak runner ile R’yi geri kazanır.' },
        { h: 'Sonuçlar (OOS)', t: '3 yıl da pozitif (yön-teyitli + 4R/3g cap, tam 1m veriyle çözüldü): 2024 +749.6R (WR %76), 2025 +1068.5R (%79), 2026 +618.2R (%80) — toplam +2436.3R / 4641 işlem. 19 kripto + XAU; her runner penceresi pencere-sonunu aşan 1m veriyle (kenar marklarsız) çözülür.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2 (−1R). İlk hedef +1R’de %60; runner: +4R cap / breakeven / 3g zaman-çıkışı. %0.1 round-trip ücret. Dar hedefte fee orantısal olarak ağır — düşük-R’yi kabul et ama NEGATİF-R’yi değil.' },
      ],
      caveat: 'Backtest-only başladı (canlı sinyaller dch30_4h emit’inden gelir, scale-out olarak çözülür). Crypto+XAU evreni (hisse-perp/XAG dahil değil). Slippage modellenmiyor → canlı R backtest’in altında.',
    },
    en: {
      title: 'DONCHIAN 30m+4h · WR', tagline: 'High win-rate: scale-out + breakeven runner',
      summary: 'Identical entry to dch30_4h (30m breakout + 4h confirm) and the SAME −1R stop; only the exit differs. The LOW-R / HIGH-WR end of the same edge: the trend book (6R) is ~26% WR / big winners, this is a ~78% WR smooth curve. The first target sets the win rate; the runner only adds R.',
      sections: [
        { h: 'Scale-out', t: '60% of the position closes at +1R (this sets the WR). The remaining 40% is the RUNNER: its stop moves to breakeven, then it exits at the FIRST of — a +4R cap (== the signal’s own TP), breakeven (0R, price back to entry), or a 3-day time-exit (mark-to-market).' },
        { h: 'Runner cap (4R / 3d)', t: '2024-2026 sweep: uncapped/20d was +2776R; capping the runner at +4R and 3 days gives +2438R (−12%) but bounds duration to ≤3d and per-trade R to ≤2.2R. WR is unchanged (set by the first target). Alternatives: cap6/3d +2594R (more R), cap3/3d +2388R (tighter). User choice: 4R/3d balance.' },
        { h: 'The frontier', t: 'WR↔R are two sides of one coin: lower the target → higher WR, lower R. Merely cutting the target to 0.5R turns negative after fees (69% WR, −99R). Scale-out keeps ~54% WR while the runner recovers the R.' },
        { h: 'Results (OOS)', t: 'Positive all three years (directional-confirmed + 4R/3d cap, resolved on full 1m data): 2024 +749.6R (76% WR), 2025 +1068.5R (79%), 2026 +618.2R (80%) — total +2436.3R / 4641 trades. 19 crypto + XAU; every runner window is resolved on 1m data that extends past the window end (no data-edge marks).' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2 (−1R). First target 60% at +1R; runner: +4R cap / breakeven / 3-day time exit. 0.1% round-trip fee. Fees bite proportionally hard at tight targets — accept low-R, not NEGATIVE-R.' },
      ],
      caveat: 'Shipped backtest-first (live signals come from the dch30_4h emit, resolved as scale-out). Crypto+XAU universe (no stock-perps/XAG). Slippage not modelled → live R below backtest.',
    },
  },
  d1h_so: {
    icon: '⛰️', accent: '#2ECC71',
    tr: {
      title: 'DONCHIAN 1h · WR', tagline: '1h kırılım + kademeli çıkış (4R/6R/8R) + breakeven runner',
      summary: 'Donchian 1h base sürümüyle (donchian ·0.5R) BİREBİR AYNI giriş — saf 1h Donchian(55) kırılımı, kendi-TF ER≥0.35 kapısı, 4h onayı YOK — ama full-TP yerine yüksek-WR kademeli çıkış modeliyle çözülür. 30m+4h scale-out ailesinin (d30so) 1h kardeşi: aynı mekanik, farklı zaman dilimi. Win-rate’i ilk hedef belirler; runner sadece R ekler.',
      sections: [
        { h: 'Giriş (1h, 4h onayı yok)', t: '1h kapanış 55-bar ekstremini kırar (LONG/SHORT), ER(24)≥0.35 güçlü-trend kapısı. 30m+4h ailesinden farkı: orada 4h yön onayı vardı; burada 1h kendi ER kapısını kullanır (donchian base ile aynı entry). Gerçekçi giriş: +0.5R onay seviyesinden doldurulur (risk = 1.5×ham).' },
        { h: 'Kademeli çıkış', t: 'Pozisyonun %60’ı +1R’de kapanır (WR’yi bu belirler, ~%53). Kalan %40 RUNNER: stop breakeven’a çekilir; runner şunlardan İLK olanında kapanır — +cap R (4/6/8), breakeven (girişe dönüş, 0R), veya 3-günlük zaman-çıkışı (mark-to-market).' },
        { h: 'Cap seçenekleri (4R / 6R / 8R)', t: 'Tek fark runner cap’i — üç sürüm AYNI 1h sinyali + AYNI +0.5R fill’i paylaşır, sadece runner tavanı değişir. Cap büyüdükçe toplam R artar, WR sabit kalır (%53). İsimler kasıtlı olarak açık: d1h_so4c / d1h_so6c / d1h_so8c — 30m+4h ailesinin d30so* etiketleriyle asla karışmaz.' },
        { h: 'Sonuçlar (OOS, +0.5R gerçekçi giriş, 3 yıl)', t: '19 kripto + XAU, tam 1m veriyle çözüldü, WR ~%53. 4R: 2024 −9.2R · 2025 +90.5R · 2026 +43.4R (top +124.4R). 6R: +12.7 / +106.4 / +29.9 (top +149.0R). 8R: +19.5 / +101.4 / +34.3 (top +155.1R). 6R ve 8R üç yılda da pozitif; 4R yalnız 2024’te hafif negatif (30m ailesindeki desenle aynı). Backtest-only.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2 (−1R, ham). İlk hedef +1R’de %60; runner: +cap R / breakeven / 3g zaman-çıkışı. %0.1 round-trip ücret. Aynı edge’in düşük-R/yüksek-WR ucu — 1h full-TP (donchian) ise düşük-WR/büyük-kazanan ucu.' },
      ],
      caveat: 'Backtest-only (canlı scanner yok; istenirse 1h donchian canlı sinyallerinden scale-out olarak çözülebilir). 30m+4h scale-out’a göre daha az ama daha uzun-soluklu sinyal (1h bar). Crypto+XAU evreni. Slippage modellenmiyor → canlı R backtest’in altında olur.',
    },
    en: {
      title: 'DONCHIAN 1h · WR', tagline: '1h breakout + scale-out (4R/6R/8R) + breakeven runner',
      summary: 'Identical entry to the Donchian 1h base (donchian ·0.5R) — plain 1h Donchian(55) breakout, own-TF ER≥0.35 gate, NO 4h confirm — but resolved under the high-WR scale-out exit instead of full-TP. The 1h sibling of the 30m+4h scale-out family (d30so): same mechanic, different timeframe. The first target sets the win rate; the runner only adds R.',
      sections: [
        { h: 'Entry (1h, no 4h confirm)', t: '1h close breaks the 55-bar extreme (LONG/SHORT), ER(24)≥0.35 strong-trend gate. Unlike the 30m+4h family (which adds a 4h-direction confirm), the 1h stream uses its own ER gate (same entry as the donchian base). Realistic entry: filled from the +0.5R confirmation level (risk = 1.5×raw).' },
        { h: 'Scale-out', t: '60% of the position closes at +1R (sets the WR, ~53%). The remaining 40% is the RUNNER: stop moves to breakeven, then it exits at the FIRST of — a +cap R (4/6/8) take-profit, breakeven (0R, back to entry), or a 3-day time-exit (mark-to-market).' },
        { h: 'Cap options (4R / 6R / 8R)', t: 'The only difference is the runner cap — the three versions share the SAME 1h signals + SAME +0.5R fill; only the runner ceiling changes. A higher cap lifts total R while WR stays fixed (53%). Names are deliberately explicit: d1h_so4c / d1h_so6c / d1h_so8c — never colliding with the 30m+4h family’s d30so* tags.' },
        { h: 'Results (OOS, +0.5R realistic entry, 3 years)', t: '19 crypto + XAU, resolved on full 1m data, WR ~53%. 4R: 2024 −9.2R · 2025 +90.5R · 2026 +43.4R (total +124.4R). 6R: +12.7 / +106.4 / +29.9 (total +149.0R). 8R: +19.5 / +101.4 / +34.3 (total +155.1R). 6R and 8R are positive all three years; only 4R dips slightly in 2024 (same pattern as the 30m family). Backtest-only.' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2 (−1R, raw). First target 60% at +1R; runner: +cap R / breakeven / 3-day time exit. 0.1% round-trip fee. The low-R/high-WR end of the same edge — the 1h full-TP (donchian) is its low-WR/big-winner end.' },
      ],
      caveat: 'Backtest-only (no live scanner; could be resolved as scale-out off the 1h donchian live signals if wanted). Fewer but longer-horizon signals than the 30m+4h scale-out (1h bars). Crypto+XAU universe. Slippage not modelled → live R below backtest.',
    },
  },

  // 🌀 ATRX-kapılı OPUS ikizleri (2026-07-12 sembol-durum çalışması) — backtest-only.
  // Tam kart anahtarı = version tag (infoFor'un suffix-türetmesini bilerek kısa devre eder).
  d30so8f3sq: {
    icon: '🌀', accent: '#9B59B6',
    tr: {
      title: 'OPUS · SQZ', tagline: 'OPUS ikizi + günlük oynaklık-SIKIŞMASI kapısı (ATRX<0.8) — yüksek-WR ucu',
      summary: 'OPUS (d30so8f3h7) ile BİREBİR aynı sinyal ve çıkış modeli (30m Donchian kırılım + 4h yön onayı, +0.5R confirm giriş, TP1’de %30 bankla, runner cap 8R, 7 gün, kripto-only evren); tek fark bir SEMBOL-DURUM kapısı: sinyal yalnızca sembolün GÜNLÜK oynaklığı sıkışmışken alınır — ATRX = günlük ATR(5)/ATR(20) < 0.8, bir önceki günün kapanışıyla hesaplanır (bakışsız). Fikir: Donchian kırılımı, oynaklık sıkışmasından ÇIKARKEN çalışır; kırılım geldiğinde patlama daha öndedir.',
      sections: [
        { h: 'Kapı tanımı', t: 'Her sembol için günlük barlardan ATR(5)/ATR(20) oranı (ATRX). Sinyal gününden STRİKT önceki günün değeri kullanılır — gün içi hiçbir bilgi sızmaz. ATRX<0.8 = son 5 günün ortalama gerçek aralığı, 20-günlük ortalamanın %80’inin altında (sıkışma). Geçemeyen sinyal hiç alınmaz; pozisyon zinciri (tek-poz/sembol, reverse) kalan sinyallerle yeniden kurulur.' },
        { h: 'Neden bu kapı (çalışmanın özeti)', t: '2026-07-12 taraması: 101 Binance kripto perp × 2026-H1, canlı-ikiz motorla 3.245 işlem, 39 bakışsız sembol-durum senaryosu (hacim bantları, gün/hafta/ay kaybeden-kazananları, dip/tepe yakınlığı, trend hizası, BTC-görece güç…). Hepsi 2024-25’te gerçek dinamik-evren backtest’iyle OOS doğrulandı. SONUÇ: ATRX ailesi dışındaki HER koşul yıldan yıla işaret değiştirdi (ör. 2026’nın yıldızı “hacim 1.3-2×” OOS’ta WR %47 + negatif R). Sıkışma/genişleme üç yılda da aynı yönde tutan TEK durumdu.' },
        { h: 'Sonuçlar (dinamik-evren, ATRX<0.8)', t: '2024 (18 sym): WR %58.6 · avgR +0.22 · +51.9R (baseline %53.0 · +0.06 · +51.6R). 2025: WR %55.0 · avgR +0.22 · +83.9R (baseline %54.3 · +0.17 · +201.1R). 2026-H1 (101 sym): WR %56.4 · avgR +0.195 · +193.7R (baseline %54.0 · +0.10 · +311.4R). WR ve R/işlem ÜÇ yılda da baseline üstü.' },
        { h: 'Bedeli', t: 'İşlem sayısı ~1/3’e düşer ve iyi yıllarda toplam R’ın bir kısmından vazgeçilir (2025: +84 vs +201). Bu akış WR/verim ucudur: eğri düzgünleşir, işlem başına R 2-4 katına çıkar, ama mutlak R hedefliyorsan kardeşi OPUS·Q5’e bak.' },
        { h: 'Evren & çözüm', t: 'DİNAMİK evren — OPUS’un sabit 18’i değil: kapıyı geçen HER sembol sinyal üretebilir. Çekirdek 18 kripto-perp’in kitabı 2024-01’den; +83 Binance kripto-perp’in kitabı 2026-01’den (paylaşımlı 1m-veri kapsamının başladığı yer). Hisse-perp ve metaller hariç. Aynı 1m-veri çözümü, %0.1 round-trip ücret. Gece backfill’i (atrx_backfill.py, 02:30) kitabı tazeler; canlı emit YOK.' },
      ],
      caveat: 'Backtest-only araştırma varyantı — canlı OPUS’a dokunulmadı. Etki mütevazı ve 2025’te WR marjı ince (+0.7 puan); 39-senaryo taramasından sağ çıkan tek aile olması güven verir ama çoklu-test riski sıfır değildir. Geniş evrenin 83 sembolü yalnız 2026 kitabına katkı verir (öncesinde 1m verisi yok) — çok-yıl kanıt çekirdek 18 + 101-sembol dinamik-evren çalışmasından gelir. Canlıya alma kararı ayrı bir doğrulama ister.',
    },
    en: {
      title: 'OPUS · SQZ', tagline: 'OPUS twin + a daily volatility-SQUEEZE gate (ATRX<0.8) — the high-WR end',
      summary: 'IDENTICAL signals and exit model to OPUS (d30so8f3h7: 30m Donchian breakout + 4h confirm, +0.5R confirm entry, book 30% at TP1, 8R runner cap, 7-day limit, crypto-only universe); the one difference is a SYMBOL-STATE gate: a signal is taken only while the symbol’s DAILY volatility is compressed — ATRX = daily ATR(5)/ATR(20) < 0.8, computed at the previous day’s close (no lookahead). The idea: Donchian breakouts work coming OUT of a squeeze; by the time vol has already expanded, the breakout is late.',
      sections: [
        { h: 'Gate definition', t: 'Per symbol, the daily-bar ATR(5)/ATR(20) ratio (ATRX). The value of the day STRICTLY before the signal’s day is used — nothing intraday leaks. ATRX<0.8 = the last 5 days’ average true range sits below 80% of the 20-day average (a squeeze). A failing signal is never taken; the position chain (one-pos/symbol, reverses) is re-walked on the surviving signals.' },
        { h: 'Why this gate (the study)', t: '2026-07-12 scan: 101 Binance crypto perps × 2026-H1, 3,245 trades on the live-twin engine, 39 lookahead-free symbol-state scenarios (volume bands, daily/weekly/monthly losers & winners, low/high proximity, trend alignment, BTC-relative strength…). All were OOS-validated on 2024-25 as TRUE dynamic-universe re-walks. RESULT: every condition except the ATRX family flipped sign across years (e.g. 2026’s star “volume 1.3-2×” went to 47% WR and negative R OOS). Squeeze/expansion was the ONLY state that held all three years.' },
        { h: 'Results (dynamic universe, ATRX<0.8)', t: '2024 (18 sym): WR 58.6% · avgR +0.22 · +51.9R (baseline 53.0% · +0.06 · +51.6R). 2025: WR 55.0% · avgR +0.22 · +83.9R (baseline 54.3% · +0.17 · +201.1R). 2026-H1 (101 sym): WR 56.4% · avgR +0.195 · +193.7R (baseline 54.0% · +0.10 · +311.4R). WR and R/trade beat baseline in ALL three years.' },
        { h: 'The cost', t: 'Trade count drops to ~1/3 and good years give up part of the total R (2025: +84 vs +201). This stream is the WR/efficiency end: smoother curve, 2-4× R per trade — if you want absolute R, see its sibling OPUS·Q5.' },
        { h: 'Universe & resolution', t: 'DYNAMIC universe — not OPUS’s fixed 18: ANY symbol passing the gate can signal. The core 18 crypto-perps’ book runs from 2024-01; +83 more Binance crypto-perps from 2026-01 (where the shared 1m-data coverage starts). Stock-perps and metals excluded. Same 1m-data resolution, 0.1% round-trip fee. The nightly backfill (atrx_backfill.py, 02:30) refreshes the book; NO live emit.' },
      ],
      caveat: 'Backtest-only research variant — live OPUS is untouched. The effect is modest and the 2025 WR margin thin (+0.7pt); being the sole survivor of a 39-scenario scan is reassuring but multiple-testing risk is not zero. The 83 broad symbols only contribute to the 2026 book (no 1m data earlier) — the multi-year evidence comes from the core 18 + the 101-symbol dynamic-universe study. Going live would need its own validation.',
    },
  },
  d30so8f3q5: {
    icon: '🛡️', accent: '#16A085',
    tr: {
      title: 'OPUS · Q5', tagline: 'OPUS ikizi + genişleme-ATLA kapısı (ATRX≤1.25) — toplam-R’ı koruyan uç',
      summary: 'OPUS (d30so8f3h7) ile BİREBİR aynı sinyal ve çıkış modeli; tek fark: günlük oynaklığı ZATEN patlamış sembollere girilmez — ATRX = günlük ATR(5)/ATR(20) > 1.25 ise sinyal atlanır (önceki gün kapanışıyla, bakışsız). OPUS·SQZ’nin gevşek kardeşi: sıkışma ŞART DEĞİL, sadece en kötü durum kovası (aşırı genişleme, ~Q5) elenir. İşlemlerin ~%85’i kalır; amaç WR patlatmak değil, üç yılda da baseline’ın üstünde toplam R.',
      sections: [
        { h: 'Kapı tanımı', t: 'OPUS·SQZ ile aynı ATRX metriği (günlük ATR5/ATR20, D-1 kapanışı). Fark eşik: <0.8 yerine ≤1.25 — yani yalnız “oynaklık son 5 günde 20-günlük ortalamanın %125’ini aşmış” semboller elenir. Kuintil analizi bu kovanın (Q5) üç yılda da EN KÖTÜ olduğunu gösterdi: avgR 2026 −0.04 / 2024 −0.12 / 2025 en düşük.' },
        { h: 'Neden (çalışmanın özeti)', t: 'Aynı 2026-07-12 taraması (101 sembol × 39 senaryo + 2024-25 dinamik-evren OOS). Genişleme-atla, tarama boyunca toplam R’ı ÜÇ yılda da baseline üstüne çıkaran TEK kural oldu: kırılım sinyali oynaklık patlamasının ARDINDAN geliyorsa ortalamada geç kalmıştır — trend zaten koşmuş, stop geniş, runner’a alan dar.' },
        { h: 'Sonuçlar (dinamik-evren, ATRX≤1.25)', t: '2024 (18 sym): +62.5R vs baseline +51.6R (WR %53.5 vs %53.0). 2025: +212.4R vs +201.1R (WR %55.3 vs %54.3, avgR +0.20 vs +0.17). 2026-H1 (101 sym): +332.4R vs +311.4R (avgR +0.12 vs +0.10). Üç yılda da toplam R baseline üstü; işlem sayısı yalnızca ~%15 azalır.' },
        { h: 'SQZ ile karşılaştırma', t: 'SQZ = WR oyunu (WR %55-59, işlem 1/3, iyi yılda R bırakır). Q5 = totR oyunu (kazanç mütevazı +10..21R/yıl ama yönü hiç şaşırmadı, davranış OPUS’a en yakın). Canlı filtre adayı olarak önce izlenmesi gereken bu uçtur; SQZ ise “yüksek isabet” vitrini.' },
        { h: 'Evren & çözüm', t: 'DİNAMİK evren — OPUS’un sabit 18’i değil: kapıyı geçen HER sembol sinyal üretebilir. Çekirdek 18 kripto-perp’in kitabı 2024-01’den; +83 Binance kripto-perp’in kitabı 2026-01’den (paylaşımlı 1m-veri kapsamının başladığı yer). Hisse-perp ve metaller hariç. Aynı 1m-veri çözümü, %0.1 round-trip ücret. Gece backfill’i (atrx_backfill.py, 02:30) kitabı tazeler; canlı emit YOK.' },
      ],
      caveat: 'Backtest-only araştırma varyantı — canlı OPUS’a dokunulmadı. Kazanç payı küçüktür (yılda ~+10..21R, %5-7); bu bir “çöpü at” sigortasıdır, alfa makinesi değil. Geniş evrenin 83 sembolü yalnız 2026 kitabına katkı verir (öncesinde 1m verisi yok); geniş evrende çöp yeni-listing’ler de bulunur — 2026 çalışmasında en-oynak %20 kovası tam bu popülasyondu. Çoklu-test riski için not: 39 senaryodan üç yıl tutarlı kalan tek aile ATRX idi.',
    },
    en: {
      title: 'OPUS · Q5', tagline: 'OPUS twin + a skip-the-EXPANSION gate (ATRX≤1.25) — the totR-preserving end',
      summary: 'IDENTICAL signals and exit model to OPUS (d30so8f3h7); the one difference: symbols whose daily volatility has ALREADY blown out are skipped — if ATRX = daily ATR(5)/ATR(20) > 1.25 the signal is not taken (previous-day close, no lookahead). The looser sibling of OPUS·SQZ: a squeeze is NOT required, only the worst state bucket (extreme expansion, ~Q5) is removed. ~85% of trades survive; the goal is not a WR spike but total R above baseline in all three years.',
      sections: [
        { h: 'Gate definition', t: 'Same ATRX metric as OPUS·SQZ (daily ATR5/ATR20 at D-1 close). Only the threshold differs: ≤1.25 instead of <0.8 — i.e. only symbols whose 5-day vol exceeds 125% of the 20-day average are skipped. Quintile analysis showed this bucket (Q5) is the WORST in all three years: avgR 2026 −0.04 / 2024 −0.12 / 2025 the lowest.' },
        { h: 'Why (the study)', t: 'Same 2026-07-12 scan (101 symbols × 39 scenarios + 2024-25 dynamic-universe OOS). Skip-the-expansion was the ONLY rule in the whole scan that lifted total R above baseline in ALL three years: a breakout arriving AFTER the vol explosion is on average late — the trend has run, the stop is wide, the runner has little room.' },
        { h: 'Results (dynamic universe, ATRX≤1.25)', t: '2024 (18 sym): +62.5R vs baseline +51.6R (WR 53.5% vs 53.0%). 2025: +212.4R vs +201.1R (WR 55.3% vs 54.3%, avgR +0.20 vs +0.17). 2026-H1 (101 sym): +332.4R vs +311.4R (avgR +0.12 vs +0.10). Total R beats baseline all three years; trade count falls only ~15%.' },
        { h: 'vs SQZ', t: 'SQZ = the WR play (55-59% WR, 1/3 the trades, gives up R in good years). Q5 = the totR play (modest +10..21R/yr gains but the direction never flipped; behaviour closest to OPUS). As a live-filter candidate this end should be watched first; SQZ is the “high hit-rate” showcase.' },
        { h: 'Universe & resolution', t: 'DYNAMIC universe — not OPUS’s fixed 18: ANY symbol passing the gate can signal. The core 18 crypto-perps’ book runs from 2024-01; +83 more Binance crypto-perps from 2026-01 (where the shared 1m-data coverage starts). Stock-perps and metals excluded. Same 1m-data resolution, 0.1% round-trip fee. The nightly backfill (atrx_backfill.py, 02:30) refreshes the book; NO live emit.' },
      ],
      caveat: 'Backtest-only research variant — live OPUS is untouched. The edge is small (~+10..21R/yr, 5-7%); this is a “skip the junk” insurance, not an alpha machine. The 83 broad symbols only contribute to the 2026 book (no 1m data earlier); the broad set includes junk fresh listings — in the 2026 study the most-volatile-quintile bucket was exactly that population. Multiple-testing note: of 39 scenarios, ATRX was the only family consistent across three years.',
    },
  },

  d30so8f3bd: {
    icon: '🎯', accent: '#E67E22',
    tr: {
      title: 'OPUS · BAND', tagline: 'OPUS ikizi + ATRX tatlı-bant kapısı (0.60 ≤ ATRX < 0.80) — günün seçilmiş sembolleri',
      summary: 'OPUS ile BİREBİR aynı sinyal ve çıkış modeli; kapı, SQZ’nin rafine hali: sembolün günlük oynaklığı sıkışmış OLACAK ama AŞIRI ölü olmayacak — 0.60 ≤ günlük ATR(5)/ATR(20) < 0.80 (önceki gün kapanışı, bakışsız). İnce-bant taraması <0.60 diliminin güvenilmez olduğunu gösterdi (2025’te negatif; ölü/likiditesiz sembol popülasyonu); tatlı nokta 0.60-0.80 bandı. Günde medyan ~15 sembol geçer (P25 7 · P75 35) — “bugün hangi semboller aktif” listesinin işlem kitabı budur.',
      sections: [
        { h: 'Kapı tanımı', t: 'SQZ ile aynı ATRX metriği (günlük ATR5/ATR20, D-1 kapanışıyla; gün boyu sabit). Fark: alt sınır — ATRX<0.60 olan aşırı-derin sıkışmalar da elenir. Yani üç dilimden yalnız ortadaki alınır: aşırı-ölü (<0.6) dışarıda, tatlı bant (0.6-0.8) içeride, normal/genişlemiş (≥0.8) dışarıda.' },
        { h: 'Neden bant, neden ilk-N değil', t: '2026-07-12 seçim analizi: “en sıkışık İLK-10” hem 2026’da (avgR +0.10 vs bandın +0.20) hem likidite-bazlı ilk-10 olarak (WR %51.7) bandın altında kaldı — derinlik sıralaması edge’i KIRPIYOR çünkü en derin sıkışma çoğu kez ölü semboldür. Sabit-N dayatmak yerine bandın kendisi filtre; pozisyon kapasitesi endişesi varsa çözüm eşzamanlı-pozisyon sınırıdır, sembol ön-seçimi değil.' },
        { h: 'Sonuçlar (ince-bant, üç yıl)', t: '0.60-0.80 bandı: 2026 (101 sym) WR %55.8 · avgR +0.20 · +158R (n=805) · 2024 (18 sym) WR %61.8 · avgR +0.29 · +52R · 2025 WR %60.2 · avgR +0.38 · +100R. Karşılaştırma — atılan <0.60 dilimi: 2025 WR %44.9 civarı / negatif avgR; ≥0.80 dilimleri baseline’a yakın veya altında.' },
        { h: 'SQZ / Q5 ile ilişki', t: 'BAND ⊂ SQZ (SQZ = <0.8’in tamamı = bant + riskli <0.6 dilimi). SQZ’nin 2026’daki <0.50 işlemleri parlaktı (WR %70) ama 2025’te aynı dilim para kaybetti — BAND bu oynak dilimi tamamen dışarıda bırakan “temiz” versiyondur. Q5 ise ayrı felsefe: yalnız en kötüyü atar, kalan her şeyi işler.' },
        { h: 'Evren & çözüm', t: 'DİNAMİK evren — kapıyı geçen HER sembol: çekirdek 18 kripto-perp (kitap 2024-01’den) + 83 Binance kripto-perp (2026-01’den). Hisse-perp/metal hariç. %0.1 round-trip ücret, 1m çözüm. Gece backfill’i (atrx_backfill.py, 02:30); canlı emit YOK.' },
      ],
      caveat: 'Backtest-only araştırma varyantı. Bant sınırları (0.60/0.80) ince-bant taramasından seçildi — eşik-hassasiyeti riski SQZ/Q5’ten bir kademe yüksektir (iki eşik, tek dönemde kalibre edildi; üç yılda tutması güven verir ama 2026-sonrası izlenmeli). Canlıya alma kararı ayrı doğrulama ister.',
    },
    en: {
      title: 'OPUS · BAND', tagline: 'OPUS twin + the ATRX sweet-band gate (0.60 ≤ ATRX < 0.80) — the day’s selected symbols',
      summary: 'IDENTICAL signals and exit model to OPUS; the gate is SQZ refined: the symbol’s daily vol must be compressed but NOT dead — 0.60 ≤ daily ATR(5)/ATR(20) < 0.80 (previous-day close, no lookahead). The fine-band scan showed the <0.60 slice is unreliable (negative in 2025; a dead/illiquid-symbol population); the sweet spot is the 0.60-0.80 band. A median of ~15 symbols pass per day (P25 7 · P75 35) — this book is the trade record of the daily “which symbols are active” list.',
      sections: [
        { h: 'Gate definition', t: 'Same ATRX metric as SQZ (daily ATR5/ATR20 at D-1 close; fixed for the whole day). The difference: a lower bound — ultra-deep squeezes with ATRX<0.60 are also skipped. Of the three slices, only the middle is taken: ultra-dead (<0.6) out, sweet band (0.6-0.8) in, normal/expanded (≥0.8) out.' },
        { h: 'Why a band, not top-N', t: 'The 2026-07-12 selection study: “the 10 most squeezed” underperformed the band both by depth ranking (2026 avgR +0.10 vs the band’s +0.20) and by liquidity ranking (51.7% WR) — depth ranking CUTS the edge because the deepest squeeze is often a dead symbol. Rather than forcing a fixed N, the band itself is the filter; if position capacity is the concern, cap concurrent positions, not the symbol pre-selection.' },
        { h: 'Results (fine-band, three years)', t: 'The 0.60-0.80 band: 2026 (101 sym) WR 55.8% · avgR +0.20 · +158R (n=805) · 2024 (18 sym) WR 61.8% · avgR +0.29 · +52R · 2025 WR 60.2% · avgR +0.38 · +100R. For contrast — the dropped <0.60 slice: ~45-51% WR / negative avgR in 2025; the ≥0.80 slices sit at or below baseline.' },
        { h: 'Relation to SQZ / Q5', t: 'BAND ⊂ SQZ (SQZ = all of <0.8 = the band + the risky <0.6 slice). SQZ’s <0.50 trades shone in 2026 (70% WR) but the same slice lost money in 2025 — BAND is the “clean” version that leaves that unstable slice out entirely. Q5 is a different philosophy: drop only the worst, trade everything else.' },
        { h: 'Universe & resolution', t: 'DYNAMIC universe — ANY symbol passing the gate: core 18 crypto-perps (book from 2024-01) + 83 more Binance crypto-perps (from 2026-01). Stock-perps/metals excluded. 0.1% round-trip fee, 1m resolution. Nightly backfill (atrx_backfill.py, 02:30); NO live emit.' },
      ],
      caveat: 'Backtest-only research variant. The band edges (0.60/0.80) were picked from the fine-band scan — threshold-sensitivity risk is one notch above SQZ/Q5 (two thresholds, calibrated in one pass; holding across three years is reassuring but watch it beyond 2026). Going live would need separate validation.',
    },
  },

  // 🥇 MIDAS — gold-only intraday VWAP-trend (INDEPENDENT from the Donchian book).
  midas: {
    icon: '🥇', accent: '#D4AF37',
    tr: {
      title: 'MIDAS · ALTIN VWAP-Trend', tagline: 'Sadece XAUUSDT · 1m · trend yönünde VWAP’a geri çekilmeyi al, 3.5×ATR trailing ile koştur',
      summary: 'Donchian/ICT kitabından BAĞIMSIZ, sıfırdan araştırılmış altına-özel intraday strateji. Bir FX enstrümanı olarak altının trendleyen yapısını kullanır: günlük anchored-VWAP eğimiyle belirlenen trend yönünde, fiyat VWAP’a geri çekilince girer; SABİT HEDEF KOYMAZ, 3.5×ATR trailing stop ile gün-içi koşturup seans-sonu kapatır ("anlık aç-kapa", gecelik pozisyon yok). Sadece gerçek FX-altın piyasa saatlerinde işlem açar.',
      sections: [
        { h: 'Giriş (LONG)', t: 'close > VWAP (trend yukarı) + VWAP eğimi 60-bar yukarı + bu bar VWAP’a geri çekilip dokundu (low ≤ VWAP+0.25·ATR) + boğa geri-alış barı (close>open). SHORT simetrik. Karar bar KAPANIŞINDA, giriş bir SONRAKİ bar açılışında (lookahead yok).' },
        { h: 'Çıkış & risk', t: 'Başlangıç stop = 1.5×ATR(15m) (1R). SABİT KÂR HEDEFİ YOK — çıkış = 3.5×ATR trailing stop VEYA 8 saat zaman-stop VEYA seans-sonu zorunlu düz (Cuma 17:00 ET / günlük rollover / hafta sonu). Tek pozisyon. Kazançları bırakır (ort. kazanç +2.25R / kayıp −0.90R).' },
        { h: 'Sonuçlar (2026-H1, piyasa-açık saatler, $0.50/oz maliyet)', t: '528 işlem · +145R · PF 1.48 · WR %37 · maxDD ~−34R. In-Sample (Oca-Nis) +83 / Out-of-Sample (May-Haz) +61. Londra seansı (07-13 UTC) elendi — tek net-negatif seans (hem IS hem OOS), atınca +118R→+145R. Doğrulama: parametre platosu + dürüst IS→OOS + random-null (p<0.005) + seans IS/OOS analizi + bağımsız tekrar-kodlama virgülüne kadar aynı.' },
        { h: 'Evren & saat', t: 'Sadece XAUUSDT (altın). FX-altın saatleri Paz 18:00 ET → Cuma 16:00 ET (hafta sonu için 1 saat erken flat), günlük 17:00-18:00 ET molası + Londra penceresi hariç: 07:00 ≤ UTC < 13:00 (TR saatiyle 10:00 ≤ saat < 16:00) — yani 06:59 UTC kapanışlı bara sinyal gelebilir, 13:00 UTC itibarıyla tekrar açık. Bu pencere yalnız YENİ girişleri engeller; 07:00 öncesi açılmış pozisyon trailing ile koşmaya devam eder. Backtest ve canlı aynı signals() fonksiyonunu kullanır (ayrışma yok). Hafta sonu/kapalıda açık pozisyon kalmaz. 2026.' },
      ],
      caveat: 'MALİYET KRİTİK: bu bir FX modeli ($0.50/oz ≈ ECN spread). Binance taker komisyonunda (~10 bps ≈ $4/oz) tam set NEGATİFE DÖNER. 🔵 2026-07-08’DEN BERİ PAPER: MIDAS-X gerçek-para executor’ı EMEKLİ; yerine daha güçlü TALOS-ICHI-X (Ichimoku Kumo filtreli) mainnet’e geçti. MIDAS artık canlı PAPER sinyal akışı + gece backtest’i — gerçek para YOK. (Geçmiş: 2026-07-07’den 07-08’e MIDAS-X mainnet’te $3 gerçek paraydı.) Çok-yıllı OOS negatif (edge 2026-rejimi olabilir).',
    },
    en: {
      title: 'MIDAS · GOLD VWAP-Trend', tagline: 'XAUUSDT only · 1m · buy the pullback to VWAP in the trend, ride a 3.5×ATR trailing stop',
      summary: 'A gold-specific intraday strategy researched from scratch, INDEPENDENT from the Donchian/ICT book. It exploits gold’s trending character as an FX instrument: in the direction of the anchored-VWAP slope, enter when price pulls back to VWAP; take NO fixed target and ride a 3.5×ATR trailing stop, flat by session close ("instant open/close", no overnight). Trades only during real FX-gold market hours.',
      sections: [
        { h: 'Entry (LONG)', t: 'close > VWAP (uptrend) + VWAP rising over 60 bars + this bar pulled back to VWAP (low ≤ VWAP+0.25·ATR) + bullish reclaim (close>open). SHORT symmetric. Decided at bar CLOSE, filled at the NEXT bar open (no lookahead).' },
        { h: 'Exit & risk', t: 'Initial stop = 1.5×ATR(15m) (1R). NO fixed target — exit = 3.5×ATR trailing stop OR 8h time-stop OR forced session-close flat (Fri 17:00 ET / daily rollover / weekend). One position. Lets winners run (avg win +2.25R / loss −0.90R).' },
        { h: 'Results (2026-H1, market hours, $0.50/oz cost)', t: '528 trades · +145R · PF 1.48 · WR 37% · maxDD ~−34R. In-Sample (Jan-Apr) +83 / Out-of-Sample (May-Jun) +61. The London session (07-13 UTC) is dropped — the only net-negative session in BOTH halves; dropping it lifts +118R→+145R. Validation: parameter plateau + honest IS→OOS + random-null (p<0.005) + per-session IS/OOS + an independent reimplementation reproduced it to the decimal.' },
        { h: 'Universe & hours', t: 'XAUUSDT only. FX-gold hours Sun 18:00 ET → Fri 16:00 ET (flat 1h early for the weekend), excluding the daily 17:00-18:00 ET break + the London window: 07:00 ≤ UTC < 13:00 — i.e. a bar closing 06:59 UTC can still signal; open again from 13:00 UTC. The window blocks NEW entries only; a position opened before 07:00 keeps trailing through it. Backtest and live share the same signals() function (no divergence). No position is held over the weekend / closed market. 2026.' },
      ],
      caveat: 'COST IS CRITICAL: this is an FX model ($0.50/oz ≈ ECN spread). On Binance taker fees (~10 bps ≈ $4/oz) the full set turns NEGATIVE. 🔵 PAPER SINCE 2026-07-08: the MIDAS-X real-money executor is RETIRED; the stronger TALOS-ICHI-X (Ichimoku Kumo filter) took its mainnet place. MIDAS is now a live PAPER signal feed + nightly backtest — NO real money. (History: MIDAS-X traded $3 real money on mainnet from 2026-07-07 to 07-08.) Multi-year OOS is negative (the edge may be 2026-regime).',
    },
  },

  // 🥇 TALOS — gold-only intraday KELTNER-trend (MIDAS'ın iskeletinde VWAP-dışı kardeş akış).
  talos: {
    icon: '🥇', accent: '#B87333',
    tr: {
      title: 'TALOS · ALTIN Keltner-Trend', tagline: 'Sadece XAUUSDT · 1m · trend yönünde 15m Keltner bandına DERİN çekilmeyi al, 3.5×ATR trailing ile koştur',
      summary: '"MIDAS\'tan iyi XAU stratejisi" taramasının (2026-07-07, 30+ aile / ~90 varyant) tek sağlam VWAP-dışı kazananı. MIDAS ile aynı iskelet (1.5×ATR stop, sabit hedef YOK, 3.5×ATR iz-süren stop, 8s, seans-sonu düz, FX-altın saatleri) ama giriş metriği farklı: 15m EMA(20) trendi tanımlar, fiyat EMA−0.75×ATR(20) alt bandına DERİN sarkıp in-trend kapanışla dönünce girer (MIDAS\'ın VWAP dokunuşundan daha derin bir iskonto). Hacim kullanmaz (yalnız EMA/ATR) — rejim dayanıklılığı için ship edildi: PAXG çok-yıllık OOS\'ta MIDAS\'tan belirgin üstün.',
      sections: [
        { h: 'Giriş (LONG)', t: '15m-EMA20 eğimi 4-bar (1s) yukarı + bu 1m bar ALT Keltner bandına sarktı (low ≤ bant+0.25·ATR15) + bandın üstünde boğa kapanış (close>open, close>bant). SHORT üst bantta simetrik. Karar bar KAPANIŞINDA, giriş SONRAKİ bar açılışında (lookahead yok). Londra penceresi atlanır (07:00 ≤ UTC < 13:00 = TR 10:00 ≤ saat < 16:00; yalnız yeni giriş — açık pozisyon koşar) + fx-günü ilk 120dk girilmez (MIDAS filtreleri).' },
        { h: 'Çıkış & risk', t: 'MIDAS ile birebir aynı motor (kod paylaşımlı): başlangıç stop 1.5×ATR(15m) (1R), SABİT HEDEF YOK — 3.5×ATR iz-süren stop VEYA 8 saat VEYA seans-sonu düz. Tek pozisyon, gecelik yok.' },
        { h: 'Sonuçlar (2026-H1, $0.50/oz maliyet)', t: '+87.5R · 314 işlem · PF 1.54 · WR %38 · maxDD −8.3R (MIDAS: +142.6R ama DD −18). IS +55.9 / OOS +31.6. Parametre platosu düz (kmult .625-.875 × trail 3.5-4.0 → +75..+88), random-null P=0.000 (~3σ).' },
        { h: 'Asıl kozu: çok-yıllık dayanıklılık', t: 'PAXG (1oz altın token) vekil OOS: 2024 −168.8 / 2025 +114.5 (PF 1.33) / 2026 +93.5 (PF 1.55) = 3 yıl +39.2R — aynı testte MIDAS-repro −183.0R. 2025\'te MIDAS\'ı ezer, 2024 kaybı yarısı. MIDAS ile günlük R korelasyonu 0.396 → portföy 2026-H1 +230.1R / DD −21.1, her ay yeşil.' },
      ],
      caveat: '2026-07-08\'DEN BERİ ARAŞTIRMA/BACKTEST-ONLY — canlı PAPER emit\'i EMEKLİ; yerine daha güçlü TALOS-ICHI (Ichimoku Kumo yön filtreli) canlıya geçti. Gece backtest\'i (version=talos) tazelenmeye devam eder. Executor\'u hiç olmadı (aynı FX-maliyet modeli; Binance taker\'da MIDAS gibi ölür). 2024 tarzı başarısız-kırılım rejiminde MIDAS ile BİRLİKTE kaybeder.',
    },
    en: {
      title: 'TALOS · GOLD Keltner-Trend', tagline: 'XAUUSDT only · 1m · buy the DEEP pullback to the 15m Keltner band in the trend, ride a 3.5×ATR trailing stop',
      summary: 'The one robust non-VWAP winner of the 2026-07-07 "better than MIDAS" scan (30+ families / ~90 variants). Same skeleton as MIDAS (1.5×ATR stop, NO fixed target, 3.5×ATR trailing, 8h cap, session-close flat, FX-gold hours) but a different entry metric: the 15m EMA(20) defines the trend and entries fire on a DEEP dip to the EMA−0.75×ATR(20) lower band that closes back in-trend — a deeper discount than MIDAS\'s VWAP touch. Volume-free (EMA/ATR only); shipped for its regime robustness: clearly beats MIDAS on multi-year PAXG OOS.',
      sections: [
        { h: 'Entry (LONG)', t: '15m-EMA20 slope up over 4 bars (1h) + this 1m bar dipped to the LOWER Keltner band (low ≤ band+0.25·ATR15) + bullish close back above the band. SHORT symmetric on the upper band. Decided at bar CLOSE, filled next-bar OPEN (no lookahead). London window skipped (07:00 ≤ UTC < 13:00; NEW entries only — an open position keeps trailing) + no entries in the fx-day\'s first 120min (MIDAS filters).' },
        { h: 'Exit & risk', t: 'Identical engine to MIDAS (shared code): initial stop 1.5×ATR(15m) (1R), NO fixed target — 3.5×ATR trailing stop OR 8h OR session-close flat. One position, no overnight.' },
        { h: 'Results (2026-H1, $0.50/oz cost)', t: '+87.5R · 314 trades · PF 1.54 · WR 38% · maxDD −8.3R (MIDAS: +142.6R but DD −18). IS +55.9 / OOS +31.6. Flat parameter plateau (kmult .625-.875 × trail 3.5-4.0 → +75..+88), random-entry null P=0.000 (~3σ).' },
        { h: 'Its real edge: multi-year robustness', t: 'PAXG proxy OOS: 2024 −168.8 / 2025 +114.5 (PF 1.33) / 2026 +93.5 (PF 1.55) = 3yr +39.2R — vs MIDAS-repro −183.0R on the same test. Crushes MIDAS in 2025, half the 2024 loss. Daily-R correlation with MIDAS 0.396 → the portfolio does +230.1R / DD −21.1 in 2026-H1, every month green.' },
      ],
      caveat: 'SINCE 2026-07-08 RESEARCH/BACKTEST-ONLY — its live PAPER emit is retired; the stronger TALOS-ICHI (Ichimoku Kumo direction filter) took its live place. The nightly backtest (version=talos) keeps refreshing. It never had an executor (same FX-cost model; dies on Binance taker like MIDAS). In a 2024-style failed-breakout regime it loses TOGETHER with MIDAS.',
    },
  },

  // 🔬 TALOS-ICHI — TALOS + Ichimoku Kumo-colour direction filter (RESEARCH / PAPER).
  talos_ichi: {
    icon: '🔬', accent: '#5B8DEF',
    tr: {
      title: 'TALOS-ICHI · Keltner + Ichimoku',
      tagline: 'Araştırma/paper · TALOS ne zaman gireceğine karar verir, Ichimoku bulut rengi yön (long/short) onayı verir',
      summary: 'TALOS\'un birebir aynısı (15m Keltner alt/üst bandına derin çekilme, 1.5×ATR stop, sabit hedef YOK, 3.5×ATR iz-süren stop, 8s, seans-sonu düz, FX-altın saatleri) + bir YÖN FİLTRESİ: 15m Ichimoku bulutu (Kumo). LONG yalnız bulut YEŞİL iken (Senkou A > B, yavaş orta-vade trend yukarı), SHORT yalnız bulut KIRMIZI iken alınır. Bu, TALOS\'un daha büyük trende karşı açılan derin-çekilme ("düşen bıçak") girişlerini eler — kötü rejimlerde kanayan popülasyon tam olarak budur. Senkou span\'ları +26 İLERİ kaydırıldığı için bulut ≥26 bar geçmişten türetilir (lookahead yok). ARAŞTIRMA/PAPER akışı — executor YOK.',
      sections: [
        { h: 'Fikir (kullanıcı)', t: 'Ichimoku short/long tercihini yapar, gold-trend (TALOS) ne zaman girileceğine karar verir. Yani zamanlama TALOS\'ta, yön onayı bulutta. MIDAS\'ın kendi VWAP-eğim kapısı zaten sığ girişini hizaladığı için AYNI filtre MIDAS\'ta tutmadı (2025 tersine döndü); TALOS\'un derin girişinde tuttu.' },
        { h: 'Giriş (LONG)', t: 'TALOS koşulları (15m-EMA20 eğim yukarı + alt Keltner bandına derin çekilme + boğa kapanış) VE Ichimoku Kumo YEŞİL (Senkou A > Senkou B). SHORT üst bantta + Kumo KIRMIZI. Karar bar KAPANIŞINDA, giriş SONRAKİ bar açılışında. Londra 07-13 UTC + ilk 120dk seans-olgunluk filtreleri aynen.' },
        { h: 'Çıkış & risk', t: 'MIDAS/TALOS ile birebir aynı motor (kod paylaşımlı): başlangıç stop 1.5×ATR(15m) (1R), SABİT HEDEF YOK — 3.5×ATR iz-süren stop VEYA 8 saat VEYA seans-sonu düz. Tek pozisyon, gecelik yok.' },
        { h: 'Sonuçlar (aynı taze veri, 2026, $0.50/oz)', t: 'TALOS (filtresiz) 325 işlem +85.6R WR%41 PF1.51 → TALOS-ICHI 230 işlem +111.7R WR%43 PF2.00. Filtre 95 işlemi eler, toplam R\'ı ve PF\'i yükseltir.' },
        { h: 'Çok-yıl OOS (PAXG vekil) — asıl gerekçe', t: 'Kumo filtresi avgR/WR/PF\'i HER üç yılda da yükseltti ve en kötü yılın (2024) zararını yarıya indirdi: 2024 −167.7→−61.1R, 2025 +117.2→+89.7R (avgR 0.196→0.293), 2026 +86.1→+89.6R. 3-yıl birleşik +35.6R→+118.3R (elenen kitap −80.0R). MIDAS\'ta aynı filtre 2025\'te tersine döner — bu yüzden yalnız TALOS varyantı.' },
      ],
      caveat: 'ARAŞTIRMA/PAPER akışı — executor YOK, gerçek para YOK. ✅ TAM DOĞRULAMA BATARYASINI GEÇTİ (2026-07-08): (1) Ichimoku periyot platosu düz — tenkan 7-11 / kijun 22-30 / senkou_b 44-60 / shift 26-30 hepsi +84..+96R / PF ~2.0, varsayılan 9/26/52/26 platonun ortasında; (2) random-drop null p=0.004 — Kumo aynı sayıya rastgele düşürmenin (+48±17R) belirgin üstünde (+89.6R), yani seçim becerikli ~2.6σ; (3) 2026 aylık 6/7 ay yeşil; (4) çok-yıl OOS her yıl avgR/WR/PF artar. 🔴 2026-07-08\'DEN BERİ MAINNET GERÇEK PARA (TALOS-ICHI-X, MIDAS-X\'in yerine — kullanıcı kararı): $3/işlem, maker GTX + taker fallback, oto-kaldıraç ≤25x, iz-süren stop borsa-tarafı STOP_MARKET. XAUUSDT\'yi tek executor sahiplenir (MIDAS-X emekli). Canlı PAPER sinyal akışı + gece backtest\'i (version=talos_ichi) otorite kitap olmayı sürdürür. ⚠️ FX-maliyet modeli: çok-yıl taker OOS negatif (2026-rejim riski) — $3 küçük risk, kitabı izle.',
    },
    en: {
      title: 'TALOS-ICHI · Keltner + Ichimoku',
      tagline: 'Research/paper · TALOS decides WHEN to enter, the Ichimoku cloud colour confirms the direction (long/short)',
      summary: 'Identical to TALOS (deep pullback to the 15m Keltner band, 1.5×ATR stop, NO fixed target, 3.5×ATR trailing, 8h cap, session-close flat, FX-gold hours) PLUS a DIRECTION filter: the 15m Ichimoku cloud (Kumo). A LONG is taken only when the cloud is GREEN (Senkou A > B, slow medium-term trend up), a SHORT only when RED. This removes TALOS\'s deep-pullback ("falling-knife") entries that fight the larger trend — exactly the population that bleeds in bad regimes. Senkou spans are shifted +26 FORWARD so the cloud is derived from ≥26 bars in the PAST (no lookahead). RESEARCH/PAPER stream — NO executor.',
      sections: [
        { h: 'The idea', t: 'Ichimoku sets the long/short bias, TALOS (gold trend) decides the timing. The same filter did NOT hold on MIDAS (2025 reversed) because MIDAS\'s VWAP-slope gate already aligns its shallow entry; it held on TALOS\'s deeper entry.' },
        { h: 'Entry (LONG)', t: 'TALOS conditions (15m-EMA20 slope up + deep dip to the lower Keltner band + bullish close) AND Ichimoku Kumo GREEN (Senkou A > Senkou B). SHORT on the upper band + Kumo RED. Decided at bar CLOSE, filled next-bar OPEN. Same London 07-13 UTC + first-120min filters.' },
        { h: 'Exit & risk', t: 'Identical engine to MIDAS/TALOS (shared code): initial stop 1.5×ATR(15m) (1R), NO fixed target — 3.5×ATR trailing OR 8h OR session-close flat. One position, no overnight.' },
        { h: 'Results (same fresh data, 2026, $0.50/oz)', t: 'TALOS (unfiltered) 325 trades +85.6R WR41% PF1.51 → TALOS-ICHI 230 trades +111.7R WR43% PF2.00. The filter drops 95 trades and raises total R and PF.' },
        { h: 'Multi-year OOS (PAXG proxy) — the real rationale', t: 'The Kumo filter improved avgR/WR/PF in ALL three years and halved the worst-year (2024) loss: 2024 −167.7→−61.1R, 2025 +117.2→+89.7R (avgR 0.196→0.293), 2026 +86.1→+89.6R. 3-year combined +35.6R→+118.3R (removed book −80.0R). On MIDAS the same filter reverses in 2025 — hence TALOS-only.' },
      ],
      caveat: 'RESEARCH/PAPER stream — NO executor, NO real money. ✅ PASSED THE FULL VALIDATION BATTERY (2026-07-08): (1) flat Ichimoku period plateau — tenkan 7-11 / kijun 22-30 / senkou_b 44-60 / shift 26-30 all +84..+96R / PF ~2.0, the default 9/26/52/26 sits mid-plateau; (2) random-drop null p=0.004 — Kumo (+89.6R) clearly beats randomly dropping to the same count (+48±17R), a skillful selection at ~2.6σ; (3) 2026 monthly 6/7 months green; (4) multi-year OOS improves avgR/WR/PF every year. 🔴 REAL MONEY ON MAINNET SINCE 2026-07-08 (TALOS-ICHI-X, in MIDAS-X\'s place — user decision): $3/trade, maker GTX + taker fallback, auto-leverage ≤25x, trailing stop rides exchange-side as a STOP_MARKET. One executor owns XAUUSDT (MIDAS-X retired). The live PAPER signal feed + nightly backtest (version=talos_ichi) remain the authoritative book. ⚠️ FX-cost model: multi-year taker OOS is negative (2026-regime risk) — small $3 size, watch the book.',
    },
  },
  // ── Yavaş trend-yönü kapılı ALTIN ikizleri (2026-07-13; backtest-only, executor YOK) ──
  // Köken: "OPUS ve TALOS aynı yönde sinyal verince işlem aç" konfluans sorusu. Sonuç: OPUS'un
  // kattığı şey ZAMANLAMA değil YAVAŞ YÖN'dü ve o yönü 4h Donchian orta-çizgisi daha temiz taşıyor.
  talos_dg: {
    icon: '🧭', accent: '#E8A33D',
    tr: {
      title: 'TALOS·4H · Keltner + 4h trend kapısı',
      tagline: 'Backtest-only · TALOS ne zaman gireceğine karar verir, 4h Donchian orta-çizgisi hangi YÖNE izin verildiğini söyler',
      summary: 'TALOS\'un birebir aynısı (15m Keltner alt/üst bandına derin çekilme, 1.5×ATR stop, sabit hedef YOK, 3.5×ATR iz-süren stop, 8s, seans-sonu düz, FX-altın saatleri, Londra 07-13 UTC atlanır) + tek bir YÖN KAPISI: 4h Donchian(55) ORTA-ÇİZGİSİ. Fiyat orta-çizginin üstündeyse yalnız LONG, altındaysa yalnız SHORT alınır. TALOS derin banda çekilmeyle girer; bu bazen büyük trende karşı "düşen bıçak" yakalamaktır — kapı tam olarak o popülasyonu eler. Kötü rejimde kanamayı kesmenin en ucuz yolu.',
      sections: [
        { h: 'Nereden çıktı (araştırma hikâyesi)', t: 'Soru şuydu: "OPUS ile TALOS altında aynı dönemde aynı yönde sinyal verince işlem açalım." (1) Katı eş-zamanlılık — OPUS\'un XAU\'da pozisyonu AÇIKKEN TALOS tetiklerse — ÖLÜ: 45 işlem, avgR iyileşmesi sıfır. (2) Kapı gevşetilince (OPUS\'un son kırılım yönü, süresiz taşınır) avgR +0.235→+0.409. (3) Ama ablasyon OPUS\'u ELEDİ: aynı işi sade bir 4h Donchian orta-çizgisi daha iyi yapıyor (avgR +0.448), üstelik OPUS\'un ER kapısı/4h confirm/confirm-fill makinesi olmadan. OPUS altında kendi başına zaten gürültü (2026: 42 işlem, +3.6R). Yani ortada "iki strateji konfluansı" YOK; değerli olan tek şey YAVAŞ TREND YÖNÜ.' },
        { h: 'Giriş (LONG)', t: 'TALOS koşulları (15m-EMA20 eğim yukarı + alt Keltner bandına derin çekilme + boğa kapanış) VE 4h kapanış > 4h Donchian(55) orta-çizgisi. SHORT: üst bant + 4h kapanış < orta-çizgi. Karar 1m bar KAPANIŞINDA, dolum SONRAKİ bar açılışında. No-lookahead: 4h barlar label="right"/closed="right" (değer bar kapanınca doğar), orta-çizgi .shift(1) ile cari barı dışlar, 1m\'ye yalnız ffill ile taşınır.' },
        { h: 'Çıkış & risk', t: 'MIDAS/TALOS ile birebir aynı motor (kod paylaşımlı): başlangıç stop 1.5×ATR(15m) = 1R, SABİT HEDEF YOK — 3.5×ATR iz-süren stop VEYA 8 saat VEYA seans-sonu düz. Tek pozisyon, gecelik yok. Maliyet $0.50/oz round-trip (ECN-FX varsayımı).' },
        { h: 'Sonuçlar · XAU 2026 (canlı sembol)', t: 'TALOS (kapısız) 335 işlem +78.9R avgR+0.235 WR%40 PF1.45 maxDD−15.1 → TALOS·4H 238 işlem +106.7R avgR+0.448 WR%42 PF1.90 maxDD−9.6. Kapı 97 işlemi eler, toplam R\'ı %35 artırır, drawdown\'ı %36 azaltır. Aylık 6/7 yeşil.' },
        { h: 'Çok-yıl OOS (PAXG vekil) — asıl gerekçe', t: 'Kapı HER ÜÇ YILDA da avgR\'ı yükseltir: 2024 −174.6→−51.8R (avgR −0.281→−0.132), 2025 +120.7→+125.8R (+0.200→+0.295), 2026 +95.6→+105.0R (+0.303→+0.505). 3-YIL: +41.7R → +178.9R; maxDD −195.0 → −65.6. En yüksek toplam-R veren varyant budur (kardeşi LYNX daha az R ama çok daha az risk üretir).' },
        { h: 'Plato (uydurma-değil testi)', t: 'Kapı ızgarası tf×lookback (PAXG 3-yıl totR, referans kapısız +41.7R): 2h→+76..+143 · 4h→+112..+162 · 8h→+112..+148 · lookback 30/40/55/70/90 hepsi. 15 hücrenin 15\'i baseline\'ı yener, 14\'ü "her üç yılda da avgR artar" ölçütünü geçer. DÜZ ve GENİŞ plato — bıçak sırtı değil. Varsayılan 4h/55 ızgaradan seçilmedi, OPUS\'un kendi parametrelerinden a-priori miras alındı.' },
        { h: 'Null testleri', t: 'A) Dairesel kaydırma (katı: kapsama + yön dengesi + rejim uzunlukları korunur, yalnız hizalama bozulur): PAXG 2024 %98.4 ✅ · 2025 %89.2 ❌ · 2026 %98.4 ✅ · XAU 2026 %92.8 (zayıf). B) Rastgele-düşürme (aynı sayıya rastgele in — Kumo\'nun orijinal ship testi): 4 hücrenin 4\'ü ✅ (%95.4-98.2). Üç yıl BAĞIMSIZ ve üçü de aynı yönde → birleşik z ≈ +3.1 (p ≈ 0.001).' },
      ],
      caveat: 'BACKTEST-ONLY araştırma akışı — executor YOK, canlı emit YOK, gerçek para YOK. ⚠️ 2024 KAPIYLA BİLE ZARARDA (−51.8R): bu bir rejim KALKANI değil, hasar AZALTICI. ⚠️ Maliyet modeli $0.50/oz ECN-FX; Binance taker ücretinde (~$4/oz) bu aile zaten negatif — MIDAS/TALOS ailesinin tamamı için geçerli yapısal kısıt. ⚠️ XAUUSDT vadeli verisi yalnızca 2025-12-11\'den başlar, bu yüzden çok-yıl OOS PAXG vekiliyle yapıldı. ⚠️ 2025 katı null\'ı geçemeyen tek yıl — ama o yıl HER yön filtresi kalıyor (Kumo dahil, %69 ile daha kötü), yani yıla özgü, kapıya özgü değil. SEMANTİK: filtre PRE uygulanır (side maskelenir, walk yeniden koşar) — canlı kodun yaptığı bu; POST (hazır kitaptan eleme) XAU\'da +75.5R verirdi (bkz. LYNX kartındaki not).',
    },
    en: {
      title: 'TALOS·4H · Keltner + 4h trend gate',
      tagline: 'Backtest-only · TALOS decides WHEN to enter, the 4h Donchian midline decides WHICH DIRECTION is allowed',
      summary: 'Identical to TALOS (deep pullback to the 15m Keltner band, 1.5×ATR stop, NO fixed target, 3.5×ATR trailing, 8h cap, session-close flat, FX-gold hours, London 07-13 UTC skipped) PLUS one DIRECTION gate: the 4h Donchian(55) MIDLINE. Above it, only LONGs are taken; below it, only SHORTs. TALOS enters on a deep band pullback, which sometimes means catching a falling knife against the larger trend — the gate removes exactly that population. The cheapest way to stop the bleeding in a bad regime.',
      sections: [
        { h: 'Where it came from', t: 'The question was: "open a trade when OPUS and TALOS signal the same direction on gold." (1) Strict co-occurrence — TALOS firing while OPUS actually holds an XAU position — is DEAD: 45 trades, zero avgR improvement. (2) Relaxing it to a gate (OPUS\'s last breakout direction, carried indefinitely) lifted avgR +0.235→+0.409. (3) But ablation KILLED OPUS: a plain 4h Donchian midline does the job better (avgR +0.448) without OPUS\'s ER gate / 4h confirm / confirm-fill machinery. OPUS on gold is noise standalone (2026: 42 trades, +3.6R). So there is no "two-strategy confluence" — the only valuable thing is SLOW TREND DIRECTION.' },
        { h: 'Entry (LONG)', t: 'TALOS conditions (15m-EMA20 slope up + deep dip to the lower Keltner band + bullish close) AND 4h close > 4h Donchian(55) midline. SHORT: upper band + 4h close < midline. Decided at 1m bar CLOSE, filled next-bar OPEN. No lookahead: 4h bars use label="right"/closed="right" (a value exists only once the bar closes), the midline .shift(1)s out the current bar, and it is carried to 1m by ffill only.' },
        { h: 'Exit & risk', t: 'Identical engine to MIDAS/TALOS (shared code): initial stop 1.5×ATR(15m) = 1R, NO fixed target — 3.5×ATR trailing OR 8h OR session-close flat. One position, no overnight. Cost $0.50/oz round-trip (ECN-FX assumption).' },
        { h: 'Results · XAU 2026 (the live symbol)', t: 'TALOS (ungated) 335 trades +78.9R avgR+0.235 WR40% PF1.45 maxDD−15.1 → TALOS·4H 238 trades +106.7R avgR+0.448 WR42% PF1.90 maxDD−9.6. The gate drops 97 trades, lifts total R by 35% and cuts drawdown by 36%. 6/7 months green.' },
        { h: 'Multi-year OOS (PAXG proxy) — the real rationale', t: 'The gate lifts avgR in ALL THREE years: 2024 −174.6→−51.8R (avgR −0.281→−0.132), 2025 +120.7→+125.8R (+0.200→+0.295), 2026 +95.6→+105.0R (+0.303→+0.505). 3-YEAR: +41.7R → +178.9R; maxDD −195.0 → −65.6. This is the highest-total-R variant (its sibling LYNX earns less R but with far less risk).' },
        { h: 'Plateau (the not-overfit test)', t: 'Gate grid tf×lookback (PAXG 3-year totR, ungated reference +41.7R): 2h→+76..+143 · 4h→+112..+162 · 8h→+112..+148 · lookbacks 30/40/55/70/90. 15 of 15 cells beat the baseline, 14 pass "avgR improves in all three years". A FLAT, WIDE plateau — not a knife edge. The default 4h/55 was not picked from the grid; it was inherited a-priori from OPUS\'s own parameters.' },
        { h: 'Null tests', t: 'A) Circular shift (strict: coverage + long/short balance + regime lengths preserved, only the alignment is broken): PAXG 2024 98.4% ✅ · 2025 89.2% ❌ · 2026 98.4% ✅ · XAU 2026 92.8% (weak). B) Random-drop (drop to the same count at random — Kumo\'s original ship test): 4 of 4 ✅ (95.4-98.2%). The three years are INDEPENDENT and all point the same way → combined z ≈ +3.1 (p ≈ 0.001).' },
      ],
      caveat: 'BACKTEST-ONLY research stream — NO executor, NO live emit, NO real money. ⚠️ 2024 STILL LOSES even with the gate (−51.8R): this is a damage REDUCER, not a regime SHIELD. ⚠️ Cost model is $0.50/oz ECN-FX; on Binance taker fees (~$4/oz) this whole family is negative — a structural constraint for all of MIDAS/TALOS. ⚠️ Binance XAUUSDT futures data only starts 2025-12-11, so the multi-year OOS uses the PAXG proxy. ⚠️ 2025 is the only year that fails the strict null — but EVERY direction filter fails that year (Kumo worse, at 69%), so it is year-specific, not gate-specific. SEMANTICS: the filter is applied PRE (mask the side array, re-run the walk) — that is what the live code does; POST (dropping from the finished book) would give +75.5R on XAU (see the note on the LYNX card).',
    },
  },
  talos_kdg: {
    icon: '🛡️', accent: '#4FB286',
    tr: {
      title: 'TALOS-ICHI·4H · Kumo ∧ 4h kapı',
      tagline: 'Backtest-only · İKİ yavaş yön filtresi birden — Ichimoku bulutu VE 4h Donchian orta-çizgisi aynı yönü göstermeli',
      summary: 'TALOS motoru + İKİ yön kapısının KESİŞİMİ: LONG yalnız (Ichimoku Kumo YEŞİL) VE (4h kapanış > 4h Donchian(55) orta-çizgisi) iken alınır; SHORT yalnız (Kumo KIRMIZI) VE (4h kapanış < orta-çizgi) iken. İkisi anlaşmazsa işlem YOK (fail-closed; bulut henüz oluşmamışsa da işlem yok). Bu, kitabın en yüksek kaliteli ve AÇIK ARA en dayanıklı alt kümesini üretir: en kötü yılın zararını 10 KATA yakın azaltır. Toplam-R şampiyonu değildir (o kardeşi CRUX\'tur) — bu HAYATTA KALMA varyantıdır.',
      sections: [
        { h: 'Neden ikisi birden', t: 'İki filtre bağımsız bilgi taşıyor: Kumo 26-bar gecikmeli yavaş trend rengi, 4h Donchian orta-çizgisi ise fiyatın 4h kanal yapısındaki konumu. XAU 2026\'da ikisi işlemlerin %32\'sinde AYRIŞIYOR — ve ayrıştıkları yerlerin İKİSİ de değersiz (yalnız-Kumo işlemleri avgR +0.106, yalnız-kapı işlemleri +0.091). Paranın TAMAMI ikisinin hemfikir olduğu 163 işlemde: avgR +0.613, PF 2.30. Yani kesişim, gürültüyü ayıklamanın doğal yolu.' },
        { h: 'Giriş (LONG)', t: 'TALOS koşulları (15m-EMA20 eğim yukarı + alt Keltner bandına derin çekilme + boğa kapanış) VE Kumo YEŞİL (Senkou A > B) VE 4h kapanış > 4h Donchian(55) orta-çizgisi. SHORT simetrik. Karar 1m bar kapanışında, dolum sonraki bar açılışında. Her iki kapı da no-lookahead (Senkou span\'lar +26 İLERİ kaydırılır → bulut ≥26 bar geçmişten türer; Donchian orta-çizgi .shift(1) ile cari barı dışlar).' },
        { h: 'Çıkış & risk', t: 'MIDAS/TALOS motoru birebir: stop 1.5×ATR(15m) = 1R, sabit hedef YOK, 3.5×ATR iz-süren stop / 8 saat / seans-sonu düz. Tek pozisyon, gecelik yok. $0.50/oz round-trip.' },
        { h: 'Sonuçlar · XAU 2026 (canlı sembol)', t: 'TALOS 335tr +78.9R avgR+0.235 PF1.45 maxDD−15.1 · KUMO (bugünkü canlı filtre) 238tr +107.8R avgR+0.453 PF1.93 maxDD−12.4 · 4h kapı (CRUX) 238tr +106.7R avgR+0.448 PF1.90 maxDD−9.6 · KUMO∧4h (bu akış) 171tr +105.2R avgR+0.615 WR%45 PF2.30 maxDD−8.8. AYNI parayı %28 daha az işlem ve %29 daha az drawdown ile kazanır. Aylık 6/7 yeşil.' },
        { h: 'Çok-yıl OOS (PAXG vekil) — asıl gerekçe', t: '2024 (kötü yıl): TALOS −174.6R → Kumo −73.9 → 4h kapı −51.8 → KUMO∧4h −17.6R. Zarar 10 KAT azalır. 2025: +120.7 → +76.2R. 2026: +95.6 → +71.3R. 3-YIL: totR +129.9 (TALOS +41.7, Kumo +55.2, 4h kapı +178.9), avgR +0.194 (EN İYİ), PF 1.35 (EN İYİ), maxDD −36.5 (EN İYİ — TALOS −195.0, Kumo −91.6, 4h kapı −65.6). Risk-getiri (3-yıl totR/maxDD): TALOS 0.21 · Kumo 0.60 · 4h kapı 2.73 · KUMO∧4h 3.56.' },
        { h: 'Null testleri — katı null\'ı geçen TEK filtre', t: 'A) Dairesel kaydırma (katı): XAU 2026 %98.0 ✅ · PAXG 2024 %96.6 ✅ · PAXG 2026 %95.6 ✅ · PAXG 2025 %82.4 ❌. 4 hücrenin 3\'ü geçer — Kumo (2/4) ve 4h kapı (2/4) tek başına yapamıyor. B) Rastgele-düşürme: XAU %100.0 ✅ · 2024 %97.6 ✅ · 2026 %97.2 ✅ · 2025 %92.4 (zayıf). Tek zayıf hücre 2025, ama o yıl HER yön filtresi kalıyor (Kumo %69 ile en kötüsü) → yıla özgü.' },
        { h: 'ÖNEMLİ: canlı akışla ilişkisi', t: 'Bugün gerçek parayla koşan TALOS-ICHI-X yalnızca Kumo kullanıyor. Bu araştırma canlı filtreyi DEĞİŞTİRMEK için yeterli DEĞİL: XAUUSDT\'de (gerçek sembol) Kumo ile 4h kapı istatistiksel olarak ayırt edilemez (+107.8R vs +106.7R, net fark −1.1R). Kapının üstünlüğü TAMAMEN PAXG vekilinden geliyor. Bu akış, gerçek parayı riske atmadan canlı Kumo\'nun yanında koşup ayrışmayı ölçmek için var.' },
      ],
      caveat: 'BACKTEST-ONLY araştırma akışı — executor YOK, canlı emit YOK, gerçek para YOK. ⚠️ 2024 hâlâ ZARARDA (−17.6R) — rejim kalkanı değil, hasar azaltıcı (ama ailenin en iyisi). ⚠️ Maliyet $0.50/oz ECN-FX; Binance taker\'da (~$4/oz) aile zaten negatif. ⚠️ XAU vadeli verisi 2025-12-11\'de başlar → çok-yıl OOS PAXG vekiliyle. ⚠️ Filtre kombinasyonu (Kumo ∧ 4h) bir ARAMA sonucudur (denenen: OPUS-BIAS, 4h Donchian, 4h EMA200, ham 30m kırılım, Kumo, ve kesişimler) — plato + 3-yıl OOS + 2 null testi bunu telafi eder ama tek pencerede seçilmiş bir kombinasyon olduğu unutulmamalı. 🔬 SEMANTİK KEŞFİ (2026-07-13): bu motora filtre uygulamanın iki yolu var ve AYNI ŞEY DEĞİLLER. PRE = side dizisini maskele + walk\'ı yeniden koş (CANLI KOD BUNU YAPAR). POST = TALOS\'un hazır kitabından eleme. Motor tek-pozisyonlu olduğu için PRE\'de elenen sinyal motoru BOŞ bırakır ve TALOS\'un hiç girmediği "doğan" işlemler kitaba girer. talos_ichi\'nin ship gerekçesi POST\'u ölçmüştü, canlı PRE koşuyor: PAXG 3-yıl POST +107.2R vs PRE +55.2R (doğan işlemler 227tr / −53.7R / 3 yılın 3\'ünde zarar). XAU\'da işaret TERSİNE dönüyor (doğanlar +18.7R) — bu yüzden canlı P&L\'de acil bir bug YOK, ama TALOS-ICHI\'nin çok-yıl karnesi kayıtlıdan zayıf. Bu iki yeni akış PRE (canlı-sadık) yazılır; kapıda POST/PRE farkı önemsiz (XAU: POST +101.5R vs PRE +105.2R).',
    },
    en: {
      title: 'TALOS-ICHI·4H · Kumo ∧ 4h gate',
      tagline: 'Backtest-only · TWO slow direction filters at once — the Ichimoku cloud AND the 4h Donchian midline must agree',
      summary: 'The TALOS engine plus the INTERSECTION of two direction gates: a LONG is taken only when (Ichimoku Kumo is GREEN) AND (4h close > 4h Donchian(55) midline); a SHORT only when (Kumo RED) AND (4h close < midline). If they disagree, no trade (fail-closed; also no trade while the cloud has not formed). This yields the highest-quality and BY FAR the most durable subset of the book: it cuts the worst year\'s loss by nearly 10x. It is not the total-R champion (that is its sibling CRUX) — this is the SURVIVAL variant.',
      sections: [
        { h: 'Why both', t: 'The two filters carry independent information: Kumo is a 26-bar-lagged slow trend colour, while the 4h Donchian midline is price\'s position in the 4h channel structure. On XAU 2026 they DISAGREE on 32% of trades — and both disagreement buckets are worthless (Kumo-only trades avgR +0.106, gate-only trades +0.091). ALL the money sits in the 163 trades they agree on: avgR +0.613, PF 2.30. The intersection is the natural way to strip the noise.' },
        { h: 'Entry (LONG)', t: 'TALOS conditions (15m-EMA20 slope up + deep dip to the lower Keltner band + bullish close) AND Kumo GREEN (Senkou A > B) AND 4h close > 4h Donchian(55) midline. SHORT is symmetric. Decided at 1m bar close, filled next-bar open. Both gates are no-lookahead (Senkou spans shift +26 FORWARD → the cloud derives from ≥26 bars in the past; the Donchian midline .shift(1)s out the current bar).' },
        { h: 'Exit & risk', t: 'The MIDAS/TALOS engine verbatim: stop 1.5×ATR(15m) = 1R, no fixed target, 3.5×ATR trailing / 8h / session-close flat. One position, no overnight. $0.50/oz round-trip.' },
        { h: 'Results · XAU 2026 (the live symbol)', t: 'TALOS 335tr +78.9R avgR+0.235 PF1.45 maxDD−15.1 · KUMO (today\'s live filter) 238tr +107.8R avgR+0.453 PF1.93 maxDD−12.4 · 4h gate (CRUX) 238tr +106.7R avgR+0.448 PF1.90 maxDD−9.6 · KUMO∧4h (this stream) 171tr +105.2R avgR+0.615 WR45% PF2.30 maxDD−8.8. It earns the SAME money with 28% fewer trades and 29% less drawdown. 6/7 months green.' },
        { h: 'Multi-year OOS (PAXG proxy) — the real rationale', t: '2024 (the bad year): TALOS −174.6R → Kumo −73.9 → 4h gate −51.8 → KUMO∧4h −17.6R. A ~10x smaller loss. 2025: +120.7 → +76.2R. 2026: +95.6 → +71.3R. 3-YEAR: totR +129.9 (TALOS +41.7, Kumo +55.2, 4h gate +178.9), avgR +0.194 (BEST), PF 1.35 (BEST), maxDD −36.5 (BEST — TALOS −195.0, Kumo −91.6, 4h gate −65.6). Risk-adjusted (3-year totR/maxDD): TALOS 0.21 · Kumo 0.60 · 4h gate 2.73 · KUMO∧4h 3.56.' },
        { h: 'Null tests — the ONLY filter that passes the strict null', t: 'A) Circular shift (strict): XAU 2026 98.0% ✅ · PAXG 2024 96.6% ✅ · PAXG 2026 95.6% ✅ · PAXG 2025 82.4% ❌. 3 of 4 cells pass — neither Kumo (2/4) nor the 4h gate (2/4) manages that alone. B) Random-drop: XAU 100.0% ✅ · 2024 97.6% ✅ · 2026 97.2% ✅ · 2025 92.4% (weak). The one weak cell is 2025, but EVERY direction filter fails that year (Kumo worst at 69%) → year-specific.' },
        { h: 'IMPORTANT: relation to the live stream', t: 'TALOS-ICHI-X, which runs real money today, uses Kumo only. This research is NOT sufficient to change the live filter: on XAUUSDT (the real symbol) Kumo and the 4h gate are statistically indistinguishable (+107.8R vs +106.7R, net difference −1.1R). The gate\'s edge comes ENTIRELY from the PAXG proxy. This stream exists to run alongside the live Kumo and measure the divergence without risking real money.' },
      ],
      caveat: 'BACKTEST-ONLY research stream — NO executor, NO live emit, NO real money. ⚠️ 2024 still LOSES (−17.6R) — a damage reducer, not a regime shield (though the best of the family). ⚠️ Cost is $0.50/oz ECN-FX; on Binance taker (~$4/oz) the family is already negative. ⚠️ XAU futures data starts 2025-12-11 → the multi-year OOS uses the PAXG proxy. ⚠️ The filter combination (Kumo ∧ 4h) is the winner of a SEARCH (tried: OPUS-BIAS, 4h Donchian, 4h EMA200, raw 30m breakout, Kumo, and intersections) — the plateau + 3-year OOS + 2 null tests compensate, but remember it was selected on one window. 🔬 SEMANTIC DISCOVERY (2026-07-13): there are two ways to apply a filter to this engine and they are NOT the same. PRE = mask the side array + re-run the walk (WHAT THE LIVE CODE DOES). POST = drop from TALOS\'s finished book. Because the engine is single-position, under PRE a dropped signal leaves it FLAT and "newborn" trades TALOS never took enter the book. talos_ichi\'s ship evidence measured POST while live runs PRE: PAXG 3-year POST +107.2R vs PRE +55.2R (newborn trades 227tr / −53.7R / losing in all 3 years). On XAU the sign REVERSES (newborns +18.7R) — hence no urgent live P&L bug, but TALOS-ICHI\'s multi-year record is weaker than recorded. These two new streams are written PRE (live-faithful); for the gate the POST/PRE difference is immaterial (XAU: POST +101.5R vs PRE +105.2R).',
    },
  },
};

export const infoFor = (strategy, lang) => {
  // Realistic-entry twins ('c' suffix) + scale-out runner-cap variants (d30so6...) derive from the
  // base card + a 0.5R-entry note, so they render everywhere without duplicating full cards.
  // Variant suffixes derive from the same base card: 'm' = margin≥0.25 (d30so8cm),
  // 'f3' = close_frac 0.3 / book 30% at TP1 (d30so8f3).
  const lowFrac = /f3/.test(strategy) && !STRATEGY_INFO[strategy];   // f3 = close_frac 0.3 (may carry an h7 suffix)
  const s0 = lowFrac ? strategy.replace(/f3.*$/, '') : strategy;
  const margin = s0.endsWith('m') && !STRATEGY_INFO[s0];
  const k0 = margin ? s0.slice(0, -1) : s0;
  const realistic = k0.endsWith('c') && !STRATEGY_INFO[k0];
  let key = realistic ? k0.slice(0, -1) : k0;
  if (/^d30so\d+$/.test(key)) key = 'd30_4h_so';     // 6R/… scale-out cap variant -> base scale-out card
  if (/^d1h_?so\d+$/.test(key)) key = 'd1h_so';      // 1h scale-out 4/6/8R cap variant (margin tag has no '_')
  const e = STRATEGY_INFO[key];
  if (!e) return null;
  const base = { icon: e.icon, accent: e.accent, ...(e[lang] || e.tr) };
  if (realistic) {
    base.title = `${base.title} ·0.5R`;
    base.tagline = lang === 'en'
      ? 'Realistic entry from the +0.5R confirmation zone (RR collapses 4→2.33 — the honest edge)'
      : 'Gerçekçi giriş: +0.5R onay bölgesinden (RR 4→2.33 düşer — dürüst edge)';
  }
  if (margin) {
    base.title = `${base.title} ·M0.25`;
    base.tagline = lang === 'en'
      ? 'Breakout must clear the channel by ≥0.25 ATR (OOS-robust false-breakout filter)'
      : 'Kırılım kanalı ≥0.25 ATR aşmalı (OOS-robust sahte-kırılım filtresi)';
  }
  if (lowFrac) {
    const h7 = /h7/.test(strategy);
    base.title = `${base.title} ·b30${h7 ? '·7g' : ''}`;
    base.tagline = lang === 'en'
      ? `Book only 30% at TP1, ride 70% on the runner — lets winners run${h7 ? '; 7-day time-stop (vs 3) gives the runner more room' : ''} (+R OOS, WR held)`
      : `TP1’de yalnızca %30 bankla, %70’i runner’da koştur — kazananları bırakır${h7 ? '; 7 günlük time-stop (3 yerine) runner’a daha çok alan verir' : ''} (+R OOS, WR sabit)`;
  }
  return base;
};
