import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw, Phone } from "lucide-react";
import { api, errDetail } from "../lib/api";
import { Badge, Button, Card, EmptyState, Field, Input, Modal, PageHeader, Spinner, useToast } from "../components/ui";
import { statusMeta, type PipelineOverview, type TalentPoolItem } from "../types";

const STAGE_KEYS = ["新候选人", "简历已分析", "人才池", "问卷已发送", "问卷已完成", "面试已排期", "已面试", "已录用", "已拒绝"];
const STAGE_COLORS = [
  "bg-slate-400", "bg-blue-500", "bg-amber-500", "bg-purple-500", "bg-violet-500",
  "bg-cyan-500", "bg-indigo-500", "bg-emerald-500", "bg-rose-500",
];

export default function Pipeline() {
  const nav = useNavigate();
  const { toast } = useToast();
  const [data, setData] = useState<PipelineOverview | null>(null);
  const [pool, setPool] = useState<TalentPoolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [reactivateTarget, setReactivateTarget] = useState<TalentPoolItem | null>(null);
  const [newPosition, setNewPosition] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, tp] = await Promise.all([
        api.workflow.pipeline(),
        api.workflow.talentPool({ page: 1, page_size: 50 }),
      ]);
      setData(p.data);
      setPool(tp.data.items);
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setLoading(false); }
  }, []); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  if (loading) return <Spinner />;
  if (!data) return <EmptyState text="加载失败" />;

  const maxStage = Math.max(1, ...Object.values(data.stages));

  const doReactivate = async () => {
    if (!reactivateTarget || !newPosition.trim()) return;
    setBusy(true);
    try {
      await api.workflow.reactivate({ talent_pool_id: reactivateTarget.id, position: newPosition.trim() });
      toast(`已为「${reactivateTarget.original_position}」候选人重新激活流程`);
      setReactivateTarget(null); setNewPosition("");
      load();
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader
        title="招聘管道"
        desc={`共 ${data.total} 位候选人在管道中`}
        actions={<Button variant="outline" onClick={load}><RefreshCw size={14} /> 刷新</Button>}
      />

      {/* 漏斗 */}
      <Card className="p-5 mb-6">
        <div className="space-y-3">
          {STAGE_KEYS.map((s, i) => {
            const v = data.stages[s] ?? 0;
            return (
              <div key={s} className="flex items-center gap-3 text-sm">
                <span className="w-20 shrink-0 text-slate-500">{s}</span>
                <div className="flex-1 h-7 bg-slate-100 rounded-lg overflow-hidden">
                  <div className={`h-full ${STAGE_COLORS[i]} rounded-lg transition-all duration-500 flex items-center justify-end pr-2 min-w-[34px]`}
                    style={{ width: `${Math.max(4, (v / maxStage) * 100)}%` }}>
                    <span className="text-white text-xs font-semibold tabular-nums drop-shadow">{v}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* 最近候选人 */}
      <h3 className="text-sm font-semibold text-slate-700 mb-3">最近录入</h3>
      <div className="grid grid-cols-4 gap-4 mb-8">
        {data.recent.map((r) => {
          const m = statusMeta(r.status);
          return (
            <Card key={r.id} className="p-4 hover:shadow-pop cursor-pointer transition-shadow" >
              <div onClick={() => nav(`/candidates/${r.id}`)}>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-slate-800">{r.name}</span>
                  <Badge label={m.label} cls={m.cls} />
                </div>
                <p className="text-xs text-slate-400 truncate">{r.position}</p>
                {r.match_score != null && (
                  <p className={`mt-2 text-lg font-semibold tabular-nums ${r.match_score >= 80 ? "text-emerald-600" : r.match_score >= 60 ? "text-amber-600" : "text-rose-500"}`}>
                    {r.match_score.toFixed(0)}<span className="text-xs text-slate-300 ml-1">分</span>
                  </p>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      {/* 人才池 */}
      <h3 className="text-sm font-semibold text-slate-700 mb-3">人才池 ({pool.length})</h3>
      {pool.length === 0 ? (
        <EmptyState text="人才池暂无记录" />
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                <th className="px-5 py-3 font-medium">岗位</th>
                <th className="px-5 py-3 font-medium">匹配分</th>
                <th className="px-5 py-3 font-medium">技能</th>
                <th className="px-5 py-3 font-medium">入池原因</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {pool.map((t) => (
                <tr key={t.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/70">
                  <td className="px-5 py-3.5 font-medium text-slate-800">
                    <button className="hover:text-brand-600" onClick={() => nav(`/candidates/${t.candidate_id}`)}>#{t.candidate_id} · {t.original_position}</button>
                  </td>
                  <td className="px-5 py-3.5 tabular-nums">{t.match_score?.toFixed(1) ?? "—"}</td>
                  <td className="px-5 py-3.5 max-w-52">
                    <div className="flex flex-wrap gap-1">
                      {t.skills.slice(0, 4).map((s) => (
                        <span key={s} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">{s}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-5 py-3.5 text-slate-500 truncate max-w-48" title={t.pool_reason ?? ""}>{t.pool_reason ?? "—"}</td>
                  <td className="px-5 py-3.5 text-right">
                    <Button variant="outline" onClick={() => setReactivateTarget(t)}><RefreshCw size={13} /> 重新激活</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <Modal open={!!reactivateTarget} onClose={() => setReactivateTarget(null)} title="从人才池重新激活">
        <Field label="新的应聘岗位">
          <Input value={newPosition} onChange={(e) => setNewPosition(e.target.value)}
            placeholder={reactivateTarget?.original_position} autoFocus />
        </Field>
        <p className="text-xs text-slate-400 mb-4 flex items-center gap-1"><Phone size={12} /> 系统将重置候选人状态并重新进入 AI 分流</p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setReactivateTarget(null)}>取消</Button>
          <Button loading={busy} disabled={!newPosition.trim()} onClick={doReactivate}>确认激活</Button>
        </div>
      </Modal>
    </>
  );
}
