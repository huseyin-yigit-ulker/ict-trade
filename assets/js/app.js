// --- KONFİGÜRASYON ---
const CONFIG = {
    DEFAULT_JSON_PATH: './assets/data/trades.json',
    BINANCE_API_URL: 'https://fapi.binance.com/fapi/v1/klines'
};

// --- GLOBAL DEĞİŞKENLER ---
let signals = [];
let chartInstance = null;
let activeSeries = null;

// ----------------------------------------------------
// 1. BAŞLATMA VE OLAY DİNLEYİCİLERİ
// ----------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    // Buton tanımlamaları
    document.getElementById('btn-backtest').addEventListener('click', () => selectMode('BACKTEST'));
    document.getElementById('close-modal').addEventListener('click', closeChart);
    
    // Dosya Yükleme Olayı
    document.getElementById('jsonInput').addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (!file) return;
        
        const reader = new FileReader();
        reader.onload = (event) => startBacktest(JSON.parse(event.target.result));
        reader.readAsText(file);
    });

    // Klavye Kısayolu (ESC ile kapatma)
    document.onkeydown = (evt) => { 
        if (evt.key === "Escape") closeChart(); 
    };
});

function selectMode(mode) {
    if (mode === 'BACKTEST') {
        document.getElementById('spinner').style.display = 'block';
        fetchLocalJson();
    }
}

async function fetchLocalJson() {
    try {
        const timestamp = new Date().getTime();
        // Cache önlemek için timestamp ekliyoruz
        const response = await fetch(`${CONFIG.DEFAULT_JSON_PATH}?t=${timestamp}`);
        if (!response.ok) throw new Error("Otomatik yol başarısız");
        
        const jsonData = await response.json();
        startBacktest(jsonData);
    } catch (err) {
        console.warn("Otomatik okuma başarısız, manuel dosya seçimi açılıyor...", err);
        document.getElementById('spinner').style.display = 'none';
        document.getElementById('path-text').innerText = "Lütfen JSON dosyası seçiniz...";
        document.getElementById('jsonInput').click();
    }
}

// ----------------------------------------------------
// 2. VERİ İŞLEME VE DASHBOARD RENDERING
// ----------------------------------------------------
function startBacktest(rawData) {
    // UI Değişimi
    document.getElementById('mode-selection').style.display = 'none';
    document.getElementById('main-app').style.display = 'block';

    // Veriyi işle
    signals = rawData.map((item, index) => {
        const status = mapStatus(item);
        let exitTime = item.exit_time ? new Date(item.exit_time).getTime() : new Date(item.signal_time).getTime() + (2 * 60 * 60 * 1000);
        
        let exitPrice = item.current_price || item.entry_price;
        if(status === 'TP') exitPrice = parseFloat(item.tp_price);
        if(status === 'SL') exitPrice = parseFloat(item.sl_price);

        return {
            id: index,
            symbol: item.symbol,
            dir: item.trade_type === 'BUY' ? 'LONG' : 'SHORT',
            entry: parseFloat(item.entry_price),
            tp: parseFloat(item.tp_price),
            sl: parseFloat(item.sl_price),
            dateObj: new Date(item.signal_time),
            exitTs: exitTime,
            status: status,
            exitPrice: exitPrice
        };
    });

    // Tarihe göre sırala (Yeniden eskiye)
    signals.sort((a, b) => b.dateObj - a.dateObj);
    
    renderGroupedDashboard();
    
    setTimeout(() => document.getElementById('dashboard').classList.add('visible'), 100);
}

function mapStatus(item) {
    if (item.status === 'TAKE PROFIT') return 'TP';
    if (item.status === 'STOP LOSS') return 'SL';
    return item.status || 'WAITING';
}

// PnL Hesaplama Yardımcısı (Tekrarı önlemek için)
function calculateTradePnL(sig) {
    if (sig.status !== 'TP' && sig.status !== 'SL') return 0;
    
    let pnlPercent = 0;
    if (sig.dir === 'LONG') {
        pnlPercent = ((sig.exitPrice - sig.entry) / sig.entry) * 100;
    } else {
        pnlPercent = ((sig.entry - sig.exitPrice) / sig.entry) * 100;
    }
    return pnlPercent;
}

