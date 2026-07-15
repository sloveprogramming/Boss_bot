import { useEffect, useState } from 'react'
import { Users, TrendingUp, Star, UserCheck, Sparkles, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import { dashboardApi, workflowApi } from '../lib/api'

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null)
  const [pipeline, setPipeline] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      dashboardApi.stats(),
      workflowApi.pipeline(),
    ]).then(([s, p]) => {
      setStats(s)
      setPipeline(p)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3">
          <div className="relative">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 animate-pulse" />
            <Sparkles className="w-5 h-5 text-white absolute inset-0 m-auto animate-spin" />
          </div>
          <p className="text-gray-400 text-sm">加载仪表盘中...</p>
        </div>
      </div>
    )
  }

  const cards = [
    {
      label: '候选人总数', value: stats?.total_candidates ?? 0,
      icon: Users, trend: '+12%', trendUp: true,
      gradient: 'from-blue-500 to-cyan-500', bg: 'from-blue-50 to-cyan-50',
    },
    {
      label: '今日新增', value: stats?.today_new ?? 0,
      icon: TrendingUp, trend: '今日', trendUp: true,
      gradient: 'from-emerald-500 to-teal-500', bg: 'from-emerald-50 to-teal-50',
    },
    {
      label: '平均匹配分', value: `${stats?.average_match_score ?? 0}`,
      icon: Star, suffix: '分', trend: null as string | null,
      gradient: 'from-violet-500 to-purple-500', bg: 'from-violet-50 to-purple-50',
    },
    {
      label: '录取率', value: `${stats?.hire_rate ?? 0}`,
      icon: UserCheck, suffix: '%', trend: null as string | null,
      gradient: 'from-amber-500 to-orange-500', bg: 'from-amber-50 to-orange-50',
    },
  ]

  const statusLabels: Record<string, string> = {
    new: '新候选人', analyzed: '已分析', talent_pool: '人才池',
    q_sent: '问卷已发', q_done: '问卷完成', scheduled: '已排期',
    interviewed: '已面试', hired: '已录用', rejected: '已拒绝',
    archived: '已归档',
  }

  return (
    <div className="space-y-8">
      {/* 欢迎横幅 */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-500 p-8 text-white">
        <div className="absolute inset-0 bg-white/10 backdrop-blur-3xl" />
        <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full -translate-y-1/2 translate-x-1/4" />
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-white/5 rounded-full translate-y-1/2 -translate-x-1/4" />
        <div className="relative z-10 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-5 h-5 text-amber-300" />
              <span className="text-sm font-medium text-white/80">AI 驱动的智能招聘系统</span>
            </div>
            <h2 className="text-2xl font-bold mb-1">欢迎使用 AI 招聘助手</h2>
            <p className="text-white/70 text-sm max-w-lg">
              无需手动筛选，AI 自动完成简历解析、匹配度评分、面试排期 — 让招聘效率提升 10 倍
            </p>
          </div>
          <div className="hidden lg:block">
            <div className="flex gap-3">
              {['解析', '评分', '分流', '排期', '录用'].map((step, i) => (
                <div key={step} className="flex items-center gap-1.5">
                  <div className="w-8 h-8 rounded-lg bg-white/20 backdrop-blur flex items-center justify-center text-xs font-bold">
                    {i + 1}
                  </div>
                  {i < 4 && <div className="w-4 h-px bg-white/30" />}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map(card => (
          <div key={card.label} className="glass-card p-5 group cursor-default">
            <div className="flex items-start justify-between mb-4">
              <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${card.bg} flex items-center justify-center`}>
                <card.icon className={`w-5 h-5 bg-gradient-to-br ${card.gradient} bg-clip-text text-transparent`} />
              </div>
              {card.trend && (
                <div className={`flex items-center gap-0.5 text-xs font-medium ${
                  card.trendUp ? 'text-emerald-600' : 'text-red-500'
                }`}>
                  {card.trendUp ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                  {card.trend}
                </div>
              )}
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-1">{card.label}</p>
              <div className="flex items-baseline gap-1">
                <span className="text-3xl font-bold text-gray-800 tracking-tight">{card.value}</span>
                {card.suffix && <span className="text-sm text-gray-400">{card.suffix}</span>}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* 状态分布 - 占 3 列 */}
        <div className="lg:col-span-3 glass-card p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-5 flex items-center gap-2">
            <div className="w-1 h-4 rounded-full bg-indigo-500" />
            候选人状态分布
          </h3>
          <div className="space-y-3">
            {Object.entries(stats?.status_distribution ?? {}).map(([key, count]) => {
              const total = stats?.total_candidates || 1
              const pct = Math.round((Number(count) / total) * 100)
              const colors: Record<string, string> = {
                new: 'bg-blue-500', analyzed: 'bg-purple-500', talent_pool: 'bg-orange-500',
                q_sent: 'bg-yellow-500', q_done: 'bg-indigo-500', scheduled: 'bg-teal-500',
                interviewed: 'bg-cyan-500', hired: 'bg-emerald-500', rejected: 'bg-red-500',
                archived: 'bg-gray-400',
              }
              return (
                <div key={key} className="group">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <div className={`w-2.5 h-2.5 rounded-full ${colors[key] || 'bg-gray-400'} group-hover:scale-125 transition-transform`} />
                      <span className="text-sm text-gray-600">{statusLabels[key] || key}</span>
                    </div>
                    <span className="text-sm font-medium text-gray-800">{count as number}</span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${colors[key] || 'bg-gray-400'}`}
                      style={{ width: `${Math.max(pct, 3)}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* 本周趋势 - 占 2 列 */}
        <div className="lg:col-span-2 glass-card p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-5 flex items-center gap-2">
            <div className="w-1 h-4 rounded-full bg-emerald-500" />
            本周新增趋势
          </h3>
          {stats?.weekly_trend && (
            <div className="flex items-end justify-between h-36 gap-2">
              {stats.weekly_trend.map((day: any, idx: number) => {
                const max = Math.max(...stats.weekly_trend.map((d: any) => d.count), 1)
                const height = Math.max((day.count / max) * 100, 8)
                const isToday = idx === stats.weekly_trend.length - 1
                return (
                  <div key={day.date} className="flex-1 flex flex-col items-center gap-2">
                    <span className={`text-xs font-medium ${isToday ? 'text-indigo-600' : 'text-gray-400'}`}>
                      {day.count}
                    </span>
                    <div
                      className={`w-full max-w-[36px] rounded-t-lg transition-all duration-500 ${
                        isToday
                          ? 'bg-gradient-to-t from-indigo-500 to-purple-400 shadow-lg shadow-indigo-500/25'
                          : 'bg-gradient-to-t from-indigo-200 to-indigo-100'
                      }`}
                      style={{ height: `${height}%` }}
                    />
                    <span className={`text-[11px] ${isToday ? 'text-indigo-500 font-medium' : 'text-gray-400'}`}>
                      {day.date.slice(5)}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* 最近候选人表格 */}
      <div className="glass-card overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100/80 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <div className="w-1 h-4 rounded-full bg-blue-500" />
            最近候选人
          </h3>
          <span className="text-xs text-gray-400">
            {pipeline?.recent?.length || 0} 条记录
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-400 bg-gray-50/50">
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-wider">姓名</th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-wider">岗位</th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-wider">状态</th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-wider">匹配度</th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-wider">日期</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100/80">
              {pipeline?.recent?.map((c: any) => (
                <tr key={c.id} className="hover:bg-indigo-50/50 transition-colors">
                  <td className="px-6 py-3.5">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-xs font-bold">
                        {c.name?.[0] || '?'}
                      </div>
                      <span className="font-medium text-gray-800">{c.name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-3.5 text-gray-600">{c.position}</td>
                  <td className="px-6 py-3.5">
                    <span className={`status-badge ${c.status}`}>
                      {statusLabels[c.status] || c.status}
                    </span>
                  </td>
                  <td className="px-6 py-3.5">
                    {c.match_score != null ? (
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              c.match_score >= 70 ? 'bg-emerald-500' : c.match_score >= 50 ? 'bg-amber-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${c.match_score}%` }}
                          />
                        </div>
                        <span className={`text-xs font-medium ${
                          c.match_score >= 70 ? 'text-emerald-600' : c.match_score >= 50 ? 'text-amber-600' : 'text-red-600'
                        }`}>
                          {c.match_score}分
                        </span>
                      </div>
                    ) : <span className="text-gray-300">-</span>}
                  </td>
                  <td className="px-6 py-3.5 text-gray-400 text-xs">{c.created_at?.slice(0, 10) || '-'}</td>
                </tr>
              ))}
              {(!pipeline?.recent || pipeline.recent.length === 0) && (
                <tr><td colSpan={5} className="px-6 py-12 text-center text-gray-400">暂无数据</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
