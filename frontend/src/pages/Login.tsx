import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { Button, Input } from "../components/ui";
import FluidBackground from "../components/FluidBackground";
import { errDetail } from "../lib/api";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setErr("");
    try {
      await login(username, password);
      nav("/", { replace: true });
    } catch (e2) {
      setErr(errDetail(e2) || "登录失败，请检查用户名或密码");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0f1e] relative overflow-hidden">
      <FluidBackground dark />
      {/* 中心暗角，突出表单 */}
      <div className="absolute inset-0 z-[1] bg-[radial-gradient(ellipse_at_center,transparent_0%,rgba(10,15,30,.5)_100%)] pointer-events-none" />

      <div className="relative z-10 w-full max-w-sm mx-4">
        <div className="reveal flex flex-col items-center gap-3 mb-8">
          <div className="w-12 h-12 rounded-2xl grad-anim flex items-center justify-center shadow-glow-lg">
            <Sparkles size={22} className="text-white" />
          </div>
          <div className="text-center">
            <h1 className="font-display text-2xl font-bold grad-text bg-clip-text text-transparent">智聘云</h1>
            <p className="text-xs text-slate-400 mt-1">AI 智能招聘助手 · 让人才甄选更聪明</p>
          </div>
        </div>

        <form
          onSubmit={submit}
          style={{ animationDelay: ".12s" }}
          className="reveal bg-white/[.06] backdrop-blur-2xl border border-white/10 rounded-2xl p-7 space-y-4 shadow-pop"
        >
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">用户名</label>
            <Input value={username} onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名" autoFocus
              className="!bg-white/[.07] !border-white/10 !text-white placeholder:!text-slate-500 hover:!border-white/20 focus:!ring-brand-500/25 focus:!bg-white/[.09]" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">密码</label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              className="!bg-white/[.07] !border-white/10 !text-white placeholder:!text-slate-500 hover:!border-white/20 focus:!ring-brand-500/25 focus:!bg-white/[.09]" />
          </div>

          {err && <p className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3 py-2 animate-[fadeIn_.2s_ease-out]">{err}</p>}

          <Button type="submit" loading={loading} className="w-full !py-2.5 !rounded-xl">登 录</Button>

          <p className="text-center text-xs text-slate-500 pt-1">
            还没有账号？<Link to="/register" className="text-brand-300 hover:text-brand-200 transition-colors">注册新账号</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
