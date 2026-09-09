import { useEffect, useMemo, useState } from "react";
import {
  FileBadge2, Plus, Save, Trash2, RotateCcw, Power, Crosshair, Search,
} from "lucide-react";
import { api, errDetail } from "../lib/api";
import {
  Badge, Button, Card, EmptyState, Field, Input, PageHeader,
  Select, Spinner, Textarea, useToast,
} from "../components/ui";
import type { PositionJd, PositionJdMatch } from "../types";
import { JD_CATEGORY_KEYS, jdCategoryLabel } from "../types";


interface FormState {
  position: string;
  aliases: string;
  category: string;
  salary: string;
  responsibilities: string;
  requirements: string;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  position: "",
  aliases: "",
  category: JD_CATEGORY_KEYS[0] ?? "销售",
  salary: "面议",
  responsibilities: "",
  requirements: "",
  is_active: true,
};

export default function PositionJds() {
  const { toast } = useToast();
  const [list, setList] = useState<PositionJd[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | string>("all");
  const [keyword, setKeyword] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // 匹配测试
  const [testPos, setTestPos] = useState("");
  const [match, setMatch] = useState<PositionJdMatch | null>(null);
  const [matchLoading, setMatchLoading] = useState(false);

  const selected = list.find((j) => j.id === selectedId) ?? null;

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.positionJds.list();
      setList(data.items);
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  // 分类下拉 = 内置分类 ∪ 现存行里的自定义分类
  const categoryOptions = useMemo(() => {
    const set = new Set<string>(JD_CATEGORY_KEYS);
    list.forEach((j) => { if (j.category && j.category !== "other") set.add(j.category); });
    return [...set];
  }, [list]);

  const setField = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const openNew = () => {
    setSelectedId(null);
    setIsNew(true);
    setForm(EMPTY_FORM);
    setMatch(null);
  };

  const openRow = (row: PositionJd) => {
    setSelectedId(row.id);
    setIsNew(false);
    setForm({
      position: row.position,
      aliases: row.aliases,
      category: row.category || "other",
      salary: row.salary,
      responsibilities: row.responsibilities,
      requirements: row.requirements,
      is_active: row.is_active,
    });
    setMatch(null);
  };

  const discardEdit = () => {
    if (selectedId != null && selected) openRow(selected);
    else { setSelectedId(null); setIsNew(false); setForm(EMPTY_FORM); }
  };

  const save = async () => {
    if (!form.position.trim()) return toast("请填写岗位名称", "err");
    if (!form.responsibilities.trim() && !form.requirements.trim())
      return toast("请至少填写「岗位职责」或「任职要求」之一", "err");
    setSaving(true);
    try {
      const payload = {
        position: form.position.trim(),
        aliases: form.aliases.trim(),
        category: form.category || "other",
        salary: form.salary.trim() || "面议",
        responsibilities: form.responsibilities,
        requirements: form.requirements,
        is_active: form.is_active,
      };
      if (selectedId != null) {
        await api.positionJds.update(selectedId, payload);
        toast("岗位 JD 已保存");
        await load();
        setSelectedId(selectedId);
      } else {
        const { data } = await api.positionJds.create(payload);
        toast("岗位 JD 已创建");
        setIsNew(false);
        await load();
        setSelectedId(data.id);
      }
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setSaving(false); }
  };

  const toggleActive = async (row: PositionJd) => {
    try {
      await api.positionJds.update(row.id, { is_active: !row.is_active });
      await load();
    } catch (e) { toast(errDetail(e), "err"); }
  };

  const removeJd = async (row: PositionJd) => {
    if (!window.confirm(`确定删除岗位「${row.position}」的 JD？\n删除后简历分析按该岗位将不再自动套用 JD（退回按岗位名分析）。`)) return;
    try {
      await api.positionJds.remove(row.id);
      toast("岗位 JD 已删除");
      if (selectedId === row.id) { setSelectedId(null); setIsNew(false); setForm(EMPTY_FORM); }
      await load();
    } catch (e) { toast(errDetail(e), "err"); }
  };

  const resetJd = async () => {
    if (selectedId == null) return;
    if (!window.confirm(`将「${form.position}」恢复为《在招岗位说明书汇总》里的系统默认 JD？`)) return;
    try {
      await api.positionJds.reset(selectedId);
      toast("已恢复系统内置 JD");
      await load();
      const fresh = list.find((j) => j.id === selectedId);
      if (fresh) openRow(fresh);
    } catch (e) { toast(errDetail(e), "err"); }
  };

  const restoreDefaults = async () => {
    if (!window.confirm("补齐所有缺失的内置岗位 JD？不会覆盖你已经编辑过的记录。")) return;
    try {
      const { data } = await api.positionJds.restoreDefaults();
      toast(`内置岗位 JD 补齐完成：新增 ${data.inserted} 条`);
      await load();
    } catch (e) { toast(errDetail(e), "err"); }
  };

  const runMatch = async () => {
    if (!testPos.trim()) return toast("请输入一个应聘岗位做匹配测试", "err");
    setMatchLoading(true);
    try {
      const { data } = await api.positionJds.match(testPos.trim());
      setMatch(data);
    } catch (e) { toast(errDetail(e), "err"); }
    finally { setMatchLoading(false); }
  };

  // 左栏过滤：分类 + 关键词
  const shown = list.filter((j) => {
    if (filter !== "all" && j.category !== filter) return false;
    const kw = keyword.trim();
    if (kw) {
      const hay = `${j.position} ${j.aliases} ${j.category}`.toLowerCase();
      if (!hay.includes(kw.toLowerCase())) return false;
    }
    return true;
  });

  return (
    <div>
      <PageHeader
        title="岗位 JD 库"
        desc="维护每个在招岗位的标准 JD（岗位职责 + 任职要求）。简历分析 / 全自动流程会自动按候选人「应聘岗位」套用对应 JD 喂给大模型，HR 不再每次手填招聘标准；手填的 JD 仍优先生效"
        actions={
          <>
            <Button variant="outline" onClick={restoreDefaults} title="补齐缺失的内置岗位 JD">
              <RotateCcw size={15} /> 恢复默认
            </Button>
            <Button onClick={openNew}><Plus size={15} /> 新建岗位 JD</Button>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[340px_1fr] items-start">
        {/* ===== 左：岗位列表 ===== */}
        <Card className="p-4">
          <div className="flex flex-wrap gap-1.5 mb-3">
            <button onClick={() => setFilter("all")}
              className={`px-2.5 py-1 rounded-lg text-xs transition-colors ${
                filter === "all" ? "grad-anim text-white shadow-glow-brand"
                  : "bg-slate-100 text-slate-500 hover:bg-slate-200/70"}`}>
              全部
            </button>
            {categoryOptions.map((c) => (
              <button key={c} onClick={() => setFilter(c)}
                className={`px-2.5 py-1 rounded-lg text-xs transition-colors ${
                  filter === c ? "grad-anim text-white shadow-glow-brand"
                    : "bg-slate-100 text-slate-500 hover:bg-slate-200/70"}`}>
                {jdCategoryLabel(c)}
              </button>
            ))}
          </div>

          <div className="relative mb-3">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-300" />
            <Input value={keyword} onChange={(e) => setKeyword(e.target.value)}
              placeholder="搜岗位 / 别名…" className="pl-9" />
          </div>

          {loading ? <Spinner text="加载岗位 JD…" /> : shown.length === 0 ? (
            <EmptyState icon={<FileBadge2 size={28} />} text={list.length === 0 ? "暂无岗位 JD，点击右上角新建" : "没有匹配的岗位 JD"} />
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
                    title={row.is_active ? "停用（该岗位不再自动套用）" : "启用"}
                    onClick={(e) => { e.stopPropagation(); toggleActive(row); }}
                    className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-colors ${
                      row.is_active ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-300"}`}>
                    <Power size={13} />
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-700 truncate">
                      {row.position}
                      {row.is_system && <span className="ml-1.5 align-middle"><Badge label="系统" cls="bg-indigo-50 text-indigo-500" /></span>}
                    </p>
                    <p className="text-[11px] text-slate-400 truncate">
                      {jdCategoryLabel(row.category)}{row.salary ? ` · ${row.salary}` : ""}
                    </p>
                  </div>
                  <span className={`text-[11px] shrink-0 ${row.is_active ? "text-emerald-500" : "text-slate-300"}`}>
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
            <EmptyState icon={<FileBadge2 size={30} />} text="选择左侧岗位开始编辑，或点击「新建岗位 JD」" />
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-slate-700 font-medium">
                  <FileBadge2 size={16} className="text-brand-500" />
                  {isNew ? "新建岗位 JD" : `编辑：${form.position}`}
                </div>
                {selected?.is_system && !isNew && (
                  <Badge label="系统内置" cls="bg-indigo-50 text-indigo-500" />
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="岗位名称">
                  <Input value={form.position} onChange={(e) => setField("position", e.target.value)}
                    placeholder="如：电商运营经理" maxLength={100} />
                </Field>
                <Field label="薪资（仅展示）">
                  <Input value={form.salary} onChange={(e) => setField("salary", e.target.value)}
                    placeholder="如：面议 / 15-25K" maxLength={50} />
                </Field>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="分类">
                  <Select value={form.category} onChange={(e) => setField("category", e.target.value)}>
                    {categoryOptions.map((c) => (
                      <option key={c} value={c}>{jdCategoryLabel(c)}</option>
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
                    <span className="text-sm text-slate-500">{form.is_active ? "启用（分析时自动套用）" : "停用（该岗位不再自动套用）"}</span>
                  </div>
                </Field>
              </div>

              <Field label="匹配别名（顿号分隔，可空）">
                <Input value={form.aliases} onChange={(e) => setField("aliases", e.target.value)}
                  placeholder="如：电商经理，电商运营，坚果电商运营" maxLength={255} />
                <p className="text-[11px] text-slate-400 mt-1">候选人应聘岗位命中「岗位名称」或任一别名即套用本 JD；如「城市经理（安徽）」可写别名「城市经理」兼容不带括号的写法。</p>
              </Field>

              <Field label="岗位职责">
                <Textarea rows={9} value={form.responsibilities} onChange={(e) => setField("responsibilities", e.target.value)}
                  placeholder="逐条粘贴该岗位的岗位职责…" className="text-[13px] leading-6 min-h-[180px] resize-y" />
              </Field>

              <Field label="任职要求">
                <Textarea rows={7} value={form.requirements} onChange={(e) => setField("requirements", e.target.value)}
                  placeholder="逐条粘贴该岗位的任职要求…" className="text-[13px] leading-6 min-h-[140px] resize-y" />
              </Field>

              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Button loading={saving} onClick={save}><Save size={15} /> {selectedId != null ? "保存修改" : "创建岗位 JD"}</Button>
                {!isNew && selected?.is_system && (
                  <Button variant="ghost" onClick={resetJd} title="恢复汇总 docx 的默认 JD"><RotateCcw size={15} /> 恢复默认</Button>
                )}
                {!isNew && selected && (
                  <Button variant="ghost" className="text-rose-500 hover:text-rose-600"
                    onClick={() => removeJd(selected)}><Trash2 size={15} /> 删除</Button>
                )}
                {(isNew || !selected) && (
                  <Button variant="ghost" onClick={discardEdit}>取消</Button>
                )}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* ===== 匹配测试（自动套用预览） ===== */}
      <Card className="p-5 mt-5">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <p className="text-sm font-medium text-slate-700 flex items-center gap-2">
            <Crosshair size={15} className="text-brand-500" />
            匹配测试：输入一个应聘岗位，看看会套用哪份 JD
          </p>
          <span className="text-xs text-slate-400">规则：HR 手填 JD ＞ 岗位 JD 库匹配 ＞ 岗位名兜底</span>
        </div>
        <div className="flex gap-2 max-w-xl">
          <Input value={testPos} onChange={(e) => setTestPos(e.target.value)}
            placeholder="如：电商运营经理 / 城市经理 / 食品研发" maxLength={100}
            onKeyDown={(e) => { if (e.key === "Enter") runMatch(); }} />
          <Button variant="outline" loading={matchLoading} onClick={runMatch}><Crosshair size={15} /> 测试</Button>
        </div>
        {match && (
          <div className={`mt-4 rounded-xl border px-4 py-3 ${
            match.matched ? "border-emerald-200 bg-emerald-50/50" : "border-amber-200 bg-amber-50/50"}`}>
            <p className={`text-sm font-medium ${match.matched ? "text-emerald-700" : "text-amber-700"}`}>
              {match.matched ? (
                <>命中岗位：<b>{match.row?.position}</b>（{jdCategoryLabel(match.row?.category ?? "other")}）</>
              ) : (
                <>未命中任何岗位 JD —— 该岗位分析将退回「按岗位名」的通用分析（可在左侧新建一条 JD）</>
              )}
            </p>
            {match.matched && match.jd && (
              <pre className="mt-2 whitespace-pre-wrap text-[13px] text-slate-700 leading-6 max-h-64 overflow-y-auto rounded-lg bg-white/60 p-3">{match.jd}</pre>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
