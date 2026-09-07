import { useState } from "react";
import { Briefcase, Copy, RefreshCw, Sparkles } from "lucide-react";
import { getToken } from "../lib/api";
import { Button, Card, Input, PageHeader, Textarea, useToast } from "../components/ui";

const EDU_OPTIONS = ["不限", "大专", "本科", "硕士", "博士"];

/** 主后端 SSE 读取（/api 直连 :18000，不走 postSSE 的 /rag-api 映射） */
async function postBackendSSE(
  url: string,
  body: Record<string, unknown>,
  onDelta: (full: string) => void,
): Promise<string> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) throw new Error(`请求失败 (${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "", full = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const s = line.trim();
      if (!s.startsWith("data:")) continue;
      const payload = s.slice(5).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        const j = JSON.parse(payload);
        if (j.error) throw new Error(j.error);
        if (j.text) { full += j.text; onDelta(full); }
      } catch (e) {
        if (e instanceof SyntaxError) continue; // 心跳/非 JSON 忽略
        throw e;
      }
    }
  }
  return full;
}

export default function JdGenerator() {
  const { toast } = useToast();
  const [form, setForm] = useState({ position: "", salary: "", education: "本科", extra: "" });
  const [jd, setJd] = useState("");
  const [streaming, setStreaming] = useState(false);

  const setField = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const generate = async () => {
    if (!form.position.trim() || streaming) {
      if (!form.position.trim()) toast("请先填写岗位名称", "err");
      return;
    }
    setJd("");
    setStreaming(true);
    try {
      const full = await postBackendSSE("/api/jd/generate/stream", form, (t) => setJd(t));
      if (!full.trim()) toast("未生成内容，请重试", "err");
    } catch (e) {
      toast(e instanceof Error ? e.message : "生成失败", "err");
    } finally {
      setStreaming(false);
    }
  };

  const copy = async () => {
    if (!jd.trim()) return;
    try { await navigator.clipboard.writeText(jd); toast("已复制到剪贴板"); }
    catch { toast("复制失败，请手动选择复制", "err"); }
  };

  return (
    <div>
      <PageHeader
        title="JD 生成"
        desc="输入岗位、薪资与学历要求，AI 自动生成结构化岗位描述（已内置就业合规检查）"
      />

      <div className="grid gap-5 lg:grid-cols-[360px_1fr] items-start">
        {/* ===== 左侧：输入表单 ===== */}
        <Card className="p-5 space-y-4">
          <div className="flex items-center gap-2 text-slate-700 font-medium">
            <Briefcase size={16} className="text-brand-500" />
            岗位信息
          </div>

          <div>
            <label className="text-xs text-slate-500 mb-1 block">岗位名称 *</label>
            <Input placeholder="如：Python 后端工程师" value={form.position} onChange={setField("position")} />
          </div>

          <div>
            <label className="text-xs text-slate-500 mb-1 block">薪资范围</label>
            <Input placeholder="如：20-35K·14薪" value={form.salary} onChange={setField("salary")} />
          </div>

          <div>
            <label className="text-xs text-slate-500 mb-1 block">学历要求</label>
            <select
              value={form.education}
              onChange={setField("education")}
              className="w-full rounded-xl border border-slate-200/90 bg-white/80 px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            >
              {EDU_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>

          <div>
            <label className="text-xs text-slate-500 mb-1 block">补充说明（可选）</label>
            <Textarea
              rows={3}
              placeholder="团队亮点 / 技术栈 / 福利等，让 JD 更有区分度"
              value={form.extra}
              onChange={setField("extra")}
            />
          </div>

          <Button className="w-full" loading={streaming} onClick={generate} disabled={!form.position.trim()}>
            <Sparkles size={15} className="mr-1.5" />
            {streaming ? "生成中..." : "生成 JD"}
          </Button>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            生成结果为草稿建议，发布前请人工确认内容合规与准确性。
          </p>
        </Card>

        {/* ===== 右侧：生成结果（可编辑） ===== */}
        <Card className="p-5 flex flex-col min-h-[520px]">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 text-slate-700 font-medium">
              <Briefcase size={16} className="text-brand-500" />
              岗位职责（Markdown，可编辑）
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={generate} disabled={!form.position.trim() || streaming}>
                <RefreshCw size={14} className="mr-1" /> 重新生成
              </Button>
              <Button variant="ghost" onClick={copy} disabled={!jd.trim()}>
                <Copy size={14} className="mr-1" /> 复制
              </Button>
            </div>
          </div>

          {streaming && !jd ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
              <Sparkles size={18} className="mr-2 animate-pulse text-brand-400" />
              AI 正在撰写 JD...
            </div>
          ) : (
            <Textarea
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              rows={22}
              placeholder={'生成结果将显示在这里，例如：\n\n## 岗位职责\n- 负责核心服务的设计与开发...\n\n## 任职要求\n- 本科及以上学历...'}
              className="flex-1 min-h-[440px] leading-relaxed font-mono text-[13px] resize-none"
            />
          )}
        </Card>
      </div>
    </div>
  );
}
