import { useEffect, useMemo, useState } from "react";
import {
  Mail, Plus, Wand2, Eye, Save, Trash2, RotateCcw, Power,
} from "lucide-react";
import { api, errDetail } from "../lib/api";
import {
  Badge, Button, Card, EmptyState, Field, Input, Modal, PageHeader,
  Select, Spinner, Textarea, useToast,
} from "../components/ui";
import type {
  EmailTemplate, TemplateCategory, TemplatePreviewResult,
} from "../types";
import { TEMPLATE_CATEGORY_META, templateCategoryLabel } from "../types";


/** 模板可用占位符说明（点击可把 {变量} 插入正文末尾） */
const VAR_HINTS: { name: string; label: string }[] = [
  { name: "candidate_name",  label: "候选人姓名" },
  { name: "position",        label: "应聘岗位" },
  { name: "survey_link",     label: "问卷链接" },
  { name: "deadline",        label: "截止时间" },
  { name: "reminder_count",  label: "提醒次数" },
  { name: "proposed_slots",  label: "可选时间段" },
  { name: "selection_link",  label: "选时间链接" },
  { name: "interview_time",  label: "面试时间" },
  { name: "location_or_link", label: "地点或会议链接" },
];

const CATEGORY_KEYS = Object.keys(TEMPLATE_CATEGORY_META) as TemplateCategory[];

function extractVars(text: string): string[] {
  const out: string[] = [];
  const re = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) { if (!out.includes(m[1])) out.push(m[1]); }
  return out;
}

interface FormState {
  code: string; name: string; category: TemplateCategory;
  subject: string; body: string; is_active: boolean;
}
const EMPTY_FORM: FormState = {
  code: "", name: "", category: "questionnaire",
  subject: "", body: "", is_active: true,
};

