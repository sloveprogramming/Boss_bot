import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, clearAuth, getCachedUser, getToken, setAuth } from "../lib/api";
import type { User } from "../types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (data: { username: string; password: string; role?: string; email?: string }) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(getCachedUser());
  const [loading, setLoading] = useState(!!getToken());

  useEffect(() => {
    if (!getToken()) return;
    api.me()
      .then((r) => { setUser(r.data); localStorage.setItem("recruit_user", JSON.stringify(r.data)); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const { data } = await api.login(username, password);
    const u: User = { id: 0, username: data.username, role: data.role, is_active: true };
    setAuth(data.access_token, u);
    setUser(u);
    try {
      const me = await api.me();
      setUser(me.data);
      localStorage.setItem("recruit_user", JSON.stringify(me.data));
    } catch { /* me 失败不阻塞 */ }
  };

  const register = async (d: { username: string; password: string; role?: string; email?: string }) => {
    await api.register(d);
  };

  const logout = () => { clearAuth(); setUser(null); location.href = "/login"; };

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>;
}
