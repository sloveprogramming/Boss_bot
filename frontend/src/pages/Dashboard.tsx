import { useEffect, useState } from "react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  AreaChart, Area, CartesianGrid, PieChart, Pie, Cell, Legend,
} from "recharts";
import { Users, UserPlus, Target, Percent } from "lucide-react";
import { api } from "../lib/api";
import { Card, PageHeader, Spinner, EmptyState } from "../components/ui";
import { STATUS_META, statusMeta, type DashboardStats } from "../types";

const COLORS = ["#6366f1", "#22d3ee", "#8b5cf6", "#f472b6", "#34d399", "#fbbf24", "#38bdf8", "#fb7185"];

const STAT_GRADS = [
  "from-indigo-500 to-blue-500",
  "from-cyan-500 to-sky-500",
  "from-violet-500 to-purple-500",
  "from-emerald-500 to-teal-500",
];

function StatCard({ icon: Icon, label, value, sub, grad, delay }: {
  icon: typeof Users; label: string; value: string | number; sub?: string; grad: string; delay: number;
}) {
  return (
    <Card
      style={{ animationDelay: `${delay}ms` }}
      className="reveal p-5 flex items-start gap-4 hover:shadow-glass-hover hover:-translate-y-1 transition-all duration-300 ease-fluid cursor-default"
    >
      <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${grad} text-white flex items-center justify-center shrink-0 shadow-lg transition-transform duration-300 hover:scale-110 hover:rotate-3`}>
        <Icon size={20} />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-slate-400 font-medium">{label}</p>
        <p className="text-2xl font-semibold font-display text-slate-900 mt-1 tabular-nums">{value}</p>
        {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </Card>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.dashboardStats().then((r) => setStats(r.data)).catch(() => setError("统计数据加载失败"));
  }, []);

  if (error) return <EmptyState text={error} />;
  if (!stats) return <Spinner />;
  if (stats.total_candidates === 0)
    return (<><PageHeader title="仪表盘" desc="招聘全局概览" /><EmptyState text="暂无候选人数据 — 先去「候选人」页创建第一位候选人吧" /></>);

  const distData = Object.entries(stats.status_distribution)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({ name: statusMeta(k).label, key: k, value: v }));

  return (
    <>
      <PageHeader title="仪表盘" desc="招聘全流程数据总览" />

      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard icon={Users} label="候选人总数" value={stats.total_candidates} grad={STAT_GRADS[0]} delay={0} />
        <StatCard icon={UserPlus} label="今日新增" value={stats.today_new} grad={STAT_GRADS[1]} delay={80} />
        <StatCard icon={Target} label="平均匹配分" value={stats.average_match_score} sub="满分 100" grad={STAT_GRADS[2]} delay={160} />
        <StatCard icon={Percent} label="录用率" value={`${stats.hire_rate}%`} sub="已决策候选人中" grad={STAT_GRADS[3]} delay={240} />
      </div>

      <div className="grid grid-cols-5 gap-4 mb-6">
        <Card className="reveal col-span-3 p-5" style={{ animationDelay: "320ms" }}>
          <h3 className="text-sm font-semibold text-slate-700 mb-4">本周新增趋势</h3>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={stats.weekly_trend}>
              <defs>
                <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} tick={{ fontSize: 12, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#94a3b8" }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ borderRadius: 12, borderColor: "#e2e8f0", fontSize: 13, background: "rgba(255,255,255,.92)", backdropFilter: "blur(8px)" }} />
              <Area type="monotone" dataKey="count" name="新增" stroke="#6366f1" strokeWidth={2.5} fill="url(#g)" animationDuration={900} />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card className="reveal col-span-2 p-5" style={{ animationDelay: "400ms" }}>
          <h3 className="text-sm font-semibold text-slate-700 mb-4">状态分布</h3>
          {distData.length === 0 ? (
            <EmptyState text="暂无状态数据" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={distData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={88} paddingAngle={3} animationDuration={900}>
                  {distData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="rgba(255,255,255,.5)" />)}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 13, background: "rgba(255,255,255,.92)", backdropFilter: "blur(8px)" }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <Card className="reveal p-5" style={{ animationDelay: "480ms" }}>
        <h3 className="text-sm font-semibold text-slate-700 mb-4">各阶段人数</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={distData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#94a3b8" }} axisLine={false} tickLine={false} width={28} />
            <Tooltip contentStyle={{ borderRadius: 12, fontSize: 13, background: "rgba(255,255,255,.92)", backdropFilter: "blur(8px)" }} cursor={{ fill: "rgba(99,102,241,.06)" }} />
            <Bar dataKey="value" name="人数" radius={[8, 8, 0, 0]} animationDuration={900}>
              {distData.map((d, i) => (
                <Cell key={i} fill={COLORS[Object.keys(STATUS_META).indexOf(d.key) % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </>
  );
}
