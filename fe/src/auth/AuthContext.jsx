import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

const LS_KEY = "infaq_auth_v1";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // {id, name, email}
  const [token, setToken] = useState(null); // string JWT / token
  const [loading, setLoading] = useState(true);

  // Load dari localStorage saat app start
  useEffect(() => {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      try {
        const data = JSON.parse(raw);
        if (data?.user && data?.token) {
          setUser(data.user);
          setToken(data.token);
        }
      } catch {}
    }
    setLoading(false);
  }, []);

  // Login: coba real API /auth/login, kalau gagal pakai mock dev
  const login = async (email, password) => {
    // 1) real API (FastAPI kamu) -----------------
    try {
      const r = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (r.ok) {
        const data = await r.json(); // {access_token, user:{...}}
        const auth = { user: data.user, token: data.access_token };
        setUser(auth.user);
        setToken(auth.token);
        localStorage.setItem(LS_KEY, JSON.stringify(auth));
        return { ok: true, mock: false };
      }
    } catch (e) {
      console.warn("Login API error:", e);
    }

    // 2) fallback mock untuk dev cepat -----------
    if (email === "admin@demo.test" && password === "123456") {
      const auth = {
        user: { id: 1, name: "Admin Demo", email },
        token: "dev-token",
      };
      setUser(auth.user);
      setToken(auth.token);
      localStorage.setItem(LS_KEY, JSON.stringify(auth));
      return { ok: true, mock: true };
    }

    return { ok: false, message: "Email atau password salah." };
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem(LS_KEY);
  };

  const value = useMemo(
    () => ({ user, token, loading, login, logout }),
    [user, token, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