function renderGroupedDashboard() {
    const container = document.getElementById('dashboard');
    container.innerHTML = '';
    
    // Günlere göre grupla
    const groups = {};
    signals.forEach(sig => {
        const dayKey = sig.dateObj.toLocaleDateString('tr-TR', { 
            year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' 
        });
        if (!groups[dayKey]) groups[dayKey] = [];
        groups[dayKey].push(sig);
    });

    // HTML Oluştur
    Object.keys(groups).forEach(dateKey => {
        const dayTrades = groups[dateKey];
        
        // --- GÜNLÜK İSTATİSTİK HESAPLAMA ---
        let dailyTotalPnL = 0;
        let winCount = 0;
        let lossCount = 0;
        let closedTrades = 0;

        dayTrades.forEach(t => {
            const pnl = calculateTradePnL(t);
            dailyTotalPnL += pnl;
            
            if (t.status === 'TP') { winCount++; closedTrades++; }
            if (t.status === 'SL') { lossCount++; closedTrades++; }
        });

        const winRate = closedTrades > 0 ? (winCount / closedTrades) * 100 : 0;
        const pnlClassHeader = dailyTotalPnL > 0 ? 'sum-win' : (dailyTotalPnL < 0 ? 'sum-loss' : 'sum-neutral');
        // -------------------------------------

        const header = document.createElement('div');
        header.className = 'date-header';
        
        // Header İçeriği: Tarih + İstatistikler
        header.innerHTML = `
            <span>${dateKey}</span>
            <div class="daily-summary">
                <span style="color:#aaa;">${dayTrades.length} İşlem</span>
                <span class="${pnlClassHeader}">Net: ${dailyTotalPnL.toFixed(2)}%</span>
                <span class="${winRate >= 50 ? 'sum-win' : 'sum-loss'}">WR: %${winRate.toFixed(0)}</span>
            </div>
        `;
        container.appendChild(header);

        const groupContainer = document.createElement('div');
        groupContainer.className = 'date-group';
        
        dayTrades.forEach(sig => {
            const item = document.createElement('div');
            item.className = 'trade-item';
            item.onclick = () => openBacktestChart(sig);

            const pnlPercent = calculateTradePnL(sig);
            const pnlClass = pnlPercent > 0 ? 'win' : (pnlPercent < 0 ? 'loss' : 'waiting');
            const statusText = sig.status === 'TP' ? 'WIN' : (sig.status === 'SL' ? 'LOSS' : sig.status);
            const timeStr = sig.dateObj.toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit'});

            item.innerHTML = `
                <div class="trade-info">
                    <span class="symbol-box">${sig.symbol}</span>
                    <span class="dir-badge ${sig.dir.toLowerCase()}">${sig.dir}</span>
                    <span class="time-detail">${timeStr}</span>
                </div>
                <div class="trade-result">
                    <span class="status-text ${pnlClass}">${statusText}</span>
                    <span class="pnl-text ${pnlClass}">${pnlPercent !== 0 ? pnlPercent.toFixed(2) + '%' : '--'}</span>
                </div>
            `;
            groupContainer.appendChild(item);
        });
        container.appendChild(groupContainer);
    });
}

