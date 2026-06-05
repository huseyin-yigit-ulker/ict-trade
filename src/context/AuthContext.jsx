import { createContext, useContext, useState, useCallback } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

// Soft client-side gate (static frontend — NOT real security; the credential
// ships in the bundle). Configure via .env: VITE_LOGIN_USER / VITE_LOGIN_PASS.
const LS = 'pusu.auth';
const USER = import.meta.env.VITE_LOGIN_USER || 'pusu';
const PASS = import.meta.env.VITE_LOGIN_PASS || 'pusu2026';

const AuthContext = createContext();
export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem(LS) || 'null'); } catch { return null; }
  });

  const login = useCallback((username, password) => {
    if (username === USER && password === PASS) {
      const u = { name: username, at: Date.now() };
      try { localStorage.setItem(LS, JSON.stringify(u)); } catch { /* ignore */ }
      setUser(u);
      return true;
    }
    return false;
  }, []);

  const logout = useCallback(() => {
    try { localStorage.removeItem(LS); } catch { /* ignore */ }
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isAuthed: !!user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

// Route guard: unauthenticated visitors are bounced to /login (remembering origin).
export const RequireAuth = ({ children }) => {
  const { isAuthed } = useAuth();
  const loc = useLocation();
  if (!isAuthed) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return children;
};
