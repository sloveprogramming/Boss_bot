import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, Upload, Trash2, FileText, SendHorizonal, MessageSquare, Plus } from "lucide-react";
import { api, errDetail, postSSE } from "../lib/api";
import { Button, Card, Input, PageHeader, useToast } from "../components/ui";
import type { PolicyChatSession } from "../types";

interface DocRow { id: number; title: string; category?: string; filename?: string }
interface ChatMsg { role: "user" | "assistant"; content: string }

const QUICK_QS = ["年假有几天？怎么申请？", "试用期多久？转正标准是什么？", "报销流程是怎样的？", "加班政策是什么？"];

const DEFAULT_WELCOME: ChatMsg = {
  role: "assistant",
  content: "你好！我是企业制度问答助手。上传制度文档后，可以问我任何公司制度相关的问题。",
};

/** 生成稳定会话 id（http 非安全上下文不可用 crypto.randomUUID，故手动生成） */
const genSessionId = () => {
  const rnd = () => Math.random().toString(36).slice(2, 10);
  return `policy_${(rnd() + rnd() + Date.now().toString(36)).slice(0, 12)}`;
};

const toChatMsg = (m: { role: "user" | "assistant"; content: string }): ChatMsg => ({
  role: m.role,
  content: m.content,
});

export default function PolicyAgent() {
  const { toast } = useToast();
  const [docs, setDocs] = useState<DocRow[]>([]);
  const [sessions, setSessions] = useState<PolicyChatSession[]>([]);
  const [activeSid, setActiveSid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<ChatMsg[]>([DEFAULT_WELCOME]);
  const [tab, setTab] = useState<"chat" | "docs">("chat");
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [form, setForm] = useState({ title: "", category: "" });
  const fileRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  const loadDocs = () =>
    api.policyDocs.list().then((r) => setDocs((r.data as { items?: DocRow[] }).items ?? r.data)).catch(() => {});

  // 初始：加载文档库 + 最近一个会话的历史（会话由后端按当前账号隔离）
  useEffect(() => {
    loadDocs();
    api.policyChat
      .sessions()
      .then((r) => {
        const list = r.data.sessions ?? [];
        setSessions(list);
        if (list.length) {
          const first = list[0].session_id;
          setActiveSid(first);
          return api.policyChat.history(first);
        }
        return null;
      })
      .then((h) => {
        if (!h) return;
        const arr = (h.data.messages ?? []).map(toChatMsg);
        setMsgs(arr.length ? arr : [DEFAULT_WELCOME]);
      })
      .catch(() => {});
  }, []); // eslint-disable-line

  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight }); }, [msgs]);

  /** 拉取服务端会话列表（返回列表供调用方继续处理） */
  const refreshSessions = async (): Promise<PolicyChatSession[]> => {
    try {
      const r = await api.policyChat.sessions();
      const list = r.data.sessions ?? [];
      setSessions(list);
      return list;
    } catch {
      return sessions;
    }
  };

  /** 打开某个会话：从服务端拉取该会话消息 */
  const openSession = async (sid: string) => {
    if (streaming || sid === activeSid) return;
    setActiveSid(sid);
    try {
      const h = await api.policyChat.history(sid);
      const arr = (h.data.messages ?? []).map(toChatMsg);
      setMsgs(arr.length ? arr : [DEFAULT_WELCOME]);
    } catch {
      setMsgs([DEFAULT_WELCOME]);
    }
  };

  /** 新会话：本地先生成 session_id，等第一条消息落库后出现在列表 */
  const newChat = () => {
    if (streaming) return;
    setActiveSid(genSessionId());
    setMsgs([DEFAULT_WELCOME]);
  };

  const send = async (text?: string) => {
    const q = (text ?? input).trim();
    if (!q || streaming) return;
    const sid = activeSid ?? genSessionId();
    if (!activeSid) setActiveSid(sid);
    setInput("");
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setStreaming(true);

    // 用户问题先落库（账号隔离），失败不阻塞问答
    try { await api.policyChat.addMessage({ session_id: sid, role: "user", content: q }); }
    catch { /* ignore */ }

    let full = "";
    try {
      await postSSE(api.rag.stream, { message: q, session_id: sid }, (t) => {
        full = t;
        setMsgs((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { role: "assistant", content: t };
          return copy;
        });
      });
    } catch (e) {
      toast(errDetail(e), "err");
      setMsgs((m) => {
        const copy = [...m];
        copy[copy.length - 1].content ||= "抱歉，回答生成失败，请确认 RAG 服务 (:18003) 已启动。";
        return copy;
      });
    } finally {
      if (full.trim()) {
        try { await api.policyChat.addMessage({ session_id: sid, role: "assistant", content: full }); }
        catch { /* ignore */ }
      }
      setStreaming(false);
      await refreshSessions(); // 更新列表预览/排序
    }
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

  const removeSession = async (sid: string) => {
    if (streaming) return;
    if (!confirm("删除该会话？服务端该会话的全部问答记录会一并清除。")) return;
    try {
      await api.policyChat.removeSession(sid);
      toast("会话已删除");
      const list = await refreshSessions();
      if (sid === activeSid) {
        if (list.length) await openSession(list[0].session_id);
        else newChat();
      }
    } catch (e) { toast(errDetail(e), "err"); }
  };

  return (
    <>
      <PageHeader
        title="制度问答"
        desc="RAG 知识库问答：混合检索 + 重排 + 流式回答（会话按账号隔离、服务端持久化）"
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setUploadOpen(true)}><Upload size={14} /> 上传制度文档</Button>
          </div>
        }
      />

      <div className="grid grid-cols-5 gap-4">
        {/* 左侧：会话 / 文档库 双 Tab */}
        <Card className="flex flex-col h-[calc(100vh-220px)] overflow-hidden">
          <div className="flex border-b border-slate-100 text-xs shrink-0">
            <button
              onClick={() => setTab("chat")}
              className={`flex-1 py-2.5 flex items-center justify-center gap-1.5 transition-colors ${
                tab === "chat" ? "text-brand-600 border-b-2 border-brand-500 font-medium" : "text-slate-400 hover:text-slate-600"
              }`}
            >
              <MessageSquare size={13} /> 会话
            </button>
            <button
              onClick={() => setTab("docs")}
              className={`flex-1 py-2.5 flex items-center justify-center gap-1.5 transition-colors ${
                tab === "docs" ? "text-brand-600 border-b-2 border-brand-500 font-medium" : "text-slate-400 hover:text-slate-600"
              }`}
            >
              <FileText size={13} /> 文档库{docs.length > 0 ? ` (${docs.length})` : ""}
            </button>
          </div>

          {tab === "chat" ? (
            <>
              <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
                {sessions.length === 0 && (
                  <p className="text-xs text-slate-300 text-center pt-8 leading-6">
                    还没有历史会话。<br />点下方「＋ 新会话」开始提问。
                  </p>
                )}
                {sessions.map((s) => {
                  const active = s.session_id === activeSid;
                  return (
                    <div
                      key={s.session_id}
                      onClick={() => openSession(s.session_id)}
                      className={`group cursor-pointer rounded-lg px-2.5 py-2 flex gap-2 transition-colors ${
                        active ? "bg-brand-50" : "hover:bg-slate-50"
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className={`text-xs truncate ${active ? "text-brand-700 font-semibold" : "text-slate-700 font-medium"}`}>
                          {s.title || "新会话"}
                        </div>
                        <div className="text-[11px] text-slate-400 truncate mt-0.5 leading-4">{s.last_preview}</div>
                      </div>
                      <button
                        title="删除会话"
                        disabled={streaming}
                        onClick={(e) => { e.stopPropagation(); removeSession(s.session_id); }}
                        className="self-center opacity-0 group-hover:opacity-100 text-slate-300 hover:text-rose-500 transition-opacity disabled:opacity-0"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  );
                })}
              </div>
              <div className="p-2 border-t border-slate-100 shrink-0">
                <Button variant="ghost" className="w-full justify-center text-xs" onClick={newChat} disabled={streaming}>
                  <Plus size={14} /> 新会话
                </Button>
              </div>
            </>
          ) : (
            <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
              {docs.length === 0 && (
                <p className="text-xs text-slate-300 text-center pt-8 leading-6">
                  暂无文档。<br />点右上角「上传制度文档」入库后即可提问。
                </p>
              )}
              {docs.map((d) => (
                <div key={d.id} className="group flex items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-slate-50">
                  <FileText size={13} className="text-slate-300 shrink-0" />
                  <span className="text-xs text-slate-600 truncate flex-1" title={d.title}>{d.title}</span>
                  <button onClick={() => removeDoc(d)} className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-rose-500 transition-opacity">
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* 对话区 */}
        <Card className="col-span-4 flex flex-col h-[calc(100vh-220px)] overflow-hidden">
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
