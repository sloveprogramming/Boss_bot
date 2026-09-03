import { useCallback, useEffect, useState } from "react";
import {
  CalendarClock, CalendarPlus, ChevronLeft, ChevronRight,
  MessageSquareQuote, Clock,
} from "lucide-react";
import { api, errDetail } from "../lib/api";
import {
  Badge, Button, Card, EmptyState, Field, Input, Modal,
  PageHeader, Select, Spinner, Textarea, useToast,
} from "../components/ui";
import type {
  Candidate, CalendarInterviewItem, CalendarInterviewResponse, TimeSlot,
} from "../types";

const pad = (n: number) => String(n).padStart(2, "0");
const fmtDateTime = (s?: string | null) =>
  s ? new Date(s).toLocaleString("zh-CN", { hour12: false }) : "—";
const fmtTime = (s?: string | null) =>
  s
    ? new Date(s).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })
    : "";

const ROUND_LABEL: Record<string, string> = {
  first: "第一轮", technical: "技术面", hr: "HR 面", final: "终面",
};
const roundLabel = (r: string) => ROUND_LABEL[r] ?? `第 ${r} 轮`;

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  confirmed:       { label: "已确认",   cls: "bg-emerald-50 text-emerald-600" },
  completed:       { label: "已完成",   cls: "bg-indigo-50 text-indigo-600" },
  pending:         { label: "待安排",   cls: "bg-slate-100 text-slate-500" },
  awaiting_confirm:{ label: "待确认",   cls: "bg-amber-50 text-amber-600" },
  rescheduling:    { label: "改期中",   cls: "bg-sky-50 text-sky-600" },
  cancelled:       { label: "已取消",   cls: "bg-rose-50 text-rose-600" },
  no_show:         { label: "未出席",   cls: "bg-rose-50 text-rose-600" },
};
const statusMeta = (s: string) => STATUS_BADGE[s] ?? { label: s, cls: "bg-slate-100 text-slate-500" };

// 日历时间块配色（按状态）
const CHIP_CLS: Record<string, string> = {
  confirmed:        "bg-emerald-500/90 text-white",
  completed:        "bg-indigo-500/85 text-white",
  pending:          "bg-slate-400/85 text-white",
  awaiting_confirm: "bg-amber-400/90 text-amber-950",
  rescheduling:     "bg-sky-500/85 text-white",
  cancelled:        "bg-rose-400/85 text-white line-through opacity-80",
  no_show:          "bg-rose-500/85 text-white",
};
const chipCls = (s: string) => CHIP_CLS[s] ?? "bg-slate-400/85 text-white";

const DECISION_LABEL: Record<string, { label: string; cls: string }> = {
  pass:   { label: "通过",   cls: "bg-emerald-50 text-emerald-600" },
  reject: { label: "拒绝",   cls: "bg-rose-50 text-rose-600" },
  pending:{ label: "待定",   cls: "bg-amber-50 text-amber-600" },
};

