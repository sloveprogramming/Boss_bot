import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Users, GitBranch, CalendarClock, FileText,
  Bot, ClipboardCheck, SlidersHorizontal, LogOut, Sparkles, Briefcase, Pencil,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { errDetail } from "../lib/api";
import { Button, Field, Input, Modal, useToast } from "./ui";
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
  const { user, logout, updateProfile } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const [profileOpen, setProfileOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [nameInput, setNameInput] = useState("");

  // 显示姓名：优先 users.display_name，缺省回退登录名 username
  const displayName = (user?.display_name?.trim() || user?.username || "").trim();

  const openProfile = () => { setNameInput(user?.display_name ?? ""); setProfileOpen(true); };
  const saveProfile = async () => {
    setSaving(true);
    try {
      await updateProfile({ display_name: nameInput.trim() || null });
      setProfileOpen(false);
      toast("显示姓名已更新");
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setSaving(false); }
  };

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
              {(displayName || "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-white truncate">{displayName || "未登录"}</p>
              {user?.display_name ? (
                <p className="text-[11px] text-slate-500 truncate">@{user.username}</p>
              ) : (
                <p className="text-[11px] text-slate-500 uppercase">{user?.role}</p>
              )}
            </div>
            <button onClick={openProfile} title="设置显示姓名"
              className="text-slate-500 hover:text-white transition-colors shrink-0 p-1">
              <Pencil size={14} />
            </button>
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

      {/* 显示姓名编辑弹窗 */}
      <Modal open={profileOpen} onClose={() => setProfileOpen(false)} title="设置显示姓名">
        <Field label="显示姓名">
          <Input value={nameInput} onChange={(e) => setNameInput(e.target.value)}
            placeholder="如：华升" maxLength={100} autoFocus />
        </Field>
        <p className="text-xs text-slate-400 mt-1.5 leading-5">
          此姓名将显示在左下角、候选人「负责人」列与导出的 Excel「负责 HR」列；
          留空则回退显示登录账号 {user?.username ? `@${user.username}` : ""}（登录不受影响）。
        </p>
        <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-slate-100">
          <Button variant="ghost" onClick={() => setProfileOpen(false)}>取消</Button>
          <Button loading={saving} onClick={saveProfile}>保存</Button>
        </div>
      </Modal>
    </div>
  );
}
