import { useEffect, useState, type ReactNode } from "react";
import { AlertCircle, Award, CheckCircle2, ChevronRight, ClipboardCheck, Database, XCircle } from "lucide-react";
import { api, errDetail } from "../lib/api";
import { Badge, Button, Card, Drawer, EmptyState, PageHeader, Spinner, useToast } from "../components/ui";
import type { ExamAnalysisItem } from "../types";

const STAT_GRADS = [
  "from-indigo-500 to-blue-500",
  "from-emerald-500 to-teal-500",
  "from-violet-500 to-purple-500",
  "from-rose-500 to-orange-500",
];

const EXAM_STATUS: Record<string, { label: string; cls: string }> = {
  completed: { label: "已完成", cls: "bg-emerald-50 text-emerald-600" },
  failed:    { label: "失败",   cls: "bg-rose-50 text-rose-600" },
  analyzing: { label: "分析中", cls: "bg-sky-50 text-sky-600" },
  pending:   { label: "待处理", cls: "bg-amber-50 text-amber-600" },
};

const examStatus = (s: string) => EXAM_STATUS[s] ?? { label: s, cls: "bg-slate-100 text-slate-500" };

// 仅当同时有得分与满分才返回百分比，避免“未出分”被画成 0%
const scorePct = (it: ExamAnalysisItem): number | null =>
  it.exam_score != null && it.exam_total ? Math.round((it.exam_score / it.exam_total) * 100) : null;

const scoreTextCls = (it: ExamAnalysisItem): string => {
  if (it.exam_score == null) return "text-slate-300";
  const pct = scorePct(it);
  return pct != null && pct >= 60 ? "text-emerald-600" : "text-rose-500";
};