export default function Interviews() {
  const { toast } = useToast();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candsLoading, setCandsLoading] = useState(true);

  // 月历游标
  const [cur, setCur] = useState(() => {
    const d = new Date();
    return { y: d.getFullYear(), m: d.getMonth() };
  });
  const { y, m } = cur;

  // 筛选 + 数据
  const [filterCid, setFilterCid] = useState<number | null>(null);
  const [events, setEvents] = useState<CalendarInterviewItem[]>([]);
  const [unconfirmed, setUnconfirmed] = useState<CalendarInterviewResponse["unconfirmed"]>([]);
  const [loading, setLoading] = useState(true);

  // 面试详情
  const [detail, setDetail] = useState<CalendarInterviewItem | null>(null);

  // 排期表单
  const [open, setOpen] = useState(false);
  const [schedCid, setSchedCid] = useState<number | null>(null);
  const [form, setForm] = useState({ start: "", end: "", interviewers: "面试官" });
  const [slots, setSlots] = useState<TimeSlot[]>([]);
  const [interviewId, setInterviewId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  // 反馈
  const [fbTarget, setFbTarget] = useState<CalendarInterviewItem | null>(null);
  const [fb, setFb] = useState({ rating: 4, strengths: "", weaknesses: "", decision: "pass", detail: "" });

  useEffect(() => {
    api.candidates.list({ page: 1, page_size: 200 })
      .then((r) => setCandidates(r.data.items))
      .catch((e) => toast(errDetail(e), "err"))
      .finally(() => setCandsLoading(false));
  }, []); // eslint-disable-line

  const monthStart = `${y}-${pad(m + 1)}-01`;
  const monthEnd = `${y}-${pad(m + 1)}-${pad(new Date(y, m + 1, 0).getDate())}`;

  const loadCalendar = useCallback(() => {
    setLoading(true);
    api.interviews.calendar({ start: monthStart, end: monthEnd, candidate_id: filterCid ?? undefined })
      .then((r) => { setEvents(r.data.items); setUnconfirmed(r.data.unconfirmed); })
      .catch((e) => { toast(errDetail(e), "err"); setEvents([]); setUnconfirmed([]); })
      .finally(() => setLoading(false));
  }, [monthStart, monthEnd, filterCid]); // eslint-disable-line

  useEffect(() => { loadCalendar(); }, [loadCalendar]);

  const moveMonth = (delta: number) => {
    const d = new Date(y, m + delta, 1);
    setCur({ y: d.getFullYear(), m: d.getMonth() });
  };
  const goToday = () => {
    const d = new Date();
    setCur({ y: d.getFullYear(), m: d.getMonth() });
  };

  // ===== AI 排期 =====
  const openSched = (cid: number | null = null) => {
    setSchedCid(cid ?? filterCid);
    setForm({ start: "", end: "", interviewers: "面试官" });
    setSlots([]); setInterviewId(null);
    setOpen(true);
  };

  const genSlots = async () => {
    if (!schedCid || !form.start || !form.end) { toast("请选择候选人和日期范围", "err"); return; }
    if (form.end < form.start) { toast("结束日期需晚于开始日期", "err"); return; }
    setBusy(true); setSlots([]);
    try {
      const { data } = await api.interviews.generateSlots({
        candidate_id: schedCid,
        date_range_start: form.start,
        date_range_end: form.end,
        interviewers: form.interviewers.split(/[,，、]/).map((s) => s.trim()).filter(Boolean),
      });
      setSlots(data.proposed_slots ?? []);
      setInterviewId(data.interview_id);
      toast(`已生成 ${data.proposed_slots?.length ?? 0} 个可选时间段`);
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setBusy(false); }
  };

  const confirmSlot = async (slot: TimeSlot) => {
    if (!interviewId) return;
    setBusy(true);
    try {
      await api.interviews.confirmSlot({
        interview_id: interviewId,
        selected_slot: slot,
        location: "线上会议",
      });
      toast("面试时间已确认");
      setOpen(false); setSlots([]); setInterviewId(null);
      loadCalendar();
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setBusy(false); }
  };

  // ===== 面试反馈 =====
  const openFeedback = (iv: CalendarInterviewItem) => {
    const f = iv.feedback && typeof iv.feedback === "object" ? iv.feedback : {};
    const d = String(f.decision ?? "");
    setFb({
      rating: typeof f.rating === "number" ? f.rating : 4,
      strengths: Array.isArray(f.strengths) ? f.strengths.join("，") : "",
      weaknesses: Array.isArray(f.weaknesses) ? f.weaknesses.join("，") : "",
      decision: ["pass", "reject", "pending"].includes(d) ? d : "pass",
      detail: typeof f.detail === "string" ? f.detail : "",
    });
    setFbTarget(iv);
  };

  const submitFeedback = async () => {
    if (!fbTarget) return;
    setBusy(true);
    try {
      await api.interviews.feedback({
        interview_id: fbTarget.id,
        interviewer: fbTarget.interviewers?.[0] ?? "面试官",
        rating: fb.rating,
        strengths: fb.strengths.split(/[,，、\n]/).map((s) => s.trim()).filter(Boolean),
        weaknesses: fb.weaknesses.split(/[,，、\n]/).map((s) => s.trim()).filter(Boolean),
        decision: fb.decision,
        detail: fb.detail,
      });
      toast("面试反馈已提交，AI 将给出综合评审");
      setFbTarget(null); setDetail(null);
      loadCalendar();
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setBusy(false); }
  };

  // ===== 月历网格 =====
  const firstDay = new Date(y, m, 1);
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const leading = firstDay.getDay(); // 0=周日
  const cellTotal = Math.ceil((leading + daysInMonth) / 7) * 7;

  const byDate: Record<string, CalendarInterviewItem[]> = {};
  for (const ev of events) {
    const k = (ev.confirmed_start ?? "").slice(0, 10);
    (byDate[k] = byDate[k] ?? []).push(ev);
  }
  const todayKey = `${new Date().getFullYear()}-${pad(new Date().getMonth() + 1)}-${pad(new Date().getDate())}`;

  const cells: { date: string; day: number | null; list: CalendarInterviewItem[] }[] = [];
  for (let i = 0; i < cellTotal; i++) {
    const day = i - leading + 1;
    if (day < 1 || day > daysInMonth) { cells.push({ date: "", day: null, list: [] }); continue; }
    const date = `${y}-${pad(m + 1)}-${pad(day)}`;
    cells.push({ date, day, list: byDate[date] ?? [] });
  }

  if (candsLoading) return <Spinner />;

  return (
    <>
      <PageHeader
        title="面试管理"
        desc="按日程查看全部面试安排；右上角筛选候选人后，日历只显示该候选人的面试时间"
        actions={
          <div className="flex gap-2">
            <div className="w-60 shrink-0">
              <Select value={filterCid ?? ""} onChange={(e) => setFilterCid(e.target.value ? Number(e.target.value) : null)}>
                <option value="">全部候选人</option>
                {candidates.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} · {c.position}</option>
                ))}
              </Select>
            </div>
            <Button onClick={() => openSched(null)}><CalendarPlus size={14} /> AI 排期</Button>
          </div>
        }
      />

      {/* 月历工具栏 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => moveMonth(-1)} className="!px-2.5"><ChevronLeft size={15} /></Button>
          <Button variant="outline" onClick={() => moveMonth(1)} className="!px-2.5"><ChevronRight size={15} /></Button>
          <Button variant="ghost" onClick={goToday}>今天</Button>
        </div>
        <h2 className="text-base font-semibold font-display text-slate-800">{y} 年 {m + 1} 月</h2>
        <div className="text-xs text-slate-400 flex items-center gap-1.5">
          <CalendarClock size={14} className="text-slate-300" />
          {events.length} 场已确认
          {unconfirmed.length > 0 && <span className="text-amber-500"> · {unconfirmed.length} 场待确认</span>}
        </div>
      </div>

      <Card className="overflow-hidden">
        <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50/60 text-xs text-slate-400 font-medium">
          {["日", "一", "二", "三", "四", "五", "六"].map((w) => (
            <div key={w} className="px-3 py-2">{w}</div>
          ))}
        </div>

        {loading ? (
          <div className="py-20"><Spinner text="加载面试日程…" /></div>
        ) : (
          <div className="grid grid-cols-7 border-t border-l border-slate-100">
            {cells.map((c, i) => (
              <div
                key={i}
                className={`min-h-[104px] border-r border-b border-slate-100 p-1.5 ${
                  c.day === null ? "bg-slate-50/60" : "hover:bg-slate-50/40 transition-colors"
                }`}
              >
                {c.day !== null && (
                  <>
                    <div className="flex items-center justify-between mb-1 px-0.5">
                      <span
                        className={`text-xs tabular-nums ${
                          c.date === todayKey
                            ? "grad-anim text-white rounded-full w-5 h-5 flex items-center justify-center font-semibold"
                            : c.day === 1 || new Date(c.date).getDay() === 0
                              ? "text-rose-500 font-medium"
                              : "text-slate-500"
                        }`}
                      >
                        {c.day}
                      </span>
                    </div>
                    <div className="space-y-1 overflow-hidden">
                      {c.list.slice(0, 3).map((ev) => (
                        <button
                          key={ev.id}
                          onClick={() => setDetail(ev)}
                          title={`${ev.candidate_name} ${fmtDateTime(ev.confirmed_start)}`}
                          className={`w-full text-left rounded-md px-1.5 py-0.5 text-[11px] leading-4 truncate block transition-transform hover:scale-[1.02] ${chipCls(ev.status)}`}
                        >
                          <span className="tabular-nums">{fmtTime(ev.confirmed_start)}</span>{" "}
                          {ev.candidate_name}
                        </button>
                      ))}
                      {c.list.length > 3 && (
                        <p className="text-[11px] text-slate-400 px-1">+{c.list.length - 3} 场</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* 待确认 / 未排期面板 */}
      {unconfirmed.length > 0 && (
        <Card className="mt-4 p-4">
          <p className="text-xs font-semibold text-slate-500 mb-2.5 flex items-center gap-1.5">
            <Clock size={13} className="text-amber-500" />
            待确认 / 未排期（以下面试尚未确认时间，不会显示在日历上）
          </p>
          <div className="space-y-2">
            {unconfirmed.map((iv) => (
              <div key={iv.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-white/60 px-3 py-2 text-sm">
                <div className="min-w-0">
                  <span className="font-medium text-slate-700">{iv.candidate_name}</span>
                  <span className="ml-2 text-xs text-slate-400">{roundLabel(iv.round)}</span>
                  <p className="text-xs text-slate-400 truncate mt-0.5">
                    {iv.proposed_slots?.map((s) => `${s.date} ${s.start_time}-${s.end_time}`).join("　") || "尚未生成可选时段"}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge label={statusMeta(iv.status).label} cls={statusMeta(iv.status).cls} />
                  <Button variant="outline" className="!px-2.5 !py-1.5 text-xs" onClick={() => openSched(iv.candidate_id)}>
                    安排
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 面试详情弹窗 */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title="面试详情" width="max-w-lg">
        {detail && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <span className="w-11 h-11 rounded-full bg-gradient-to-br from-brand-500 to-violet-500 text-white flex items-center justify-center text-base font-semibold shrink-0">
                {detail.candidate_name.slice(0, 1).toUpperCase()}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-slate-900">{detail.candidate_name}</p>
                <p className="text-xs text-slate-400">{detail.position || "—"} · {roundLabel(detail.round)}</p>
              </div>
              <Badge label={statusMeta(detail.status).label} cls={statusMeta(detail.status).cls} />
            </div>

            <dl className="rounded-xl border border-slate-100 bg-white/70 px-4 py-1.5 text-sm">
              <div className="flex justify-between gap-4 border-b border-slate-100/70 py-2.5 last:border-0">
                <dt className="shrink-0 text-slate-400">时间</dt>
                <dd className="text-right font-medium text-slate-700 tabular-nums">
                  {fmtDateTime(detail.confirmed_start)} — {fmtDateTime(detail.confirmed_end)}
                </dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-slate-100/70 py-2.5 last:border-0">
                <dt className="shrink-0 text-slate-400">地点</dt>
                <dd className="text-right font-medium text-slate-700">{detail.location || detail.meeting_link || "—"}</dd>
              </div>
              {detail.interviewers && detail.interviewers.length > 0 && (
                <div className="flex justify-between gap-4 border-b border-slate-100/70 py-2.5 last:border-0">
                  <dt className="shrink-0 text-slate-400">面试官</dt>
                  <dd className="text-right font-medium text-slate-700">{detail.interviewers.join("、")}</dd>
                </div>
              )}
              {detail.feedback && Object.keys(detail.feedback).length > 0 && (
                <div className="flex justify-between gap-4 border-b border-slate-100/70 py-2.5 last:border-0">
                  <dt className="shrink-0 text-slate-400">反馈结论</dt>
                  <dd className="text-right">
                    {detail.feedback.decision && ["pass", "reject", "pending"].includes(String(detail.feedback.decision)) ? (
                      <Badge label={DECISION_LABEL[String(detail.feedback.decision)].label} cls={DECISION_LABEL[String(detail.feedback.decision)].cls} />
                    ) : (
                      <span className="text-slate-400">未填写</span>
                    )}
                  </dd>
                </div>
              )}
            </dl>

            {detail.ai_summary ? (
              <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700 leading-6">
                <b className="text-slate-500 mr-1">AI 评审摘要</b>{detail.ai_summary}
              </div>
            ) : (
              <p className="text-xs text-slate-300">暂无 AI 评审摘要</p>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setDetail(null)}>关闭</Button>
              <Button variant="outline" onClick={() => openFeedback(detail)}>
                <MessageSquareQuote size={13} /> 提交面试反馈
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* AI 排期弹窗 */}
      <Modal open={open} onClose={() => setOpen(false)} title="AI 智能排期" width="max-w-xl">
        <Field label="候选人 *">
          <Select value={schedCid ?? ""} onChange={(e) => setSchedCid(e.target.value ? Number(e.target.value) : null)}>
            <option value="">选择候选人…</option>
            {candidates.map((c) => (
              <option key={c.id} value={c.id}>{c.name} · {c.position}</option>
            ))}
          </Select>
        </Field>
        <Field label="面试官（逗号分隔）">
          <Input value={form.interviewers} onChange={(e) => setForm({ ...form, interviewers: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="开始日期"><Input type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></Field>
          <Field label="结束日期"><Input type="date" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></Field>
        </div>
        <div className="flex justify-end mt-1">
          <Button loading={busy} onClick={genSlots}>生成推荐时间段</Button>
        </div>

        {slots.length > 0 && (
          <div className="mt-5 border-t border-slate-100 pt-4">
            <p className="text-xs font-medium text-slate-500 mb-2.5">确认一个时间段（将通知候选人）：</p>
            <div className="grid grid-cols-3 gap-2">
              {slots.map((s, i) => (
                <button key={i} disabled={busy}
                  onClick={() => confirmSlot(s)}
                  className="rounded-xl border border-slate-200 p-3 text-center hover:border-brand-500 hover:bg-brand-50 transition-colors disabled:opacity-50">
                  <p className="text-sm font-medium text-slate-800">{s.date}</p>
                  <p className="text-xs text-brand-600 mt-1 tabular-nums">{s.start_time} – {s.end_time}</p>
                </button>
              ))}
            </div>
          </div>
        )}
      </Modal>

      {/* 反馈弹窗 */}
      <Modal open={!!fbTarget} onClose={() => setFbTarget(null)} title={`面试反馈 · #${fbTarget?.id}`}>
        <div className="grid grid-cols-2 gap-4">
          <Field label="评分（1-5）">
            <Select value={fb.rating} onChange={(e) => setFb({ ...fb, rating: Number(e.target.value) })}>
              {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} 分</option>)}
            </Select>
          </Field>
          <Field label="结论">
            <Select value={fb.decision} onChange={(e) => setFb({ ...fb, decision: e.target.value })}>
              <option value="pass">通过</option>
              <option value="reject">拒绝</option>
              <option value="pending">待定</option>
            </Select>
          </Field>
        </div>
        <Field label="优势（逗号分隔）"><Textarea rows={2} value={fb.strengths} onChange={(e) => setFb({ ...fb, strengths: e.target.value })} /></Field>
        <Field label="不足（逗号分隔）"><Textarea rows={2} value={fb.weaknesses} onChange={(e) => setFb({ ...fb, weaknesses: e.target.value })} /></Field>
        <Field label="详细评价"><Textarea rows={3} value={fb.detail} onChange={(e) => setFb({ ...fb, detail: e.target.value })} placeholder="选填" /></Field>
        <div className="flex justify-end gap-2 mt-1">
          <Button variant="ghost" onClick={() => setFbTarget(null)}>取消</Button>
          <Button loading={busy} onClick={submitFeedback}>提交</Button>
        </div>
      </Modal>
    </>
  );
}
