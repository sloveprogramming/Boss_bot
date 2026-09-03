import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { Button, Input, Select } from "../components/ui";
import FluidBackground from "../components/FluidBackground";
import { errDetail } from "../lib/api";

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ username: "", password: "", email: "", role: "hr" });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [ok, setOk] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.username.trim().length < 2 || form.password.length < 4) {
      setErr("用户名至少 2 位、密码至少 4 位");
      return;
    }
    setLoading(true); setErr("");
    try {
      await register({ ...form, email: form.email || undefined });
      setOk(true);
      setTimeout(() => nav("/login"), 1200);
    } catch (e2) {
      setErr(errDetail(e2) || "注册失败");
    } finally {
      setLoading(false);
    }
  };
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0f1e] relative overflow-hidden">
      <FluidBackground dark />
      <div className="absolute inset-0 z-[1] bg-[radial-gradient(ellipse_at_center,transparent_0%,rgba(10,15,30,.5)_100%)] pointer-events-none" />

      <div className="relative z-10 w-full max-w-sm mx-4">
        <div className="reveal flex flex-col items-center gap-3 mb-8">
          <div className="w-12 h-12 rounded-2xl grad-anim flex items-center justify-center shadow-glow-lg">
            <Sparkles size={22} className="text-white" />
          </div>
          <div className="text-center">
            <h1 className="font-display text-2xl font-bold grad-text bg-clip-text text-transparent">注册智聘云</h1>
            <p className="text-xs text-slate-400 mt-1">开启 AI 驱动的智能招聘流程</p>
          </div>
        </div>

        <form
          onSubmit={submit}
          style={{ animationDelay: ".12s" }}
          className="reveal bg-white/[.06] backdrop-blur-2xl border border-white/10 rounded-2xl p-7 space-y-4 shadow-pop"
        >
          <Input placeholder="用户名（至少2位）" value={form.username} onChange={set("username")}
            className="!bg-white/[.07] !border-white/10 !text-white placeholder:!text-slate-500 hover:!border-white/20 focus:!ring-brand-500/25" />
          <Input type="password" placeholder="密码（至少4位）" value={form.password} onChange={set("password")}
            className="!bg-white/[.07] !border-white/10 !text-white placeholder:!text-slate-500 hover:!border-white/20 focus:!ring-brand-500/25" />
          <Input placeholder="邮箱（可选）" value={form.email} onChange={set("email")}
            className="!bg-white/[.07] !border-white/10 !text-white placeholder:!text-slate-500 hover:!border-white/20 focus:!ring-brand-500/25" />
          <Select value={form.role} onChange={set("role")}
            className="!bg-white/[.07] !border-white/10 !text-white hover:!border-white/20 focus:!ring-brand-500/25 [&>option]:!bg-slate-900">
            <option value="hr">HR</option>
            <option value="interviewer">面试官</option>
          </Select>

          {err && <p className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3 py-2 animate-[fadeIn_.2s_ease-out]">{err}</p>}
          {ok && <p className="text-sm text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-3 py-2 animate-[fadeIn_.2s_ease-out]">注册成功，正在跳转登录…</p>}

          <Button type="submit" loading={loading} className="w-full !py-2.5 !rounded-xl">注 册</Button>
          <p className="text-center text-xs text-slate-500 pt-1">
            已有账号？<Link to="/login" className="text-brand-300 hover:text-brand-200 transition-colors">直接登录</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
