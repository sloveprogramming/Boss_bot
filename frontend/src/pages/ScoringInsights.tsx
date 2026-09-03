import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  AlertTriangle, ArrowRight, History, Lightbulb,
  RefreshCw, Target, TrendingUp, Users,
} from "lucide-react";
import { api, errDetail } from "../lib/api";
import {
  Badge, Button, Card, EmptyState, PageHeader, Spinner, useToast,
} from "../components/ui";
import { useAuth } from "../contexts/AuthContext";
import type { ScoringInsights, ScoringIteration } from "../types";

const pct = (w?: number | null) => (w != null ? `${Math.round(w * 100)}%` : "—");
const num = (n?: number | null) => (n != null ? n.toFixed(1) : "—");

function StatCard({ icon: Icon, label, value, sub }: {
  icon: typeof Users; label: string; value: ReactNode; sub?: string;
}) {
  return (
    <Card className="p-5 flex items-start gap-4 hover:shadow-glass-hover hover:-translate-y-1 transition-all duration-300 ease-fluid cursor-default">
      <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 text-white flex items-center justify-center shrink-0 shadow-lg">
        <Icon size={20} />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-slate-400 font-medium">{label}</p>
        <p className="text-2xl font-semibold font-display text-slate-900 mt-1 tabular-nums">{value}</p>
        {sub && <p className="text-xs text-slate-400 mt-0.5 truncate">{sub}</p>}
      </div>
    </Card>
  );
}