// ----------------------------------------------------
// 3. GRAFİK VE BINANCE API İŞLEMLERİ
// ----------------------------------------------------
async function openBacktestChart(sig) {
    const modal = document.getElementById('modal');
    const container = document.getElementById('chart-container');
    modal.style.display = 'block';
    container.innerHTML = ''; // Önce temizle
    document.getElementById('modal-title').innerText = `${sig.symbol} | ${sig.dir} | ENTRY: ${sig.entry}`;

    // Grafik Ayarları
    chartInstance = LightweightCharts.createChart(container, {
        layout: { backgroundColor: '#131722', textColor: '#d1d4dc' },
        grid: { vertLines: { color: '#242938' }, horzLines: { color: '#242938' } },
        timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2b2b43' },
        rightPriceScale: { borderColor: '#2b2b43' },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });

    activeSeries = chartInstance.addCandlestickSeries({
        upColor: '#089981', downColor: '#F23645',
        borderVisible: false, wickUpColor: '#089981', wickDownColor: '#F23645'
    });

    // Zaman ve Veri Çekme
    const entryTime = sig.dateObj.getTime();
    const exitTime = sig.exitTs; 
    const barIntervalMs = 60 * 1000; // 1 dk
    const bufferBars = 60; // 1 saatlik pay
    const bufferMs = bufferBars * barIntervalMs;

    const fetchStartTime = entryTime - bufferMs;
    const fetchEndTime = exitTime + bufferMs;
    const baseSymbol = sig.symbol.replace('1000','');

    try {
        const url = `${CONFIG.BINANCE_API_URL}?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
        
        const res = await fetch(url);
        if(!res.ok) throw new Error("Binance API Hatası");
        const data = await res.json();

        const candles = data.map(d => ({
            time: d[0] / 1000,
            open: parseFloat(d[1]),
            high: parseFloat(d[2]),
            low: parseFloat(d[3]),
            close: parseFloat(d[4])
        }));

        if(candles.length === 0) { alert("Veri bulunamadı."); return; }
        activeSeries.setData(candles);

        // --- GÖRSELLEŞTİRME (TP/SL KUTULARI) ---
        // TP Bölgesi Boyama
        chartInstance.addBaselineSeries({
            baseValue: { type: 'price', price: sig.entry },
            topFillColor1: sig.dir === 'LONG' ? 'rgba(8, 153, 129, 0.25)' : 'rgba(0,0,0,0)', 
            topLineColor: 'rgba(0,0,0,0)',
            bottomFillColor1: sig.dir === 'SHORT' ? 'rgba(8, 153, 129, 0.25)' : 'rgba(0,0,0,0)',
            bottomLineColor: 'rgba(0,0,0,0)',
            crosshairMarkerVisible: false
        }).setData(
            candles
                .filter(c => (c.time * 1000) >= entryTime && (c.time * 1000) <= exitTime)
                .map(c => ({ time: c.time, value: sig.tp }))
        );

        // SL Bölgesi Boyama
        chartInstance.addBaselineSeries({
            baseValue: { type: 'price', price: sig.entry },
            topFillColor1: sig.dir === 'SHORT' ? 'rgba(242, 54, 69, 0.25)' : 'rgba(0,0,0,0)',
            topLineColor: 'rgba(0,0,0,0)',
            bottomFillColor1: sig.dir === 'LONG' ? 'rgba(242, 54, 69, 0.25)' : 'rgba(0,0,0,0)', 
            bottomLineColor: 'rgba(0,0,0,0)',
            crosshairMarkerVisible: false
        }).setData(
            candles
                .filter(c => (c.time * 1000) >= entryTime && (c.time * 1000) <= exitTime)
                .map(c => ({ time: c.time, value: sig.sl }))
        );

        // Çizgiler ve Markerlar
        activeSeries.createPriceLine({ price: sig.entry, color: '#787b86', lineWidth: 1, lineStyle: 2, title: 'ENTRY' });
        activeSeries.createPriceLine({ price: sig.tp, color: '#089981', lineWidth: 2, title: 'TP' });
        activeSeries.createPriceLine({ price: sig.sl, color: '#F23645', lineWidth: 2, title: 'SL' });

        const entryCandle = candles.find(c => Math.abs(c.time * 1000 - entryTime) < 60000);
        if (entryCandle) {
            activeSeries.setMarkers([{
                time: entryCandle.time,
                position: sig.dir === 'LONG' ? 'belowBar' : 'aboveBar',
                color: '#2962FF',
                shape: sig.dir === 'LONG' ? 'arrowUp' : 'arrowDown',
                text: 'GİRİŞ',
                size: 2
            }]);
        }

        chartInstance.timeScale().fitContent();

    } catch (err) {
        console.error(err);
        alert("Veri çekilemedi. CORS hatası alıyorsan Local Server kullanmalısın.");
    }
}

function closeChart() {
    document.getElementById('modal').style.display = 'none';
    if (chartInstance) { 
        chartInstance.remove(); 
        chartInstance = null; 
    }
}