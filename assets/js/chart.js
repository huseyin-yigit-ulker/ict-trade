let chartInstance = null;

async function openChart(sig) {
    const container = document.getElementById('chart-container');
    document.getElementById('modal').style.display = 'block';
    container.innerHTML = '';

    chartInstance = LightweightCharts.createChart(container, {
        layout: { backgroundColor: '#131722', textColor: '#d1d4dc' },
        grid: { vertLines: { color: '#242938' }, horzLines: { color: '#242938' } },
        timeScale: { timeVisible: true, secondsVisible: false }
    });

    const series = chartInstance.addCandlestickSeries({
        upColor: '#089981', downColor: '#F23645', borderVisible: false
    });

    // Binance Data Fetch
    const buffer = 50 * 60000;
    const baseSymbol = sig.symbol.replace('1000', '');
    try {
        const res = await fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${baseSymbol}&interval=1m&startTime=${sig.dateObj.getTime() - buffer}&endTime=${sig.exitTs + buffer}&limit=1000`);
        const data = await res.json();
        const candles = data.map(d => ({ time: d[0] / 1000, open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4]) }));
        series.setData(candles);

        // TV Style Position Box
        const tpColor = 'rgba(8, 153, 129, 0.2)';
        const slColor = 'rgba(242, 54, 69, 0.2)';

        // 1. Profit Zone
        const tpSeries = chartInstance.addBaselineSeries({
            baseValue: { type: 'price', price: sig.entry_price },
            topFillColor1: sig.dir === 'LONG' ? tpColor : 'transparent',
            bottomFillColor1: sig.dir === 'SHORT' ? tpColor : 'transparent',
            lineVisible: false
        });

        // 2. Loss Zone (Short SL Düzeltmesi Burada)
        const slSeries = chartInstance.addBaselineSeries({
            baseValue: { type: 'price', price: sig.entry_price },
            topFillColor1: sig.dir === 'SHORT' ? slColor : 'transparent', // Shortta üst taraf SL'dir -> Kırmızı
            bottomFillColor1: sig.dir === 'LONG' ? slColor : 'transparent', // Longta alt taraf SL'dir -> Kırmızı
            lineVisible: false
        });

        const zoneDataTP = [], zoneDataSL = [];
        candles.forEach(c => {
            if (c.time * 1000 >= sig.dateObj.getTime() && c.time * 1000 <= sig.exitTs) {
                zoneDataTP.push({ time: c.time, value: sig.tp_price });
                zoneDataSL.push({ time: c.time, value: sig.sl_price });
            }
        });

        tpSeries.setData(zoneDataTP);
        slSeries.setData(zoneDataSL);

        // Lines
        series.createPriceLine({ price: sig.entry_price, color: '#787b86', lineStyle: 2, title: 'ENTRY' });
        series.createPriceLine({ price: sig.tp_price, color: '#089981', title: 'TP' });
        series.createPriceLine({ price: sig.sl_price, color: '#F23645', title: 'SL' });

        chartInstance.timeScale().fitContent();
    } catch (e) { console.error("Data error", e); }
}

function closeChart() {
    document.getElementById('modal').style.display = 'none';
    if (chartInstance) { chartInstance.remove(); chartInstance = null; }
}

document.getElementById('close-modal').addEventListener('click', closeChart);
window.addEventListener('keydown', (e) => { if(e.key === 'Escape') closeChart(); });