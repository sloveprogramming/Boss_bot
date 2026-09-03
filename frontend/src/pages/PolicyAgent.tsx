import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, Upload, Trash2, FileText, SendHorizonal } from "lucide-react";
import { api, errDetail, postSSE } from "../lib/api";
import { Button, Card, Input, PageHeader, useToast } from "../components/ui";

interface DocRow { id: number; title: string; category?: string; filename?: string }
interface ChatMsg { role: "user" | "assistant"; content: string }

const QUICK_QS = ["年假有几天？怎么申请？", "试用期多久？转正标准是什么？", "报销流程是怎样的？", "加班政策是什么？"];

export default function PolicyAgent() {
  const { toast } = useToast();
  const [docs, setDocs] = useState<DocRow[]>([]);
  const [msgs, setMsgs] = useState<ChatMsg[]>([
    { role: "assistant", content: "你好！我是企业制度问答助手。上传制度文档后，可以问我任何公司制度相关的问题。" },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [form, setForm] = useState({ title: "", category: "" });
  const fileRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  const loadDocs = () =>
    api.policyDocs.list().then((r) => setDocs((r.data as { items?: DocRow[] }).items ?? r.data)).catch(() => {});

  useEffect(() => { loadDocs(); }, []); // eslint-disable-line
  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight }); }, [msgs]);

  const send = async (text?: string) => {
    const q = (text ?? input).trim();
    if (!q || streaming) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setStreaming(true);
    try {
      await postSSE(api.ragChatStream, { message: q }, (full) =>
        setMsgs((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { role: "assistant", content: full };
          return copy;
        }),
      );
    } catch (e) {
      toast(errDetail(e), "err");
      setMsgs((m) => {
        const copy = [...m];
        copy[copy.length - 1].content ||= "抱歉，回答生成失败，请确认 RAG 服务 (:18003) 已启动。";
        return copy;
      });
    } finally { setStreaming(false); }
  };

  const upload = async (file: File) => {
    try {
      await api.policyDocs.upload(form.title || file.name.replace(/\.[^.]+$/, ""), form.category || "通用", file);
      toast("文档上传成功");
      setUploadOpen(false); setForm({ title: "", category: "" });
      loadDocs();
    } catch (e) { toast(errDetail(e), "err"); }
  };

  const removeDoc = async (d: DocRow) => {
    if (!confirm(`删除文档「${d.title}」？`)) return;
    try { await api.policyDocs.remove(d.id); toast("已删除"); loadDocs(); }
    catch (e) { toast(errDetail(e), "err"); }
  };

  return (
    <>
      <PageHeader
        title="制度问答"
        desc="RAG 知识库问答：混合检索 + 重排 + 流式回答（独立 RAG 服务 :18003）"
        actions={<Button variant="outline" onClick={() => setUploadOpen(true)}><Upload size={14} /> 上传制度文档</Button>}
      />

      <div className="grid grid-cols-4 gap-4">
        {/* 文档列表 */}
        <Card className="p-4 h-[calc(100vh-220px)] overflow-y-auto">
          <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
            <FileText size={14} /> 已入库文档 ({docs.length})
          </h3>
          {docs.length === 0 ? (
            <p className="text-xs text-slate-300 leading-5">暂无文档。<br />先点右上角「上传制度文档」。</p>
          ) : docs.map((d) => (
            <div key={d.id} className="group flex items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-slate-50 mb-0.5">
              <FileText size={13} className="text-slate-300 shrink-0" />
              <span className="text-xs text-slate-600 truncate flex-1" title={d.title}>{d.title}</span>
              <button onClick={() => removeDoc(d)} className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-rose-500 transition-opacity">
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </Card>

        {/* 对话区 */}
        <Card className="col-span-3 flex flex-col h-[calc(100vh-220px)] overflow-hidden">
          <div ref={bodyRef} className="flex-1 overflow-y-auto p-6 space-y-4">
            {msgs.map((m, i) => (
              <div key={i} className={`flex gap-3 max-w-[80%] ${m.role === "user" ? "ml-auto flex-row-reverse" : ""}`}>
                {m.role === "assistant" && (
                  <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shrink-0">
                    <Bot size={16} className="text-white" />
                  </div>
                )}
                <div className={`rounded-2xl px-4 py-3 text-sm leading-7 whitespace-pre-wrap ${
                  m.role === "user" ? "bg-brand-600 text-white rounded-br-md" : "bg-slate-100 text-slate-800 rounded-bl-md md-body"
                }`}>
                  {m.role === "assistant" && !m.content && streaming ? (
                    <span className="inline-flex gap-1 animate-pulse"><b>.</b><b>.</b><b>.</b></span>
                  ) : m.role === "assistant" ? (
                    <ReactMarkdown>{m.content}</ReactMarkdown>
                  ) : m.content}
                </div>
              </div>
            ))}
          </div>

          {/* 快捷问题 */}
          {msgs.length <= 1 && (
            <div className="px-6 pb-2 flex flex-wrap gap-2">
              {QUICK_QS.map((q) => (
                <button key={q} onClick={() => send(q)}
                  className="text-xs rounded-full border border-slate-200 px-3 py-1.5 text-slate-500 hover:border-brand-400 hover:text-brand-600 transition-colors">
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* 输入框 */}
          <div className="border-t border-slate-100 p-4 flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
              placeholder="输入你的制度问题，Enter 发送…"
              disabled={streaming}
            />
            <Button onClick={() => send()} disabled={!input.trim()} loading={streaming}>
              {!streaming && <SendHorizonal size={15} />}
            </Button>
          </div>
        </Card>
      </div>

      {/* 上传弹窗 */}
      {uploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-950/45 backdrop-blur-sm animate-[fadeIn_.2s_ease-out]" onClick={() => setUploadOpen(false)} />
          <div className="relative bg-white/90 backdrop-blur-2xl border border-white/80 rounded-2xl shadow-pop w-full max-w-md p-6 animate-[modalIn_.3s_cubic-bezier(.22,.8,.3,1)]">
            <h3 className="font-semibold mb-4">上传制度文档</h3>
            <label className="block mb-3">
              <span className="block text-xs font-medium text-slate-500 mb-1.5">标题</span>
              <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="如：员工手册 2024" />
            </label>
            <label className="block mb-4">
              <span className="block text-xs font-medium text-slate-500 mb-1.5">分类</span>
              <Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="如：考勤 / 薪酬 / 报销" />
            </label>
            <input ref={fileRef} type="file" hidden accept=".pdf,.doc,.docx,.txt,.md"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            <Button className="w-full" onClick={() => fileRef.current?.click()}>
              <Upload size={14} /> 选择文件并上传
            </Button>
            <p className="text-xs text-slate-400 mt-3 text-center">支持 PDF / Word / TXT / Markdown</p>
          </div>
        </div>
      )}
    </>
  );
}
