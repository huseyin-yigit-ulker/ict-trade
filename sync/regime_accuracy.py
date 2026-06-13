"""Predictive-accuracy audit for the 4h Efficiency-Ratio regime classifier.

The TREND/Regime map labels each 4h bar from the TRAILING ER (last N bars):
trend if ER >= 0.25 (the strategies' REGIME_ER_MIN gate), else choppy. That
label is exact for the window it measures — the real question is whether it
PREDICTS the next window:

  - trail ER(i)  uses closes[i-N .. i]           -> the label we act on
  - fwd  ER(i)   uses closes[i   .. i+N]         -> what actually happened next
    (disjoint windows; they share only closes[i], so no overlap tautology)

Metrics per symbol (binary trend/chop at ER_MIN):
  overall  P(fwd class == trail class)            — is the label sticky/right
  trendP   P(fwd trends | labelled trend)         — precision of "trend" calls
  chopP    P(fwd chops  | labelled chop)          — precision of "chop"  calls
  contP    P(same direction next | labelled trend)— does a "trend" keep going
  base     realized trend rate (no-skill majority baseline = max(base,1-base))
  lift     overall - baseline                     — skill above guessing majority

Pure stdlib (urllib) so it runs without numpy/pandas. Mirrors symbolMeta.js /
regime.py: ER_N=10, ER_MIN=0.25, 4h klines.
"""
import json
import time
import urllib.request

N = 10          # trailing & forward window, 4h bars (matches ER_N)
ER_MIN = 0.25   # trend/chop boundary (REGIME_ER_MIN)
LIMIT = 1000    # ~166 days of 4h bars per symbol

SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', '1000PEPEUSDT', 'WIFUSDT', 'SUIUSDT',
    'NEARUSDT', 'FETUSDT', 'ADAUSDT', 'SUSDT', 'ARBUSDT', 'ORDIUSDT', 'ONDOUSDT',
    'XRPUSDT', 'DOGEUSDT', 'LINKUSDT', 'AVAXUSDT', 'XAUUSDT', 'XAGUSDT',
    'NVDAUSDT', 'METAUSDT', 'AMZNUSDT', 'COINUSDT', 'MSTRUSDT', 'CRCLUSDT', 'PLTRUSDT',
    'TSLAUSDT', 'INTCUSDT', 'HOODUSDT', 'MSFTUSDT', 'AVGOUSDT', 'BABAUSDT', 'BXUSDT',
    'HPEUSDT', 'AMATUSDT', 'CRWDUSDT', 'CRDOUSDT', 'AAOIUSDT', 'IWMUSDT',
]
METAL = {'XAUUSDT', 'XAGUSDT'}
STOCK = {
    'NVDAUSDT', 'METAUSDT', 'AMZNUSDT', 'COINUSDT', 'MSTRUSDT', 'CRCLUSDT', 'PLTRUSDT',
    'TSLAUSDT', 'INTCUSDT', 'HOODUSDT', 'MSFTUSDT', 'AVGOUSDT', 'BABAUSDT', 'BXUSDT',
    'HPEUSDT', 'AMATUSDT', 'CRWDUSDT', 'CRDOUSDT', 'AAOIUSDT', 'IWMUSDT',
}


def market(s):
    return 'metal' if s in METAL else 'stock' if s in STOCK else 'crypto'


def er_at(closes, i, n):
    """ER over closes[i-n .. i] (trailing). Caller guarantees i >= n."""
    change = abs(closes[i] - closes[i - n])
    vol = sum(abs(closes[j] - closes[j - 1]) for j in range(i - n + 1, i + 1))
    return (change / vol) if vol > 0 else 0.0


def sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def fetch_closes(sym):
    b = ''.join(c for c in sym if c.isalnum())
    url = f'https://fapi.binance.com/fapi/v1/klines?symbol={b}&interval=4h&limit={LIMIT}'
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.load(r)
    now = time.time() * 1000
    bars = [k for k in d if float(k[6]) <= now]   # completed bars only
    return [float(k[4]) for k in bars]


def audit(closes):
    agree = total = trend_t = trend_hit = chop_t = chop_hit = cont = 0
    realized_trend = 0
    # i needs a trailing window [i-N..i] and a forward window [i..i+N]
    for i in range(N, len(closes) - N):
        trail = er_at(closes, i, N)
        fwd = er_at(closes, i + N, N)            # forward window closes[i..i+N]
        p_tr = trail >= ER_MIN
        r_tr = fwd >= ER_MIN
        total += 1
        realized_trend += 1 if r_tr else 0
        if p_tr == r_tr:
            agree += 1
        if p_tr:
            trend_t += 1
            trend_hit += 1 if r_tr else 0
            if sign(closes[i] - closes[i - N]) == sign(closes[i + N] - closes[i]):
                cont += 1
        else:
            chop_t += 1
            chop_hit += 1 if not r_tr else 0
    if total == 0:
        return None
    base = realized_trend / total
    return {
        'n': total,
        'overall': agree / total,
        'trendP': (trend_hit / trend_t) if trend_t else None,
        'chopP': (chop_hit / chop_t) if chop_t else None,
        'contP': (cont / trend_t) if trend_t else None,
        'base': base,
        'baseline': max(base, 1 - base),
        'trend_share': trend_t / total,
    }


