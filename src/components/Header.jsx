import { useEffect, useMemo, useState } from 'react';
import { useTradeContext } from '../context/TradeContext';

const Header = () => {
  const {
    selectedSymbols,
    pendingSymbols,
    allSignals,
    toggleSymbol,
    applySymbols,
    clearPendingSymbols,
    selectAllPendingSymbols,
    setShowStats,
    setShowSummary,
    dateStart,
    dateEnd,
    pendingDateStart,
    setPendingDateStart,
    pendingDateEnd,
    setPendingDateEnd,
    applyDates,
    mode,
    setMode,
    liveError,
    dbStatus,
    dbMessage
  } = useTradeContext();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dateOpen, setDateOpen] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });

  const uniqueSymbols = [...new Set(allSignals.map(s => s.symbol))].sort();
  const availableDaySet = useMemo(() => {
    const scoped = allSignals.filter((s) => pendingSymbols.has(s.symbol) || selectedSymbols.has(s.symbol));
    return new Set(scoped.map((s) => s.dateObj.toISOString().slice(0, 10)));
  }, [allSignals, pendingSymbols, selectedSymbols]);
  const filteredSymbols = useMemo(() => {
    if (!symbolQuery) return uniqueSymbols;
    const q = symbolQuery.toLowerCase();
    return uniqueSymbols.filter(sym => sym.toLowerCase().includes(q));
  }, [uniqueSymbols, symbolQuery]);
  const monthLabel = calendarMonth.toLocaleDateString('tr-TR', { month: 'long', year: 'numeric' });

  const daysGrid = useMemo(() => {
    const start = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), 1);
    const end = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + 1, 0);
    const startWeekDay = (start.getDay() + 6) % 7; // Mon=0
    const totalDays = end.getDate();
    const cells = [];

    for (let i = 0; i < startWeekDay; i++) {
      cells.push(null);
    }
    for (let d = 1; d <= totalDays; d++) {
      cells.push(new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), d));
    }
    return cells;
  }, [calendarMonth]);

  const isInRange = (day) => {
    if (!day || (!pendingDateStart && !pendingDateEnd)) return false;
    const ts = day.getTime();
    const startTs = pendingDateStart ? new Date(`${pendingDateStart}T00:00:00`).getTime() : -Infinity;
    const endTs = pendingDateEnd ? new Date(`${pendingDateEnd}T23:59:59`).getTime() : Infinity;
    return ts >= startTs && ts <= endTs;
  };

  const isSameDay = (day, value) => {
    if (!day || !value) return false;
    const d = day.toISOString().slice(0, 10);
    return d === value;
  };

  const toIso = (date) => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  };

  const applyQuickRange = (kind) => {
    const now = new Date();
    const todayIso = toIso(now);
    if (kind === 'today') {
      setPendingDateStart(todayIso);
      setPendingDateEnd(todayIso);
      return;
    }
    if (kind === '7d') {
      const start = new Date(now);
      start.setDate(now.getDate() - 6);
      setPendingDateStart(toIso(start));
      setPendingDateEnd(todayIso);
      return;
    }
    if (kind === '30d') {
      const start = new Date(now);
      start.setDate(now.getDate() - 29);
      setPendingDateStart(toIso(start));
      setPendingDateEnd(todayIso);
      return;
    }
    if (kind === 'month') {
      const start = new Date(now.getFullYear(), now.getMonth(), 1);
      const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
      setPendingDateStart(toIso(start));
      setPendingDateEnd(toIso(end));
      return;
    }
    if (kind === 'clear') {
      setPendingDateStart('');
      setPendingDateEnd('');
    }
  };

  useEffect(() => {
    if (!dropdownOpen) setSymbolQuery('');
  }, [dropdownOpen]);

  return (
    <div className="app-header">
      <div className="header-title">
        <div className="brand-mark">ICT NOTEBOOK</div>
        <div className="brand-sub">TradingView Webhook • 1m Journal</div>
      </div>

      <div className="header-controls">
        {mode && (
          <button
            className="header-btn mode-toggle"
            onClick={() => setMode(mode === 'live' ? 'backtest' : 'live')}
          >
            {mode === 'live' ? '📂 Backtest\'e Geç' : '🛰️ Live\'a Geç'}
          </button>
        )}
        <div className="multi-select-container">
          <button
            id="multi-select-btn"
            className="coin-select"
            onClick={() => setDropdownOpen(!dropdownOpen)}
          >
            🪙 Sembol Seçimi ({selectedSymbols.size})
          </button>

          <div className={`multi-select-content ${dropdownOpen ? 'show' : ''}`} id="multi-select-list">
            <input
              className="symbol-search"
              type="text"
              placeholder="Sembol ara..."
              value={symbolQuery}
              onChange={(e) => setSymbolQuery(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
            <div className="symbol-list" onClick={(e) => e.stopPropagation()}>
              {filteredSymbols.length === 0 && (
                <div className="symbol-empty">Sonuç yok</div>
              )}
              {filteredSymbols.map(sym => (
                <label key={sym}>
                  <input
                    type="checkbox"
                    checked={pendingSymbols.has(sym)}
                    onChange={() => toggleSymbol(sym)}
                  />
                  {sym}
                </label>
              ))}
            </div>
            <button
              className="apply-btn"
              onClick={() => {
                applySymbols();
                setDropdownOpen(false);
              }}
            >
              ✅ Uygula
            </button>
            <button
              className="apply-btn"
              onClick={() => {
                selectAllPendingSymbols();
              }}
            >
              ✅ Tümünü Seç
            </button>
            <button
              className="apply-btn ghost"
              onClick={() => {
                clearPendingSymbols();
              }}
            >
              🧹 Temizle
            </button>
          </div>
        </div>

        {mode !== 'live' && (
          <>
            <div className="date-filters">
              <button
                className="date-picker-btn"
                onClick={() => {
                  if (!dateOpen) {
                    setPendingDateStart(dateStart);
                    setPendingDateEnd(dateEnd);
                  }
                  setDateOpen(!dateOpen);
                }}
              >
                📅 {dateStart || dateEnd ? `${dateStart || '...'} → ${dateEnd || '...'}` : 'Tarih Seçimi'}
              </button>
              {dateOpen && (
                <div className="date-popover centered" onClick={(e) => e.stopPropagation()}>
                  <div className="quick-range-row">
                    <button className="quick-range-btn" onClick={() => applyQuickRange('today')}>Bugün</button>
                    <button className="quick-range-btn" onClick={() => applyQuickRange('7d')}>Son 7 Gün</button>
                    <button className="quick-range-btn" onClick={() => applyQuickRange('30d')}>Son 30 Gün</button>
                    <button className="quick-range-btn" onClick={() => applyQuickRange('month')}>Bu Ay</button>
                    <button className="quick-range-btn ghost" onClick={() => applyQuickRange('clear')}>Sıfırla</button>
                  </div>

                  <div className="calendar-header">
                    <button
                      className="cal-nav"
                      onClick={() => setCalendarMonth(new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() - 1, 1))}
                    >
                      ‹
                    </button>
                    <div className="cal-title">{monthLabel}</div>
                    <button
                      className="cal-nav"
                      onClick={() => setCalendarMonth(new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + 1, 1))}
                    >
                      ›
                    </button>
                  </div>
                  <div className="calendar-grid">
                    {['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'].map((d) => (
                      <div key={d} className="cal-day cal-day-label">{d}</div>
                    ))}
                    {daysGrid.map((day, idx) => {
                      if (!day) return <div key={`empty-${idx}`} className="cal-day empty"></div>;
                      const iso = day.toISOString().slice(0, 10);
                      const inRange = isInRange(day);
                      const isStart = isSameDay(day, pendingDateStart);
                      const isEnd = isSameDay(day, pendingDateEnd);
                      const hasTrades = availableDaySet.has(iso);
                      return (
                        <button
                          key={iso}
                          className={`cal-day ${inRange ? 'in-range' : ''} ${isStart ? 'start' : ''} ${isEnd ? 'end' : ''} ${hasTrades ? 'has-trades' : ''}`}
                          onClick={() => {
                            if (!pendingDateStart || (pendingDateStart && pendingDateEnd)) {
                              setPendingDateStart(iso);
                              setPendingDateEnd('');
                            } else {
                              if (new Date(iso) < new Date(pendingDateStart)) {
                                setPendingDateEnd(pendingDateStart);
                                setPendingDateStart(iso);
                              } else {
                                setPendingDateEnd(iso);
                              }
                            }
                          }}
                        >
                          {day.getDate()}
                        </button>
                      );
                    })}
                  </div>
                  <div className="range-preview">
                    {pendingDateStart || pendingDateEnd
                      ? `${pendingDateStart || '...'} → ${pendingDateEnd || '...'}`
                      : 'Aralık seçilmedi'}
                  </div>
                  <div className="date-actions">
                    <button
                      className="apply-btn"
                      onClick={() => {
                        applyDates();
                        setDateOpen(false);
                      }}
                    >
                      ✅ Uygula
                    </button>
                    <button
                      className="apply-btn ghost"
                      onClick={() => {
                        setPendingDateStart('');
                        setPendingDateEnd('');
                        setDateStart('');
                        setDateEnd('');
                        setDateOpen(false);
                      }}
                    >
                      🧹 Temizle
                    </button>
                  </div>
                </div>
              )}
            </div>

            <button id="btn-summary" className="header-btn" onClick={() => setShowSummary(true)}>📈 Başarı Geçmişi</button>
          </>
        )}
      </div>

      <div className="status-badge">
        Mod: {mode === 'live' ? 'Live' : mode === 'backtest' ? 'Backtest' : 'Seçilmedi'}
        {liveError && <span className="status-error"> • {liveError}</span>}
        {dbMessage && <span className={`db-pill ${dbStatus}`}> • {dbMessage}</span>}
      </div>

      {(dropdownOpen || dateOpen) && (
        <div
          className="header-overlay"
          onClick={() => {
            setDropdownOpen(false);
            setDateOpen(false);
          }}
        ></div>
      )}
    </div>
  );
};

export default Header;