export default function EmailTemplates() {
  const { toast } = useToast();
  const [list, setList] = useState<EmailTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | TemplateCategory>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // 预览
  const [pvOpen, setPvOpen] = useState(false);
  const [pvName, setPvName] = useState("");
  const [pvPos, setPvPos] = useState("");
  const [pvLoading, setPvLoading] = useState(false);
  const [pvResult, setPvResult] = useState<TemplatePreviewResult | null>(null);

  // AI 生成
  const [aiOpen, setAiOpen] = useState(false);
  const [aiFocus, setAiFocus] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  const selected = list.find((t) => t.id === selectedId) ?? null;

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.templates.list();
      setList(data.items);
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  // 用当前 subject+body 抽取已使用占位符，与未使用列表
  const usedVars = useMemo(
    () => extractVars(`${form.subject}\n${form.body}`),
    [form.subject, form.body],
  );
  const availableVars = VAR_HINTS.filter((v) => !usedVars.includes(v.name));

  const setField = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const openNew = () => {
    setSelectedId(null);
    setIsNew(true);
    setForm(EMPTY_FORM);
  };

  const openRow = (row: EmailTemplate) => {
    setSelectedId(row.id);
    setIsNew(false);
    setForm({
      code: row.code, name: row.name, category: row.category,
      subject: row.subject, body: row.body, is_active: row.is_active,
    });
  };

  const discardEdit = () => {
    if (selectedId != null && selected) openRow(selected);
    else { setSelectedId(null); setIsNew(false); setForm(EMPTY_FORM); }
  };

  const save = async () => {
    if (isNew && !form.code.trim()) return toast("请填写模板编码（如 questionnaire_invite）", "err");
    if (!form.name.trim()) return toast("请填写模板显示名", "err");
    if (!form.subject.trim()) return toast("请填写邮件主题", "err");
    if (!form.body.trim()) return toast("请填写邮件正文", "err");
    setSaving(true);
    try {
      if (selectedId != null) {
        await api.templates.update(selectedId, {
          name: form.name.trim(), category: form.category,
          subject: form.subject.trim(), body: form.body, is_active: form.is_active,
        });
        toast("模板已保存");
        await load();
        setSelectedId(selectedId);
      } else {
        const { data } = await api.templates.create({
          code: form.code.trim(), name: form.name.trim(), category: form.category,
          subject: form.subject.trim(), body: form.body, is_active: form.is_active,
        });
        toast("模板已创建");
        setIsNew(false);
        await load();
        setSelectedId(data.id);
      }
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setSaving(false); }
  };

  const toggleActive = async (row: EmailTemplate) => {
    try {
      await api.templates.update(row.id, { is_active: !row.is_active });
      await load();
    } catch (e) { toast(errDetail(e), "err"); }
  };

  const removeTemplate = async (row: EmailTemplate) => {
    if (!window.confirm(`确定删除模板「${row.name}」？\n删除后该场景的自动发送将回退为内置默认文案。`)) return;
    try {
      await api.templates.remove(row.id);
      toast("模板已删除");
      if (selectedId === row.id) { setSelectedId(null); setIsNew(false); setForm(EMPTY_FORM); }
      await load();
    } catch (e) { toast(errDetail(e), "err"); }
  };

  const resetTemplate = async () => {
    if (selectedId == null) return;
    if (!window.confirm(`将「${form.name}」恢复为系统内置默认文案？`)) return;
    try {
      await api.templates.reset(selectedId);
      toast("已恢复内置默认");
      await load();
      const fresh = list.find((t) => t.id === selectedId);
      if (fresh) openRow(fresh);
    } catch (e) { toast(errDetail(e), "err"); }
  };

  const restoreDefaults = async () => {
    if (!window.confirm("补齐所有缺失的内置模板？不会覆盖你已经编辑过的模板。")) return;
    try {
      const { data } = await api.templates.restoreDefaults();
      toast(`内置模板补齐完成：新增 ${data.inserted} 条`);
      await load();
    } catch (e) { toast(errDetail(e), "err"); }
  };

  const insertVar = (name: string) =>
    setForm((f) => ({ ...f, body: f.body ? `${f.body.replace(/\s*$/, "")}\n{${name}}` : `{${name}}` }));

  // ── 预览 ───────────────────────────────────────────────
  const openPreview = () => {
    if (!form.subject.trim() || !form.body.trim())
      return toast("请先填写主题与正文再预览", "err");
    setPvResult(null);
    setPvOpen(true);
  };
  const runPreview = async () => {
    setPvLoading(true);
    try {
      const { data } = await api.templates.renderPreview({
        subject: form.subject, body: form.body,
        candidate_name: pvName.trim() || undefined,
        position: pvPos.trim() || undefined,
      });
      setPvResult(data);
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setPvLoading(false); }
  };
  useEffect(() => { if (pvOpen) runPreview(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [pvOpen]);

  // ── AI 生成 ─────────────────────────────────────────────
  const openAi = () => {
    if (isNew && !form.code.trim())
      return toast("请先在右侧填写「模板编码」再让 AI 生成（生成后直接套用该编码）", "err");
    setAiFocus("");
    setAiOpen(true);
  };
  const runGenerate = async () => {
    if (!aiFocus.trim()) return toast("请填写用途说明", "err");
    setAiLoading(true);
    try {
      const { data } = await api.templates.generate({
        focus: aiFocus.trim(),
        code: isNew && form.code.trim() ? form.code.trim() : (selected?.code ?? undefined),
      });
      setForm((f) => ({
        ...f,
        name: data.draft.name || f.name,
        category: data.draft.category,
        subject: data.draft.subject,
        body: data.draft.body,
      }));
      setAiOpen(false);
      if (data.unexpected_variables.length > 0)
        toast(`草稿已生成，但含白名单外占位符 ${data.unexpected_variables.join("、")}，请人工修正`, "err");
      else toast("草稿已生成，请检查后保存");
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setAiLoading(false); }
  };

  // 左栏分组展示
  const shown = list.filter((t) => filter === "all" || t.category === filter);

  return (
    <div>
      <PageHeader
        title="邮件模板"
        desc="提前配置问卷、面试、Offer 等自动发送邮件文案；支持人工编写或 AI 生成草稿，删除/停用某模板后自动发送会回退到内置默认"
        actions={
          <>
            <Button variant="outline" onClick={restoreDefaults} title="补齐缺失的内置模板">
              <RotateCcw size={15} /> 恢复默认
            </Button>
            <Button onClick={openNew}><Plus size={15} /> 新建模板</Button>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[340px_1fr] items-start">
        {/* ===== 左：模板列表 ===== */}
        <Card className="p-4">
          <div className="flex flex-wrap gap-1.5 mb-3">
            {(["all", ...CATEGORY_KEYS] as const).map((k) => (
              <button key={k} onClick={() => setFilter(k)}
                className={`px-2.5 py-1 rounded-lg text-xs transition-colors ${
                  filter === k ? "grad-anim text-white shadow-glow-brand"
                    : "bg-slate-100 text-slate-500 hover:bg-slate-200/70"}`}>
                {k === "all" ? "全部" : templateCategoryLabel(k)}
              </button>
            ))}
          </div>

          {loading ? <Spinner text="加载模板…" /> : shown.length === 0 ? (
            <EmptyState icon={<Mail size={28} />} text={list.length === 0 ? "暂无模板，点击右上角新建" : "该分类暂无模板"} />
          ) : (
            <div className="space-y-1.5 max-h-[62vh] overflow-y-auto pr-1">
              {shown.map((row) => (
                <div key={row.id}
                  className={`group flex items-center gap-2 rounded-xl border px-3 py-2.5 cursor-pointer transition-all duration-150 ${
                    selectedId === row.id
                      ? "border-brand-400 bg-brand-50/70 shadow-sm"
                      : "border-slate-100 bg-white/60 hover:border-brand-200 hover:shadow-sm"
                  }`}
                  onClick={() => openRow(row)}>
                  <button
                    title={row.is_active ? "停用（回退内置默认）" : "启用"}
                    onClick={(e) => { e.stopPropagation(); toggleActive(row); }}
                    className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-colors ${
                      row.is_active ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-300"}`}>
                    <Power size={13} />
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-700 truncate">
                      {row.name}
                      {row.is_system && <span className="ml-1.5 align-middle"><Badge label="系统" cls="bg-indigo-50 text-indigo-500" /></span>}
                    </p>
                    <p className="text-[11px] text-slate-400 truncate font-mono">{row.code}</p>
                  </div>
                  <span className={`text-[11px] ${row.is_active ? "text-emerald-500" : "text-slate-300"}`}>
                    {row.is_active ? "生效中" : "已停用"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* ===== 右：编辑器 ===== */}
        <Card className="p-5">
          {selectedId == null && !isNew ? (
            <EmptyState icon={<Mail size={30} />} text="选择左侧模板开始编辑，或点击「新建模板」" />
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-slate-700 font-medium">
                  <Mail size={16} className="text-brand-500" />
                  {isNew ? "新建模板" : `编辑模板：${form.name}`}
                </div>
                {selected?.is_system && !isNew && (
                  <Badge label="系统内置" cls="bg-indigo-50 text-indigo-500" />
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="模板编码（code）">
                  {isNew ? (
                    <Input value={form.code} onChange={(e) => setField("code", e.target.value)}
                      placeholder="如 questionnaire_invite" maxLength={64} className="font-mono" />
                  ) : (
                    <Input value={form.code} disabled className="font-mono bg-slate-50 text-slate-400" />
                  )}
                </Field>
                <Field label="模板显示名">
                  <Input value={form.name} onChange={(e) => setField("name", e.target.value)}
                    placeholder="如：问卷邀请" maxLength={100} />
                </Field>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="分类">
                  <Select value={form.category} onChange={(e) => setField("category", e.target.value as TemplateCategory)}>
                    {CATEGORY_KEYS.map((c) => (
                      <option key={c} value={c}>{templateCategoryLabel(c)}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="状态">
                  <div className="flex items-center gap-2 h-10 px-1">
                    <button onClick={() => setField("is_active", !form.is_active)}
                      className={`w-11 h-6 rounded-full transition-colors relative ${
                        form.is_active ? "bg-emerald-400" : "bg-slate-300"}`}>
                      <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all ${
                        form.is_active ? "left-[22px]" : "left-0.5"}`} />
                    </button>
                    <span className="text-sm text-slate-500">{form.is_active ? "启用（自动发送使用此文案）" : "停用（自动发送回退内置默认）"}</span>
                  </div>
                </Field>
              </div>

              <Field label="邮件主题（Subject）">
                <Input value={form.subject} onChange={(e) => setField("subject", e.target.value)}
                  placeholder="如：{candidate_name}，欢迎应聘 {position} 岗位" maxLength={255} />
              </Field>

              <Field label="邮件正文（Body）">
                <Textarea rows={12} value={form.body} onChange={(e) => setField("body", e.target.value)}
                  placeholder={`{candidate_name}，您好！\n\n感谢您应聘我司岗位……`}
                  className="font-mono text-[13px] leading-6 min-h-[220px] resize-y" />
              </Field>

              {/* 占位符 */}
              <div className="rounded-xl border border-slate-100 bg-slate-50/60 px-3 py-2.5 space-y-2">
                <p className="text-[11px] font-medium text-slate-400">可用占位符（点击插入正文，发送时自动替换）</p>
                <div className="flex flex-wrap gap-1.5">
                  {VAR_HINTS.map((v) => (
                    <button key={v.name} onClick={() => insertVar(v.name)}
                      title={v.label}
                      className={`px-2 py-0.5 rounded-md font-mono text-[11px] border transition-colors ${
                        usedVars.includes(v.name)
                          ? "border-emerald-200 bg-emerald-50 text-emerald-600"
                          : "border-slate-200 bg-white text-slate-500 hover:border-brand-300 hover:text-brand-600"}`}>
                      {"{" + v.name + "}"}
                    </button>
                  ))}
                </div>
                {availableVars.length === 0 && (
                  <p className="text-[11px] text-slate-400">所有常用占位符均已使用 ✓</p>
                )}
              </div>

              {/* 操作按钮 */}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Button loading={saving} onClick={save}><Save size={15} /> {selectedId != null ? "保存修改" : "创建模板"}</Button>
                <Button variant="outline" onClick={openAi} disabled={aiLoading}><Wand2 size={15} /> AI 生成草稿</Button>
                <Button variant="outline" onClick={openPreview}><Eye size={15} /> 预览</Button>
                {!isNew && selected?.is_system && (
                  <Button variant="ghost" onClick={resetTemplate} title="恢复内置默认文案"><RotateCcw size={15} /> 恢复默认</Button>
                )}
                {!isNew && selected && (
                  <Button variant="ghost" className="text-rose-500 hover:text-rose-600"
                    onClick={() => removeTemplate(selected)}><Trash2 size={15} /> 删除</Button>
                )}
                {(isNew || !selected) && (
                  <Button variant="ghost" onClick={discardEdit}>取消</Button>
                )}
              </div>
              {isNew && (
                <p className="text-xs text-slate-400 leading-5">
                  提示：使用内置编码（如 questionnaire_invite / interview_invite / offer / rejection）可覆盖对应自动发送文案；
                  填写新编码则仅用于留档，不会被自动发送调用。
                </p>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* ===== AI 生成草稿弹窗 ===== */}
      <Modal open={aiOpen} onClose={() => setAiOpen(false)} title="AI 生成邮件模板草稿">
        <Field label="用途说明">
          <Textarea rows={4} value={aiFocus} onChange={(e) => setAiFocus(e.target.value)}
            placeholder={`例如：给通过初面的候选人发送二面邀约，请对方在给出的时间段中选择并告知地点\n\n将作为：${isNew && form.code ? form.code : selected?.name ?? ""}`} />
        </Field>
        <p className="text-xs text-slate-400 leading-5 -mt-1 mb-4">
          AI 将结合公司档案与合规红线生成草稿，<b>不会直接保存</b>；生成后请人工检查、微调再点保存。
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setAiOpen(false)}>取消</Button>
          <Button loading={aiLoading} onClick={runGenerate}><Wand2 size={15} /> 生成草稿</Button>
        </div>
      </Modal>

      {/* ===== 预览弹窗 ===== */}
      <Modal open={pvOpen} onClose={() => setPvOpen(false)} title="模板预览（样例值渲染）" width="max-w-2xl">
        <div className="grid gap-3 sm:grid-cols-2 mb-4">
          <Field label="候选人称呼（样例）">
            <Input value={pvName} onChange={(e) => setPvName(e.target.value)} placeholder="留空用「候选人」" maxLength={50} />
          </Field>
          <Field label="岗位名称（样例）">
            <Input value={pvPos} onChange={(e) => setPvPos(e.target.value)} placeholder="留空用「应聘岗位」" maxLength={100} />
          </Field>
        </div>
        {pvResult && (
          <div className="space-y-3">
            <div className="rounded-xl border border-slate-100 bg-slate-50/70 px-4 py-3">
              <p className="text-xs text-slate-400 mb-1">主题</p>
              <p className="text-sm font-medium text-slate-800">{pvResult.subject}</p>
            </div>
            <div className="rounded-xl border border-slate-100 bg-white px-4 py-3 whitespace-pre-wrap text-sm text-slate-700 leading-6">
              {pvResult.body}
            </div>
            {pvResult.remaining_placeholders.length > 0 && (
              <p className="text-xs text-amber-600">
                未识别的占位符（发送时会原样保留，请核对）：{pvResult.remaining_placeholders.join("、")}
              </p>
            )}
          </div>
        )}
        <div className="flex justify-end gap-2 mt-5">
          <Button loading={pvLoading} variant="outline" onClick={runPreview}><Eye size={15} /> 重新渲染</Button>
          <Button variant="ghost" onClick={() => setPvOpen(false)}>关闭</Button>
        </div>
      </Modal>
    </div>
  );
}
