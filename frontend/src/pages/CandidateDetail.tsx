import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Upload, Sparkles, Workflow, FileText, CalendarClock,
  CheckCircle2, XCircle, Lightbulb, AlertTriangle,
} from "lucide-react";
import { api, errDetail } from "../lib/api";
import { Badge, Button, Card, Field, Modal, PageHeader, Spinner, Textarea, useToast } from "../components/ui";
import { statusMeta, type Candidate, type Interview, type Questionnaire, type ResumeAnalysis } from "../types";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="p-5 mb-4">
      <h3 className="text-sm font-semibold text-slate-700 mb-3">{title}</h3>
      {children}
    </Card>
  );
}

export default function CandidateDetail() {
  const { id } = useParams();
  const cid = Number(id);
  const nav = useNavigate();
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [resumeId, setResumeId] = useState<number | null>(null);

  const [c, setC] = useState<Candidate | null>(null);
  const [resume, setResume] = useState<ResumeAnalysis | null>(null);
  const [qs, setQs] = useState<Questionnaire[]>([]);
  const [ivs, setIvs] = useState<Interview[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [jdOpen, setJdOpen] = useState(false);
  const [jd, setJd] = useState("");

  const loadAll = useCallback(async () => {
    try {
      const cand = (await api.candidates.get(cid)).data;
      setC(cand);
      // 并行拉取简历分析 / 问卷 / 面试，失败不阻塞
      api.resumes.getByCandidate(cid).then((r) => setResume(r.data)).catch(() => {});
      api.questionnaires.byCandidate(cid).then((r) => setQs(r.data)).catch(() => {});
      api.interviews.byCandidate(cid).then((r) => setIvs(r.data)).catch(() => {});
    } catch (e) {
      toast(errDetail(e), "err");
    } finally { setLoading(false); }
  }, [cid]); // eslint-disable-line

  useEffect(() => { loadAll(); }, [loadAll]);

  if (loading) return <Spinner />;
  if (!c) return <p className="text-slate-400">候选人不存在</p>;

  const uploadResume = async (file: File) => {
    setBusy("upload");
    try {
      const { data } = await api.resumes.upload(cid, file);
      setResumeId(data.id);
      toast(`「${file.name}」上传成功，可点击“AI 匹配分析”开始解析`);
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setBusy(""); }
  };

  const runAnalyze = async () => {
    const rid = resumeId ?? resume?.id;
    if (!rid) return;
    if (!jd.trim()) { toast("请先粘贴岗位 JD", "err"); return; }
    setBusy("analyze"); setJdOpen(false);
    try {
      const { data } = await api.resumes.analyze(rid, jd);
      setResume(data);
      toast("AI 分析完成");
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setBusy(""); }
  };


  const autoProcess = async () => {
    if (!confirm("对该候选人执行全自动流程（解析→AI 分析→自动分流）？")) return;
    setBusy("auto");
    try {
      await api.workflow.autoProcess(cid);
      toast("流程已启动");
      setTimeout(loadAll, 5000);
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setBusy(""); }
  };

  const sendQuestionnaire = async () => {
    if (!confirm(`向「${c.name}」发送问卷链接？`)) return;
    setBusy("q");
    try {
      await api.questionnaires.sendLink(cid);
      toast("问卷链接已发送");
      loadAll();
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setBusy(""); }
  };

  const ma = resume?.match_analysis;
  const info = resume?.analysis?.basic_info ?? {};

  return (
    <>
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => nav("/candidates")} className="text-slate-400 hover:text-slate-700"><ArrowLeft size={18} /></button>
        <h1 className="text-xl font-semibold">{c.name}</h1>
        <Badge label={statusMeta(c.status).label} cls={statusMeta(c.status).cls} />
        {c.match_score != null && (
          <span className="text-sm font-semibold tabular-nums">匹配分
            <b className={c.match_score >= 80 ? "text-emerald-600 ml-2" : c.match_score >= 60 ? "text-amber-600 ml-2" : "text-rose-500 ml-2"}>
              {c.match_score.toFixed(1)}
            </b>
          </span>
        )}
        <div className="ml-auto flex gap-2">
          <Button variant="outline" loading={busy === "q"} onClick={sendQuestionnaire}><FileText size={14} /> 发送问卷</Button>
          <Button loading={busy === "auto"} onClick={autoProcess}><Workflow size={14} /> 全自动流程</Button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* 左列 */}
        <div>
          <Section title="基本信息">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 text-sm">
              {[["应聘岗位", c.position], ["电话", c.phone], ["邮箱", c.email], ["工作年限", c.experience_years != null ? `${c.experience_years} 年` : null],
                ["来源", c.source], ["创建时间", new Date(c.created_at).toLocaleString()],
              ].map(([k, v]) => (
                <div key={k as string} className="contents">
                  <dt className="text-slate-400 text-xs pt-0.5">{k}</dt>
                  <dd className="text-slate-700 break-all">{v || "—"}</dd>
                </div>
              ))}
            </dl>
          </Section>

          <Section title="简历文件">
            <input ref={fileRef} type="file" hidden accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg"
              onChange={(e) => e.target.files?.[0] && uploadResume(e.target.files[0])} />
            <Button variant="outline" loading={busy === "upload"} onClick={() => fileRef.current?.click()}>
              <Upload size={14} /> 上传简历（PDF/Word/图片）
            </Button>
            {resume && (
              <p className="mt-2.5 text-xs text-slate-400 truncate">
                当前记录：{resume.original_filename ?? `#${resume.id}`}
                {resume.analyzed_at && ` · 分析于 ${new Date(resume.analyzed_at).toLocaleString()}`}
              </p>
            )}
            <Button variant="outline" className="mt-2 w-full" onClick={() => setJdOpen(true)} disabled={!resume}>
              <Sparkles size={14} /> 对当前简历做 AI 匹配分析
            </Button>
          </Section>

          <Section title={`问卷记录 (${qs.length})`}>
            {qs.length === 0 ? <p className="text-sm text-slate-300">暂无记录</p> : qs.map((q) => (
              <div key={q.id} className="flex items-center justify-between py-1.5 text-sm border-b border-slate-50 last:border-0">
                <span className="text-slate-600 truncate">{q.title}</span>
                <Badge label={q.status === "completed" ? "已完成" : q.status === "sent" ? "已发送" : q.status}
                  cls={q.status === "completed" ? "bg-emerald-50 text-emerald-600" : "bg-purple-50 text-purple-600"} />
              </div>
            ))}
          </Section>

          <Section title={`面试记录 (${ivs.length})`}>
            {ivs.length === 0 ? <p className="text-sm text-slate-300">暂无记录</p> : ivs.map((iv) => (
              <div key={iv.id} className="py-1.5 text-sm border-b border-slate-50 last:border-0">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600">第 {iv.round === "first" ? "一" : iv.round} 轮</span>
                  <Badge label={iv.status} />
                </div>
                {iv.confirmed_start && (
                  <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1">
                    <CalendarClock size={11} /> {new Date(iv.confirmed_start).toLocaleString()}
                    {iv.location && ` · ${iv.location}`}
                  </p>
                )}
              </div>
            ))}
          </Section>
        </div>

        {/* 右侧 AI 分析区 */}
        <div className="col-span-2">
          {!resume ? (
            <Card className="p-5 h-full flex items-center justify-center min-h-64">
              <EmptyHint hasResume={false} />
            </Card>
          ) : !ma && !resume.summary ? (
            <Card className="p-5"><EmptyHint hasResume /></Card>
          ) : (
            <>
              {resume.summary && (
                <Section title="AI 总结">
                  <p className="text-sm leading-7 text-slate-700 whitespace-pre-wrap">{resume.summary}</p>
                </Section>
              )}

              {ma && (
                <>
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <Section title="✅ 优势">
                      <ul className="space-y-2">
                        {ma.strengths.map((s, i) => (
                          <li key={i} className="flex gap-2 text-sm text-slate-700"><CheckCircle2 size={15} className="text-emerald-500 shrink-0 mt-0.5" />{s}</li>
                        ))}
                      </ul>
                    </Section>
                    <Section title="⚠️ 风险点">
                      <ul className="space-y-2">
                        {ma.risks.map((s, i) => (
                          <li key={i} className="flex gap-2 text-sm text-slate-700"><AlertTriangle size={15} className="text-amber-500 shrink-0 mt-0.5" />{s}</li>
                        ))}
                      </ul>
                    </Section>
                  </div>

                  <Section title="💡 推荐面试问题">
                    <ol className="space-y-2 list-decimal list-inside">
                      {ma.recommended_questions.map((q, i) => <li key={i} className="text-sm text-slate-700 leading-6">{q}</li>)}
                    </ol>
                  </Section>
                </>
              )}

              {resume.analysis?.skills?.length ? (
                <Section title="技能标签">
                  <div className="flex flex-wrap gap-2">
                    {resume.analysis.skills.map((s) => (
                      <span key={s} className="rounded-full bg-brand-50 text-brand-600 px-3 py-1 text-xs font-medium">{s}</span>
                    ))}
                  </div>
                </Section>
              ) : null}

              {resume.analysis?.work_experience?.length ? (
                <Section title="工作经历">
                  <div className="space-y-3">
                    {resume.analysis.work_experience.map((w, i) => (
                      <div key={i} className="rounded-xl bg-slate-50 p-3.5 text-sm">
                        <p className="font-medium text-slate-800">{(w as Record<string, string>).company ?? (w as Record<string, string>).title}</p>
                        <p className="text-slate-500 mt-1 leading-6">{Object.entries(w).filter(([k]) => !["company", "title"].includes(k))
                          .map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
                      </div>
                    ))}
                  </div>
                </Section>
              ) : null}

              {Object.keys(info).length > 0 && (
                <Section title="解析出的关键信息">
                  <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                    {Object.entries(info).map(([k, v]) => (
                      <span key={k} className="text-slate-500"><b className="text-slate-700 mr-1.5">{k}</b>{v}</span>
                    ))}
                  </div>
                </Section>
              )}
            </>
          )}
        </div>
      </div>

      {/* JD 输入弹窗 */}
      <Modal open={jdOpen} onClose={() => setJdOpen(false)} title="岗位 JD（用于 AI 匹配分析）">
        <Field label="岗位描述">
          <Textarea rows={8} value={jd} onChange={(e) => setJd(e.target.value)}
            placeholder="粘贴岗位 JD，AI 将据此对候选人简历做多维匹配打分…" />
        </Field>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setJdOpen(false)}>取消</Button>
          <Button onClick={runAnalyze}>开始分析</Button>
        </div>
      </Modal>
    </>
  );
}

function EmptyHint({ hasResume }: { hasResume: boolean }) {
  return (
    <div className="text-center py-10">
      <Lightbulb size={28} className="mx-auto text-slate-200 mb-3" />
      <p className="text-sm text-slate-400 font-medium">{hasResume ? "尚未进行 AI 分析" : "还没有简历文件"}</p>
      <p className="text-xs text-slate-300 mt-1.5 max-w-xs mx-auto leading-5">
        {hasResume
          ? "点击左侧“对当前简历做 AI 匹配分析”，或直接使用顶部“全自动流程”一键完成解析与分流"
          : "先在左侧上传 PDF / Word / 图片简历，系统会自动完成 OCR 与内容提取"}
      </p>
    </div>
  );
}