function StatCard({ icon: Icon, label, value, sub, grad, delay }: {
  icon: typeof Database; label: string; value: string | number; sub?: string; grad: string; delay: number;
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

function DetailRow({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-slate-100/70 py-2.5 text-sm last:border-0">
      <dt className="shrink-0 text-slate-400">{k}</dt>
      <dd className="text-right font-medium text-slate-700 min-w-0 break-words">{v}</dd>
    </div>
  );
}

function DetailPanel({ it }: { it: ExamAnalysisItem }) {
  const st = examStatus(it.analysis_status);
  const pct = scorePct(it);
  const pass = pct != null && pct >= 60;

  return (
    <div className="space-y-5">
      {/* 身份区 */}
      <div className="flex items-center gap-3">
        <span className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white flex items-center justify-center text-lg font-semibold shadow-glow-brand shrink-0">
          {(it.candidate_name ?? "?").slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold font-display text-slate-900 truncate">{it.candidate_name || "—"}</p>
          {it.candidate_phone ? (
            <a href={`tel:${it.candidate_phone}`} className="text-xs text-brand-600 hover:text-brand-700 tabular-nums">
              {it.candidate_phone}
            </a>
          ) : (
            <p className="text-xs text-slate-400">未留联系方式</p>
          )}
        </div>
        <Badge label={st.label} cls={st.cls} />
      </div>

      <dl className="rounded-xl border border-slate-100 bg-white/70 px-4 py-1.5">
        <DetailRow k="试卷" v={it.exam_title || "—"} />
        <DetailRow
          k="得分"
          v={
            it.exam_score != null ? (
              <span className={pass ? "text-emerald-600" : "text-rose-500"}>
                {it.exam_score}{it.exam_total != null ? ` / ${it.exam_total}` : ""}
              </span>
            ) : "—"
          }
        />
        <DetailRow k="作答用时" v={it.exam_duration != null ? `${it.exam_duration} 分钟` : "—"} />
        <DetailRow k="提交时间" v={it.created_at ? new Date(it.created_at).toLocaleString() : "—"} />
        <DetailRow k="完成时间" v={it.analyzed_at ? new Date(it.analyzed_at).toLocaleString() : "—"} />
      </dl>

      {it.error_message && (
        <div className="flex items-start gap-2.5 rounded-xl border border-rose-100 bg-rose-50/70 px-4 py-3 text-sm text-rose-600">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <span className="break-all">{it.error_message}</span>
        </div>
      )}

      <section>
        <h4 className="text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wide">AI 分析结果</h4>
        {it.analysis_result && Object.keys(it.analysis_result).length > 0 ? (
          <ResultView data={it.analysis_result} />
        ) : (
          <p className="text-sm text-slate-300">暂无分析结果</p>
        )}
      </section>
    </div>
  );
}

function ResultView({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  return (
    <dl className="rounded-xl border border-slate-100 bg-white/70 divide-y divide-slate-50 overflow-hidden">
      {entries.map(([k, v]) => {
        const plain = v == null || ["string", "number", "boolean"].includes(typeof v);
        return (
          <div key={k} className="grid grid-cols-[6.5rem_1fr] gap-3 px-4 py-2.5 text-sm items-start">
            <dt className="text-slate-400 truncate font-medium pt-0.5">{k}</dt>
            <dd className="text-slate-700 min-w-0 break-words">
              {plain ? String(v ?? "null") : (
                <pre className="text-xs leading-5 bg-slate-50 rounded-lg p-2 overflow-x-auto max-h-64 text-slate-600 whitespace-pre-wrap">
                  {JSON.stringify(v, null, 2)}
                </pre>
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export default function ExamAnalysis() {
  const { toast } = useToast();
  const [items, setItems] = useState<ExamAnalysisItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const pageSize = 20;

  const load = (p: number) => {
    setLoading(true);
    api.exam.list({ page: p, page_size: pageSize })
      .then((r) => { setItems(r.data.items); setTotal(r.data.total); setPage(p); })
      .catch((e) => toast(errDetail(e), "err"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(1); /* eslint-disable-next-line */ }, []);

  const selectedItem = selected != null ? items.find((i) => i.id === selected) ?? null : null;

  // 统计卡数据仅来自现有列表接口：total 为全库，其余指标按当前页（sub 中如实标注“本页”）
  const completed = items.filter((i) => i.analysis_status === "completed").length;
  const failed = items.filter((i) => i.analysis_status === "failed").length;
  const scoredItems = items.filter((i) => i.exam_score != null);
  const avgScore = scoredItems.length
    ? (scoredItems.reduce((s, i) => s + (i.exam_score ?? 0), 0) / scoredItems.length).toFixed(1)
    : "—";

  return (
    <>
      <PageHeader title="试卷分析" desc="考试系统与自研测评推送的分析记录（查看成绩与 AI 分析结果）" />

      {loading && items.length === 0 ? (
        <Spinner />
      ) : total === 0 ? (
        <EmptyState icon={<ClipboardCheck size={36} />} text="暂无试卷分析记录" />
      ) : (
        <>
          {/* 顶部统计卡 */}
          <div className="grid grid-cols-4 gap-4 mb-6">
            <StatCard icon={Database} label="分析记录" value={total} sub="全库累计" grad={STAT_GRADS[0]} delay={0} />
            <StatCard icon={CheckCircle2} label="已完成（本页）" value={completed} sub={`本页 ${items.length} 条记录中`} grad={STAT_GRADS[1]} delay={80} />
            <StatCard icon={Award} label="平均分（本页）" value={avgScore} sub={scoredItems.length ? `本页 ${scoredItems.length} 条有分记录` : "本页暂无出分记录"} grad={STAT_GRADS[2]} delay={160} />
            <StatCard icon={XCircle} label="分析失败（本页）" value={failed} sub="可在详情中查看失败原因" grad={STAT_GRADS[3]} delay={240} />
          </div>

          <Card>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                  <th className="px-4 py-3 font-medium">候选人</th>
                  <th className="px-4 py-3 font-medium">试卷</th>
                  <th className="px-4 py-3 font-medium">得分</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">时间</th>
                  <th className="px-4 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const st = examStatus(it.analysis_status);
                  const pct = scorePct(it);
                  return (
                    <tr
                      key={it.id}
                      onClick={() => setSelected(it.id)}
                      className="group border-b border-slate-50 last:border-0 hover:bg-slate-50/70 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span className="w-8 h-8 rounded-full bg-brand-100 text-brand-600 flex items-center justify-center text-sm font-semibold shrink-0">
                            {(it.candidate_name ?? "?").slice(0, 1).toUpperCase()}
                          </span>
                          <div className="min-w-0">
                            <p className="font-medium text-slate-800 leading-tight truncate">{it.candidate_name || "—"}</p>
                            {it.candidate_phone && (
                              <p className="text-xs text-slate-400 tabular-nums leading-tight">{it.candidate_phone}</p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-600 max-w-[16rem] truncate">{it.exam_title}</td>
                      <td className="px-4 py-3">
                        <div className="min-w-[100px]">
                          <div className="flex items-baseline gap-1">
                            <span className={`text-sm font-semibold tabular-nums ${scoreTextCls(it)}`}>
                              {it.exam_score ?? "—"}
                            </span>
                            {it.exam_score != null && it.exam_total != null && (
                              <span className="text-xs text-slate-400 tabular-nums">/ {it.exam_total}</span>
                            )}
                          </div>
                          {pct != null && (
                            <div className="mt-1.5 h-1 rounded-full bg-slate-100 overflow-hidden">
                              <div className={`h-full rounded-full ${pct >= 60 ? "bg-emerald-500" : "bg-rose-400"}`} style={{ width: `${pct}%` }} />
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3"><Badge label={st.label} cls={st.cls} /></td>
                      <td className="px-4 py-3 text-slate-400 tabular-nums whitespace-nowrap">{new Date(it.created_at).toLocaleString()}</td>
                      <td className="px-3 py-3 text-right">
                        <ChevronRight size={16} className="inline text-slate-300 group-hover:text-brand-400 transition-colors" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>

          <div className="flex items-center justify-between mt-4">
            <p className="text-xs text-slate-400">共 {total} 条 · 第 {page} / {Math.max(1, Math.ceil(total / pageSize))} 页</p>
            <div className="flex gap-2">
              <Button variant="outline" disabled={page <= 1} loading={loading && page > 1} onClick={() => load(page - 1)}>上一页</Button>
              <Button variant="outline" disabled={page * pageSize >= total} loading={loading} onClick={() => load(page + 1)}>下一页</Button>
            </div>
          </div>
        </>
      )}

      <Drawer open={selectedItem != null} onClose={() => setSelected(null)} title="分析详情">
        {selectedItem && <DetailPanel it={selectedItem} />}
      </Drawer>
    </>
  );
}
