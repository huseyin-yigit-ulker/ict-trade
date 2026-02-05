const JSON_FILE_PATH = './data/btcusdt.json';
let signals = [];

document.getElementById('btn-backtest').addEventListener('click', () => {
    document.getElementById('spinner').style.display = 'block';
    fetchData();
});

async function fetchData() {
    try {
        const response = await fetch(`${JSON_FILE_PATH}?t=${Date.now()}`);
        if (!response.ok) throw new Error("JSON bulunamadı");
        const data = await response.json();
        processSignals(data);
    } catch (err) {
        document.getElementById('spinner').style.display = 'none';
        document.getElementById('jsonInput').click();
    }
}

document.getElementById('jsonInput').addEventListener('change', (e) => {
    const reader = new FileReader();
    reader.onload = (event) => processSignals(JSON.parse(event.target.result));
    reader.readAsText(e.target.files[0]);
});

function processSignals(rawData) {
    document.getElementById('mode-selection').style.display = 'none';
    document.getElementById('main-app').style.display = 'block';

    signals = rawData.map((item, index) => {
        const status = item.status === 'TAKE PROFIT' ? 'TP' : (item.status === 'STOP LOSS' ? 'SL' : 'WAITING');
        const exitTime = item.exit_time ? new Date(item.exit_time).getTime() : new Date(item.signal_time).getTime() + (2 * 3600000);
        return {
            ...item,
            id: index,
            dir: item.trade_type === 'BUY' ? 'LONG' : 'SHORT',
            dateObj: new Date(item.signal_time),
            exitTs: exitTime,
            status: status
        };
    }).sort((a, b) => b.dateObj - a.dateObj);

    renderDashboard();
}

function renderDashboard() {
    const container = document.getElementById('dashboard');
    container.innerHTML = '';
    const groups = {};

    signals.forEach(sig => {
        const day = sig.dateObj.toLocaleDateString('tr-TR', { year:'numeric', month:'long', day:'numeric' });
        if (!groups[day]) groups[day] = [];
        groups[day].push(sig);
    });

    Object.keys(groups).forEach(day => {
        container.innerHTML += `<div class="date-header">${day}</div>`;
        const groupDiv = document.createElement('div');
        groups[day].forEach(sig => {
            const pnl = sig.status === 'WAITING' ? 0 : (sig.dir === 'LONG' ? (sig.tp_price - sig.entry_price) : (sig.entry_price - sig.tp_price));
            const pnlClass = sig.status === 'TP' ? 'win' : (sig.status === 'SL' ? 'loss' : '');
            
            const item = document.createElement('div');
            item.className = 'trade-item';
            item.innerHTML = `
                <div class="trade-info">
                    <span class="symbol-box">${sig.symbol}</span>
                    <span class="dir-badge ${sig.dir.toLowerCase()}">${sig.dir}</span>
                </div>
                <div class="trade-result">
                    <span class="status-text ${pnlClass}">${sig.status}</span>
                </div>
            `;
            item.onclick = () => openChart(sig);
            groupDiv.appendChild(item);
        });
        container.appendChild(groupDiv);
    });
    document.getElementById('dashboard').classList.add('visible');
}