export default function ScoringInsights() {
  const { toast } = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [insights, setInsights] = useState<ScoringInsights | null>(null);
  const [iterations, setIterations] = useState<ScoringIteration[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([api.scoring.insights(), api.scoring.iterations(20)])
      .then(([i, it]) => { setInsights(i.data); setIterations(it.data); })
      .catch((e) => toast(errDetail(e), "err"))
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  const applySuggested = async () => {
    if (!insights?.suggested_weights) return;
    if (!isAdmin) { toast("仅管理员可应用权重", "err"); return; }
    setApplying(true);
    try {
      await api.scoring.applyIteration({
        to_weights: insights.suggested_weights,
        note: "采用页面推荐权重（启发式 v1）",
      });
      toast("已应用为一次迭代");
      load();
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setApplying(false); }
  };

  if (loading && !insights) return <Spinner text="计算评分建议…" />;

  const cur = insights?.current_weights ?? {};
  const sug = insights?.suggested_weights ?? null;
  const canApply = isAdmin && !!sug;

  return (
    <>
      <PageHeader
        title="评分优化"
        desc="根据面试结果的通过率，提出简历评分权重的调整建议，并记录每一次迭代"
        actions={
          <Button disabled={!canApply} loading={applying} onClick={applySuggested}>
            <Target size={14} /> 应用当前建议
          </Button>
        }
      />

      {/* 顶部统计 */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard icon={Users} label="已标注面试样本" value={insights?.labeled_total ?? 0}
          sub="resume 回标 + 面试反馈" />
        <StatCard icon={TrendingUp} label="综合通过率"
          value={insights?.pass_rate != null ? `${insights.pass_rate}%` : "—"}
          sub={`通过 ${insights?.passed ?? 0} 人`} />
        <StatCard icon={Target} label="当前权重"
          value={<span className="flex gap-1.5 flex-wrap">
            {Object.entries(cur).map(([k, w]) => (
              <Badge key={k} label={`${k} ${Math.round(w * 100)}%`} cls="bg-brand-50 text-brand-600" />
            ))}
          </span>}
          sub="全局默认权重" />
        <StatCard icon={History} label="迭代次数" value={iterations.length}
          sub="最近 20 条" />
      </div>

      {/* 建议列表 */}
      {insights && insights.suggestions.length > 0 && (
        <Card className="p-4 mb-6">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 mb-2.5">
            <Lightbulb size={14} className="text-amber-500" /> 建议
          </div>
          <ul className="space-y-2">
            {insights.suggestions.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-600 leading-6">
                {insights.inversions.length > 0 && s.includes("倒挂") ? (
                  <AlertTriangle size={15} className="mt-1 shrink-0 text-rose-500" />
                ) : (
                  <span className="mt-[9px] w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                )}
                <span>{s}</span>
              </li>
            ))}
          </ul>
          {insights.note && <p className="text-[11px] text-slate-300 mt-3">{insights.note}</p>}
        </Card>
      )}

      {!insights || insights.labeled_total === 0 ? (
        <EmptyState
          icon={<Target size={36} />}
          text="暂无可用于评估的面试标签：先去面试管理给候选人提交 pass / reject 反馈，或等待 supervisor 回标"
        />
      ) : (
        <>
          {/* 各维度区分度 → 建议权重 */}
          <Card className="p-5 mb-6">
            <h3 className="text-sm font-semibold font-display text-slate-800 mb-4">维度区分度与权重建议</h3>
            <div className="space-y-4">
              {insights.dimension_stats.map((st) => {
                const nextW = sug?.[st.key];
                const changed = nextW != null && Math.abs(nextW - st.weight) > 0.001;
                const barW = st.pass_n > 0 || st.reject_n > 0 ? 100 : 0;
                return (
                  <div key={st.key} className="rounded-xl border border-slate-100 bg-white/60 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-slate-800">{st.label}</span>
                        <span className="text-xs text-slate-400">{st.key}</span>
                      </div>
                      <div className="flex items-center gap-2 text-xs tabular-nums">
                        <span className="text-slate-400">当前 <b className="text-slate-700">{pct(st.weight)}</b></span>
                        {changed && (
                          <>
                            <ArrowRight size={13} className="text-slate-300" />
                            <span className="text-brand-600 font-semibold">建议 {pct(nextW)}</span>
                            <Badge
                              label={nextW! > st.weight ? "上调" : "下调"}
                              cls={nextW! > st.weight ? "bg-emerald-50 text-emerald-600" : "bg-rose-50 text-rose-500"}
                            />
                          </>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-6 mb-2">
                      <div>
                        <p className="text-[11px] text-slate-400 mb-1">通过者均分 {num(st.pass_avg)}（n={st.pass_n}）</p>
                        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                          <div className="h-full rounded-full bg-emerald-400"
                            style={{ width: `${(st.pass_avg ?? 0) / 100 * barW}%` }} />
                        </div>
                      </div>
                      <div>
                        <p className="text-[11px] text-slate-400 mb-1">未通过均分 {num(st.reject_avg)}（n={st.reject_n}）</p>
                        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                          <div className="h-full rounded-full bg-rose-300"
                            style={{ width: `${(st.reject_avg ?? 0) / 100 * barW}%` }} />
                        </div>
                      </div>
                    </div>
                    <p className="text-xs text-slate-400">区分度 {st.gap != null ? `${st.gap > 0 ? "+" : ""}${st.gap}` : "—"}
                      {st.pass_n < 3 || st.reject_n < 3
                        ? "（通过/未通过样本需各 ≥3 才参与建议）" : ""}
                    </p>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* 分桶通过率 */}
          <Card className="p-5 mb-6">
            <h3 className="text-sm font-semibold font-display text-slate-800 mb-2">按匹配分分桶的通过率</h3>
            {insights.inversions.length > 0 && (
              <div className="mb-3 rounded-xl bg-rose-50/80 border border-rose-100 px-3 py-2.5 text-xs text-rose-600">
                {insights.inversions.map((inv) => <p key={inv.detail}>{inv.detail}</p>)}
              </div>
            )}
            {insights.buckets.length === 0 ? (
              <p className="text-sm text-slate-300 py-6 text-center">暂无已标注分数样本</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                      <th className="px-4 py-2.5 font-medium">分数段</th>
                      <th className="px-4 py-2.5 font-medium">样本</th>
                      <th className="px-4 py-2.5 font-medium">通过</th>
                      <th className="px-4 py-2.5 font-medium w-56">通过率</th>
                    </tr>
                  </thead>
                  <tbody>
                    {insights.buckets.map((b) => (
                      <tr key={b.bucket} className="border-b border-slate-50 last:border-0">
                        <td className="px-4 py-2.5 font-medium text-slate-700 tabular-nums">{b.bucket} 分</td>
                        <td className="px-4 py-2.5 text-slate-600 tabular-nums">{b.total}</td>
                        <td className="px-4 py-2.5 text-slate-600 tabular-nums">{b.passed}</td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden flex-1">
                              <div className={`h-full rounded-full ${b.pass_rate >= 60 ? "bg-emerald-400" : "bg-amber-400"}`}
                                style={{ width: `${b.pass_rate}%` }} />
                            </div>
                            <span className="text-xs text-slate-500 tabular-nums w-10 text-right">{b.pass_rate}%</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* 最近样本明细 + 迭代历史 */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <Card className="p-5">
              <h3 className="text-sm font-semibold font-display text-slate-800 mb-3">最近样本明细（{insights.recent_samples.length}）</h3>
              {insights.recent_samples.length === 0 ? (
                <p className="text-sm text-slate-300 py-6 text-center">暂无明细</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                        <th className="px-3 py-2 font-medium">候选人</th>
                        <th className="px-3 py-2 font-medium">岗位</th>
                        <th className="px-3 py-2 font-medium">结果</th>
                        <th className="px-3 py-2 font-medium">匹配分</th>
                      </tr>
                    </thead>
                    <tbody>
                      {insights.recent_samples.map((s) => (
                        <tr key={s.candidate_id} className="border-b border-slate-50 last:border-0">
                          <td className="px-3 py-2 text-slate-700">{s.candidate_name}</td>
                          <td className="px-3 py-2 text-slate-500 max-w-[9rem] truncate">{s.position || "—"}</td>
                          <td className="px-3 py-2">
                            <Badge label={s.outcome === "pass" ? "通过" : "拒绝"}
                              cls={s.outcome === "pass" ? "bg-emerald-50 text-emerald-600" : "bg-rose-50 text-rose-500"} />
                          </td>
                          <td className="px-3 py-2 text-slate-600 tabular-nums">{s.score != null ? s.score.toFixed(1) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card className="p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold font-display text-slate-800">迭代历史</h3>
                <Button variant="ghost" className="!px-2.5 !py-1 text-xs" onClick={load}>
                  <RefreshCw size={13} /> 刷新
                </Button>
              </div>
              {iterations.length === 0 ? (
                <p className="text-sm text-slate-300 py-6 text-center">还没有迭代记录，点击右上角"应用当前建议"开始</p>
              ) : (
                <ul className="space-y-2.5">
                  {iterations.map((it) => {
                    const diff = Object.keys(it.to_weights).map((k) => {
                      const f = it.from_weights?.[k];
                      const t = it.to_weights?.[k];
                      return { k, f, t };
                    }).filter((x) => x.f != null && x.t != null && Math.abs(x.t - x.f) > 0.001);
                    return (
                      <li key={it.id} className="rounded-xl border border-slate-100 bg-white/60 px-3.5 py-2.5 text-sm">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="font-medium text-slate-700">#{it.id}
                            {it.category ? <Badge label={it.category} cls="bg-slate-100 text-slate-500 ml-2" /> : null}
                          </span>
                          <span className="text-xs text-slate-400 tabular-nums">
                            {it.created_at ? new Date(it.created_at).toLocaleString() : "—"}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mb-1.5">
                          {it.applied_by ? `由 ${it.applied_by} 应用` : "系统应用"}
                          {it.note ? ` · ${it.note}` : ""}
                        </p>
                        <p className="text-xs text-slate-600 flex flex-wrap gap-x-3 gap-y-0.5 tabular-nums">
                          {diff.length === 0
                            ? Object.entries(it.to_weights).map(([k, w]) => (
                              <span key={k} className="text-slate-400">{k} {Math.round(w * 100)}%</span>
                            ))
                            : diff.map(({ k, f, t }) => (
                              <span key={k}>{k}：{Math.round((f ?? 0) * 100)}% → {Math.round((t ?? 0) * 100)}%</span>
                            ))}
                        </p>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          </div>

          <p className="text-[11px] text-slate-300 mt-4">
            权重应用写入进程内存，重启后回退 .env（与既有评分权重行为一致）；每次应用都会记录到上方迭代历史。
          </p>
        </>
      )}
    </>
  );
}
