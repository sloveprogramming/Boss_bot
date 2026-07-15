// 企业规章制度问答Agent页面 — RAG聊天式知识库
import { useState, useEffect, useRef } from 'react'
import { Send, Upload, Trash2, Bot, User, FileText, Sparkles, X } from 'lucide-react'
import { policyApi } from '../lib/api'

export default function PolicyAgent() {
  const [messages, setMessages] = useState<Array<{ role: string; content: string; confidence?: string; cited_sources?: any[] }>>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [documents, setDocuments] = useState<any[]>([])
  const [showDocs, setShowDocs] = useState(false)
  const [docForm, setDocForm] = useState({ title: '', category: '' })
  const [uploading, setUploading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    policyApi.documents.list().then(setDocuments).catch(() => {})
  }, [])

  const handleSend = async () => {
    if (!input.trim() || streaming) return
    const msg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setStreaming(true)

    // 先添加一个空的 assistant 消息，用于逐字填充
    const streamingIndex = messages.length + 1
    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

    try {
      await policyApi.chatStream(
        { message: msg, session_id: sessionId || undefined },
        (text) => {
          setMessages(prev => {
            const updated = [...prev]
            const last = updated[streamingIndex]
            if (last && last.role === 'assistant') {
              updated[streamingIndex] = { ...last, content: last.content + text }
            }
            return updated
          })
        },
        (eventType, payload) => {
          if (eventType === 'done' && payload.result?.session_id && !sessionId) {
            setSessionId(payload.result.session_id)
          }
          if (eventType === 'sources' && payload.sources) {
            setMessages(prev => {
              const updated = [...prev]
              const last = updated[streamingIndex]
              if (last && last.role === 'assistant') {
                updated[streamingIndex] = { ...last, cited_sources: payload.sources }
              }
              return updated
            })
          }
        }
      )
    } catch (e: any) {
      setMessages(prev => {
        const updated = [...prev]
        if (updated[streamingIndex]) {
          updated[streamingIndex] = { role: 'assistant', content: `请求失败: ${e.message}` }
        }
        return updated
      })
    } finally {
      setStreaming(false)
    }
  }

  const handleUploadDoc = async (file: File) => {
    if (!docForm.title) { alert('请输入文档标题'); return }
    setUploading(true)
    try {
      const result = await policyApi.documents.upload(docForm.title, docForm.category, file)
      alert(`文档 "${result.title}" 上传并索引成功`)
      const docs = await policyApi.documents.list()
      setDocuments(docs)
    } catch (e: any) {
      alert('上传失败: ' + e.message)
    } finally {
      setUploading(false)
    }
  }

  const handleDeleteDoc = async (docId: number) => {
    try {
      await policyApi.documents.delete(docId)
      setDocuments(documents.filter(d => d.id !== docId))
    } catch (e: any) {
      alert('删除失败: ' + e.message)
    }
  }

  return (
    <div className="flex gap-6 h-[calc(100vh-10rem)]">
      {/* 聊天区 */}
      <div className="flex-1 flex flex-col glass-card overflow-hidden">
        {/* 聊天头部 */}
        <div className="px-6 py-4 border-b border-gray-100/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-purple-500/25">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-800 text-sm">制度问答 Agent</h3>
              <p className="text-xs text-gray-400">基于 RAG 的企业知识库助手</p>
            </div>
          </div>
          <button onClick={() => setShowDocs(!showDocs)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    showDocs ? 'bg-violet-50 text-violet-600' : 'text-gray-400 hover:text-violet-600 hover:bg-violet-50'
                  }`}>
            <FileText className="w-3.5 h-3.5" /> 文档库
          </button>
        </div>

        {/* 消息列表 */}
        <div className="flex-1 overflow-auto p-6 space-y-5 bg-gradient-to-b from-white to-gray-50/50">
          {messages.length === 0 && (
            <div className="text-center py-16">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-violet-100 to-purple-100 flex items-center justify-center">
                <Bot className="w-8 h-8 text-purple-500" />
              </div>
              <p className="text-gray-700 font-medium mb-1">您好！我是企业规章制度助手</p>
              <p className="text-sm text-gray-400 mb-6">您可以问我关于公司政策、制度规定等问题</p>
              <div className="flex flex-wrap justify-center gap-2">
                {['年假有多少天？', '加班怎么算工资？', '晋升需要什么条件？', '社保公积金怎么交？'].map(q => (
                  <button key={q} onClick={() => setInput(q)}
                          className="px-4 py-2 bg-white rounded-full text-xs text-gray-600 border border-gray-200 hover:border-violet-300 hover:text-violet-600 hover:bg-violet-50 transition-all">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
              {m.role === 'assistant' ? (
                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center flex-shrink-0 shadow-sm">
                  <Bot className="w-4 h-4 text-white" />
                </div>
              ) : (
                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-blue-600 flex items-center justify-center flex-shrink-0 shadow-sm">
                  <User className="w-4 h-4 text-white" />
                </div>
              )}
              <div className={`max-w-[75%] ${m.role === 'user' ? 'items-end' : ''}`}>
                <div className={`p-3.5 rounded-2xl text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-gradient-to-br from-indigo-500 to-blue-600 text-white rounded-tr-lg'
                    : 'bg-white border border-gray-100 shadow-sm rounded-tl-lg text-gray-700'
                }`}>
                  {m.content}
                </div>
                {m.role === 'assistant' && (
                  <div className="mt-1.5 space-y-1 pl-1">
                    {m.confidence && (
                      <div className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full ${
                          m.confidence === 'high' ? 'bg-emerald-400' :
                          m.confidence === 'medium' ? 'bg-amber-400' : 'bg-red-400'
                        }`} />
                        <span className={`text-[11px] ${
                          m.confidence === 'high' ? 'text-emerald-600' :
                          m.confidence === 'medium' ? 'text-amber-600' : 'text-red-500'
                        }`}>
                          置信度: {m.confidence === 'high' ? '高' : m.confidence === 'medium' ? '中' : '低'}
                        </span>
                      </div>
                    )}
                    {m.cited_sources?.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {m.cited_sources.map((s: any, j: number) => (
                          <span key={j} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-gray-100 text-[11px] text-gray-500">
                            <FileText className="w-3 h-3" /> {s.title}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {streaming && messages[messages.length - 1]?.content === '' && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-sm">
                <Bot className="w-4 h-4 text-white" />
              </div>
              <div className="p-3.5 bg-white border border-gray-100 shadow-sm rounded-2xl rounded-tl-lg">
                <div className="flex gap-1.5 py-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-violet-300 animate-pulse-dot" />
                  <div className="w-1.5 h-1.5 rounded-full bg-violet-300 animate-pulse-dot" />
                  <div className="w-1.5 h-1.5 rounded-full bg-violet-300 animate-pulse-dot" />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* 输入区 */}
        <div className="p-4 border-t border-gray-100/80 bg-white/50 backdrop-blur">
          <div className="flex gap-2">
            <input type="text" value={input} onChange={e => setInput(e.target.value)}
                   placeholder="输入关于公司制度的问题，按 Enter 发送..."
                   onKeyDown={e => e.key === 'Enter' && handleSend()}
                   className="input-field flex-1" />
            <button onClick={handleSend} disabled={!input.trim() || streaming}
                    className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-violet-500 to-purple-600 text-white disabled:opacity-50 hover:shadow-lg hover:shadow-purple-500/25 transition-all active:scale-95">
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* 文档库侧栏 */}
      {showDocs && (
        <div className="w-80 glass-card p-5 overflow-auto flex-shrink-0">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-100 to-purple-100 flex items-center justify-center">
                <FileText className="w-3.5 h-3.5 text-purple-500" />
              </div>
              <h3 className="text-sm font-semibold text-gray-700">制度文档库</h3>
            </div>
            <button onClick={() => setShowDocs(false)} className="p-1 rounded-lg hover:bg-gray-100">
              <X className="w-3.5 h-3.5 text-gray-400" />
            </button>
          </div>

          {/* 上传区域 */}
          <div className="p-4 rounded-xl bg-gradient-to-br from-violet-50 to-purple-50 mb-4 border border-violet-100/60">
            <p className="text-xs font-medium text-gray-600 mb-3">上传新文档</p>
            <input type="text" placeholder="文档标题（必填）" value={docForm.title}
                   onChange={e => setDocForm({ ...docForm, title: e.target.value })}
                   className="input-field w-full mb-2 text-xs" />
            <input type="text" placeholder="分类（如：员工手册）" value={docForm.category}
                   onChange={e => setDocForm({ ...docForm, category: e.target.value })}
                   className="input-field w-full mb-3 text-xs" />
            <label className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-xs font-medium cursor-pointer transition-all border-2 border-dashed ${
              uploading ? 'border-violet-300 bg-white text-violet-500' : 'border-violet-200 hover:border-violet-400 text-gray-500 hover:text-violet-600'
            }`}>
              <Upload className="w-3.5 h-3.5" />
              {uploading ? '上传中...' : '选择文件 (PDF/Word/TXT)'}
              <input type="file" className="hidden" accept=".pdf,.docx,.txt"
                     onChange={e => { const f = e.target.files?.[0]; if (f) handleUploadDoc(f) }} />
            </label>
          </div>

          {/* 文档列表 */}
          <div className="space-y-2">
            {documents.map(doc => (
              <div key={doc.id} className="flex items-center justify-between p-3 rounded-xl hover:bg-gray-50 transition-colors group">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-700 truncate">{doc.title}</p>
                  <p className="text-[11px] text-gray-400">{doc.category || '未分类'} · {doc.chunk_count || 0} 块</p>
                </div>
                <button onClick={() => handleDeleteDoc(doc.id)}
                        className="p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {documents.length === 0 && (
              <p className="text-xs text-gray-400 text-center py-6">暂无文档，请上传企业制度文件</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