def pct(x):
    return '   —' if x is None else f'{x * 100:4.0f}%'


def main():
    rows = []
    pooled = {'agree': 0, 'total': 0, 'trend_t': 0, 'trend_hit': 0,
              'chop_t': 0, 'chop_hit': 0, 'cont': 0, 'rt': 0}
    for s in SYMBOLS:
        try:
            closes = fetch_closes(s)
        except Exception as e:
            print(f'  ! {s}: fetch failed ({e})')
            continue
        if len(closes) < 2 * N + 5:
            print(f'  ! {s}: too few bars ({len(closes)})')
            continue
        a = audit(closes)
        if not a:
            continue
        a['sym'] = s
        a['market'] = market(s)
        rows.append(a)
        # re-pool from raw counts for an exact micro average
        for i in range(N, len(closes) - N):
            trail = er_at(closes, i, N) >= ER_MIN
            r_tr = er_at(closes, i + N, N) >= ER_MIN
            pooled['total'] += 1
            pooled['rt'] += 1 if r_tr else 0
            if trail == r_tr:
                pooled['agree'] += 1
            if trail:
                pooled['trend_t'] += 1
                pooled['trend_hit'] += 1 if r_tr else 0
                if sign(closes[i] - closes[i - N]) == sign(closes[i + N] - closes[i]):
                    pooled['cont'] += 1
            else:
                pooled['chop_t'] += 1
                pooled['chop_hit'] += 1 if not r_tr else 0

    rows.sort(key=lambda r: r['overall'], reverse=True)
    print('\n=== Per-symbol regime predictive accuracy (4h ER, N=10, trend@>=0.25) ===')
    print(f'{"SYM":<13}{"mkt":<7}{"n":>5}  {"overall":>7} {"trendP":>7} {"chopP":>7} '
          f'{"contP":>7} {"base":>6} {"lift":>6}')
    for r in rows:
        lift = r['overall'] - r['baseline']
        print(f'{r["sym"]:<13}{r["market"]:<7}{r["n"]:>5}  {pct(r["overall"]):>7} '
              f'{pct(r["trendP"]):>7} {pct(r["chopP"]):>7} {pct(r["contP"]):>7} '
              f'{pct(r["base"]):>6} {lift * 100:+5.0f}%')

    # aggregates
    def agg(filt, label):
        sub = [r for r in rows if filt(r)]
        if not sub:
            return
        w = sum(r['n'] for r in sub)
        ov = sum(r['overall'] * r['n'] for r in sub) / w
        bl = sum(r['baseline'] * r['n'] for r in sub) / w
        co = sum((r['contP'] or 0) * r['n'] for r in sub) / w
        print(f'  {label:<10} symbols={len(sub):>2}  overall={ov*100:4.0f}%  '
              f'baseline={bl*100:4.0f}%  lift={(ov-bl)*100:+4.0f}%  contP~{co*100:4.0f}%')

    print('\n=== Aggregates (bar-weighted) ===')
    agg(lambda r: True, 'ALL')
    agg(lambda r: r['market'] == 'crypto', 'crypto')
    agg(lambda r: r['market'] == 'metal', 'metal')
    agg(lambda r: r['market'] == 'stock', 'stock')

    p = pooled
    if p['total']:
        print('\n=== Micro-pooled (every bar, all symbols) ===')
        print(f'  bars={p["total"]}')
        print(f'  overall agreement      {p["agree"]/p["total"]*100:4.1f}%')
        print(f'  trend precision        {p["trend_hit"]/p["trend_t"]*100:4.1f}%  '
              f'(of {p["trend_t"]} trend calls)')
        print(f'  chop  precision        {p["chop_hit"]/p["chop_t"]*100:4.1f}%  '
              f'(of {p["chop_t"]} chop calls)')
        print(f'  trend continuation     {p["cont"]/p["trend_t"]*100:4.1f}%  '
              f'(same direction next window)')
        print(f'  realized trend base    {p["rt"]/p["total"]*100:4.1f}%  '
              f'(majority baseline {max(p["rt"]/p["total"], 1-p["rt"]/p["total"])*100:4.1f}%)')


if __name__ == '__main__':
    main()
