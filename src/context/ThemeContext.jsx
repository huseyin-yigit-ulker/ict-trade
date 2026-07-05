import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { savePrefs } from '../utils/userPrefs';

// Dark (default) / light theme. Applies via <html data-theme="..."> so CSS token
// overrides in [data-theme="light"] swap the whole palette. Persisted to
// localStorage (instant) AND, when logged in, to ict_trade.user_prefs so the
// preference follows the user across devices. setTheme(t, {persist:false}) is
// the server-apply path (AuthContext) — it must not echo the value back to DB.
const LS = 'pusu.theme';

const ThemeContext = createContext();
export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider = ({ children }) => {
  const [theme, setThemeState] = useState(() => {
    try { return localStorage.getItem(LS) || 'dark'; } catch { return 'dark'; }
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem(LS, theme); } catch { /* ignore */ }
  }, [theme]);

  const setTheme = useCallback((t, opts) => {
    setThemeState(t);
    if (opts?.persist !== false) savePrefs({ theme: t });
  }, []);
  const toggle = useCallback(() => setThemeState((t) => {
    const next = t === 'dark' ? 'light' : 'dark';
    savePrefs({ theme: next });
    return next;
  }), []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
};
