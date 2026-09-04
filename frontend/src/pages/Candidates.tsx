import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search, Trash2, ChevronLeft, ChevronRight, Upload, FileText, X } from "lucide-react";
import { api, errDetail } from "../lib/api";
import { Badge, Button, Card, EmptyState, Field, Input, Modal, PageHeader, Select, Spinner, Textarea, useToast } from "../components/ui";
import { STATUS_META, statusMeta, type Candidate } from "../types";

export default function Candidates() {
  const nav = useNavigate();
  const { toast } = useToast();

  const [list, setList] = useState<Candidate[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ name: "", position: "", phone: "", email: "", source: "manual" });
  const [saving, setSaving] = useState(false);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewMeta, setPreviewMeta] = useState<{ experience_years?: number | null; skills: string[] }>({ experience_years: null, skills: [] });
  const [jd, setJd] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const pageSize = 20;

  const load = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const { data } = await api.candidates.list({
        page: p, page_size: pageSize,
        search: search || undefined,
        status: statusFilter || undefined,
      });
      setList(data.items); setTotal(data.total); setPage(p);
    } catch (e) {
      toast(errDetail(e), "err");
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter]); // eslint-disable-line

  useEffect(() => { load(1); /* eslint-disable-next-line */ }, [statusFilter]);

  const resetCreateModal = () => {
    setCreateOpen(false);
    setForm({ name: "", position: "", phone: "", email: "", source: "manual" });
    setResumeFile(null);
    setPreviewMeta({ experience_years: null, skills: [] });
    setJd("");
    if (fileRef.current) fileRef.current.value = "";
  };

  const onPickResume = async (f: File) => {
    setPreviewBusy(true);
    setResumeFile(null);
    setPreviewMeta({ experience_years: null, skills: [] });
    try {
      const { data } = await api.resumes.preview(f);
      setForm((prev) => ({
        ...prev,
        name: data.name || prev.name,
        phone: data.phone || prev.phone,
        email: data.email || prev.email,
        position: data.suggested_position || prev.position,
      }));
      setResumeFile(f);
      setPreviewMeta({ experience_years: data.experience_years ?? null, skills: data.skills || [] });
      toast(`已识别简历（${data.name || "未识别到姓名"}），请核对后点击「识别建档」`);
    } catch (e) {
      toast(errDetail(e), "err");
    } finally {
      setPreviewBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const create = async () => {
    if (!form.name.trim() || !form.position.trim()) { toast("姓名和应聘岗位为必填", "err"); return; }
    setSaving(true);
    try {
      if (resumeFile) {
        // 有简历：一步建档（建候选人 + 挂简历 + 自动 AI 分析）
        const { data } = await api.resumes.quickAdd({
          file: resumeFile,
          ...form,
          phone: form.phone || undefined,
          email: form.email || undefined,
          experience_years: previewMeta.experience_years ?? null,
          job_description: jd,
        });
        resetCreateModal();
        if (data.warning) {
          toast(`候选人「${data.candidate_name}」已建档，但 ${data.warning}`, "err");
        } else {
          toast(`候选人「${data.candidate_name}」创建成功（简历已自动分析）`);
        }
        nav(`/candidates/${data.candidate_id}`);
      } else {
        const { data } = await api.candidates.create({
          ...form,
          phone: form.phone || null,
          email: form.email || null,
          tags: [],
        });
        resetCreateModal();
        toast(`候选人「${data.name}」创建成功`);
        nav(`/candidates/${data.id}`);
      }
    } catch (e) {
      toast(errDetail(e), "err");
    } finally { setSaving(false); }
  };

  const remove = async (c: Candidate, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`确定删除候选人「${c.name}」？此操作不可恢复`)) return;
    try {
      await api.candidates.remove(c.id);
      toast("已删除");
      load(page);
    } catch (err) { toast(errDetail(err), "err"); }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <>
      <PageHeader
        title="候选人"
        desc={`共 ${total} 位候选人`}
        actions={<Button onClick={() => setCreateOpen(true)}><Plus size={15} /> 新建候选人</Button>}
      />

      {/* 工具栏 */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1 max-w-md">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input placeholder="搜索姓名 / 邮箱…" value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load(1)}
            className="!pl-9" />
        </div>
        {/* ui.tsx inputCls 自带 w-full，定宽类会被 CSS 顺序覆盖 → 外层定宽包裹 */}
        <div className="w-44 shrink-0">
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">全部状态</option>
            {Object.entries(STATUS_META).map(([k, m]) => (
              <option key={k} value={k}>{m.label}</option>
            ))}
          </Select>
        </div>
        <Button variant="outline" onClick={() => load(1)}>查询</Button>
      </div>

      <Card>
        {loading ? <Spinner /> : list.length === 0 ? (
          <EmptyState text="没有匹配的候选人，试试调整筛选条件或新建一位" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                <th className="px-5 py-3 font-medium">姓名</th>
                <th className="px-5 py-3 font-medium">应聘岗位</th>
                <th className="px-5 py-3 font-medium">状态</th>
                <th className="px-5 py-3 font-medium">匹配分</th>
                <th className="px-5 py-3 font-medium">联系方式</th>
                <th className="px-5 py-3 font-medium">创建时间</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => {
                const m = statusMeta(c.status);
                const score = c.match_score;
                return (
                  <tr key={c.id}
                    onClick={() => nav(`/candidates/${c.id}`)}
                    className="border-b border-slate-50 last:border-0 hover:bg-slate-50/70 cursor-pointer transition-colors">
                    <td className="px-5 py-3.5">
                      <span className="font-medium text-slate-800">{c.name}</span>
                      <span className="ml-2 text-xs text-slate-300">#{c.id}</span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-600">{c.position}</td>
                    <td className="px-5 py-3.5"><Badge label={m.label} cls={m.cls} /></td>
                    <td className="px-5 py-3.5">
                      {score != null ? (
                        <span className={`tabular-nums font-semibold ${
                          score >= 80 ? "text-emerald-600" : score >= 60 ? "text-amber-600" : "text-rose-500"
                        }`}>{score.toFixed(1)}</span>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-5 py-3.5 text-slate-500">{c.phone || c.email || "—"}</td>
                    <td className="px-5 py-3.5 text-slate-400 tabular-nums">{new Date(c.created_at).toLocaleDateString()}</td>
                    <td className="px-5 py-3.5 text-right">
                      <button onClick={(e) => remove(c, e)} title="删除"
                        className="text-slate-300 hover:text-rose-500 transition-colors p-1.5 rounded-lg hover:bg-rose-50">
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {/* 分页 */}
        {!loading && total > pageSize && (
          <div className="flex items-center justify-between px-5 py-3.5 border-t border-slate-100">
            <p className="text-xs text-slate-400">第 {page} / {totalPages} 页</p>
            <div className="flex gap-2">
              <Button variant="outline" disabled={page <= 1} onClick={() => load(page - 1)}><ChevronLeft size={14} /> 上一页</Button>
              <Button variant="outline" disabled={page >= totalPages} onClick={() => load(page + 1)}>下一页 <ChevronRight size={14} /></Button>
            </div>
          </div>
        )}
      </Card>

      {/* 新建候选人 — 居中大表单卡片 */}
      <Modal open={createOpen} onClose={resetCreateModal} title="新建候选人" width="max-w-2xl">
        <p className="text-sm text-slate-500 mb-4 -mt-1">可直接手动录入；或上传简历自动识别基本信息并一键建档（含 AI 分析）。</p>

        {/* 上传简历自动识别 */}
        <div className={`mb-5 rounded-xl border border-dashed px-4 py-3.5 ${
          resumeFile ? "border-emerald-300 bg-emerald-50/40" : "border-slate-300 bg-slate-50/60"
        }`}>
          <input ref={fileRef} type="file" hidden accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg"
            onChange={(e) => e.target.files?.[0] && onPickResume(e.target.files[0])} />
          {previewBusy ? (
            <div className="flex items-center gap-2 text-sm text-slate-500"><Spinner /> 正在识别简历基本信息…</div>
          ) : resumeFile ? (
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <FileText size={15} className="text-emerald-600 shrink-0" />
                  <span className="truncate">{resumeFile.name}</span>
                  <span className="text-xs font-normal text-emerald-600 shrink-0">已识别 ✓</span>
                </div>
                {previewMeta.skills.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {previewMeta.skills.map((s, i) => (
                      <span key={i} className="text-xs bg-white border border-slate-200 text-slate-600 rounded-md px-2 py-0.5">{s}</span>
                    ))}
                  </div>
                )}
              </div>
              <button onClick={() => { setResumeFile(null); setPreviewMeta({ experience_years: null, skills: [] }); }}
                title="移除简历" className="text-slate-400 hover:text-rose-500 transition-colors p-1 shrink-0">
                <X size={15} />
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm text-slate-500">选择候选人简历，自动识别姓名 / 电话 / 邮箱 / 应聘岗位</div>
              <Button variant="outline" className="shrink-0" onClick={() => fileRef.current?.click()}><Upload size={14} /> 选择简历文件</Button>
            </div>
          )}
          {resumeFile && <p className="text-xs text-slate-400 mt-2">识别结果已自动填入下方表单，可直接修改后一键建档</p>}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5">
          <Field label="姓名 *"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="候选人姓名" autoFocus /></Field>
          <Field label="应聘岗位 *"><Input value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} placeholder="如：高级后端工程师" /></Field>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5">
          <Field label="电话"><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="手机号 / 座机" /></Field>
          <Field label="邮箱"><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="name@example.com" /></Field>
        </div>
        <Field label="来源">
          <Select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>
            <option value="manual">手动录入</option>
            <option value="boss">BOSS 直聘</option>
            <option value="linkedin">LinkedIn</option>
            <option value="referral">内推</option>
          </Select>
        </Field>
        {resumeFile && (
          <Field label="岗位描述（可选，用于 AI 匹配度分析）">
            <Textarea value={jd} onChange={(e) => setJd(e.target.value)} rows={3}
              placeholder="粘贴该岗位的职责与要求，AI 将据此评估候选人与岗位的匹配度；留空则按通用岗位分析" />
          </Field>
        )}
        <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-slate-100">
          <Button variant="ghost" onClick={resetCreateModal}>取消</Button>
          <Button loading={saving} onClick={create}>
            <Plus size={15} /> {resumeFile ? "识别建档" : "创建候选人"}
          </Button>
        </div>
      </Modal>
    </>
  );
}
