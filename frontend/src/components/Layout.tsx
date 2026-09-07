import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Users, GitBranch, CalendarClock, FileText,
  Bot, ClipboardCheck, SlidersHorizontal, LogOut, Sparkles, Briefcase,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import FluidBackground from "./FluidBackground";


interface NavItem { to: string; label: string; icon: LucideIcon }

const NAV: NavItem[] = [
  { to: "/",             label: "仪表盘",   icon: LayoutDashboard },
  { to: "/candidates",   label: "候选人",   icon: Users },
  { to: "/pipeline",     label: "招聘管道", icon: GitBranch },
  { to: "/interviews",   label: "面试管理", icon: CalendarClock },
  { to: "/questionnaires", label: "问卷管理", icon: FileText },
  { to: "/policy-agent", label: "智能助手", icon: Bot },
  { to: "/jd-generator", label: "JD 生成", icon: Briefcase },
  { to: "/exam-analysis", label: "试卷分析", icon: ClipboardCheck },
  { to: "/scoring", label: "评分优化", icon: SlidersHorizontal },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const location = useLocation();

  return (
    <div className="relative min-h-screen">
      {/* ===== 流体极光背景（透出玻璃卡片与侧边栏） ===== */}
      <FluidBackground />

      {/* ===== 深色玻璃侧边栏 ===== */}
      <aside className="fixed inset-y-0 left-0 z-40 flex w-60 flex-col bg-slate-950/80 backdrop-blur-2xl border-r border-white/[.08] text-slate-300">
        <div className="flex items-center gap-3 px-5 h-16 border-b border-white/[.06]">
          <div className="w-9 h-9 rounded-xl grad-anim flex items-center justify-center shadow-glow-brand shrink-0">
            <Sparkles size={17} className="text-white" />
          </div>
          <div>
            <p className="text-white font-semibold font-display tracking-wide leading-tight">智聘云</p>
            <p className="text-[11px] text-slate-400 leading-tight">AI 智能招聘助手</p>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-200 ${
                  isActive
                    ? "grad-anim text-white font-medium shadow-glow-brand"
                    : "text-slate-400 hover:bg-white/[.06] hover:text-white hover:translate-x-0.5"
                }`
              }
            >
              <Icon size={16} className="shrink-0 transition-transform duration-200 group-hover:scale-110" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-white/[.06] p-3">
          <div className="flex items-center gap-3 px-2 py-2 rounded-xl hover:bg-white/[.04] transition-colors">
            <div className="w-8 h-8 rounded-full grad-anim flex items-center justify-center text-white text-sm font-semibold shrink-0 shadow-glow-brand">
              {(user?.username ?? "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-white truncate">{user?.username}</p>
              <p className="text-[11px] text-slate-500 uppercase">{user?.role}</p>
            </div>
            <button onClick={() => { logout(); nav("/login"); }} title="退出登录"
              className="text-slate-500 hover:text-rose-400 transition-colors shrink-0">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* ===== 内容区（路由切换时渐入上浮） ===== */}
      <main className="relative z-10 ml-60 min-h-screen">
        <div key={location.pathname} className="page-in mx-auto max-w-7xl px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
