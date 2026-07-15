import { useState, useEffect } from 'react'
import { Send, FileText, ExternalLink } from 'lucide-react'
import { questionnairesApi, candidatesApi } from '../lib/api'
import { showToast } from '../components/Toast'

export default function Questionnaires() {
  const [candidates, setCandidates] = useState<any[]>([])
  const [sentRecords, setSentRecords] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState<number | null>(null)

  const QUESTIONNAIRE_LINK = 'https://www.qingsuyun.com/h5/251261/18081878897/'

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const c = await candidatesApi.list({ page_size: 100 })
      setCandidates(c.items)

      // 加载所有候选人的问卷记录
      const all: any[] = []
      for (const cand of c.items) {
        try {
          const qs = await questionnairesApi.getByCandidate(cand.id)
          all.push(...(Array.isArray(qs) ? qs : []))
        } catch { }
      }
      setSentRecords(all.sort((a, b) =>
        new Date(b.sent_at || b.created_at).getTime() - new Date(a.sent_at || a.created_at).getTime()
      ))
    } catch (e: any) {
      showToast('error', '加载失败', e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSend = async (candidateId: number) => {
    setSending(candidateId)
    try {
      await questionnairesApi.sendLink(candidateId)
      showToast('success', '问卷链接已发送', '候选人将收到邮件通知')
      loadData()
    } catch (e: any) {
      showToast('error', '发送失败', e.message)
    } finally {
      setSending(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-800">发送问卷</h2>
          <p className="text-sm text-gray-400 mt-0.5">向候选人发送轻速云问卷链接</p>
        </div>
        <a href={QUESTIONNAIRE_LINK} target="_blank" rel="noopener noreferrer"
          className="btn-secondary flex items-center gap-2 text-sm">
          <ExternalLink className="w-4 h-4" /> 打开问卷
        </a>
      </div>

      {/* 快速发送 */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <Send className="w-4 h-4 text-indigo-500" /> 快速发送
        </h3>
        <div className="flex flex-wrap gap-2">
          {candidates
            .filter(c => c.status !== 'hired' && c.status !== 'rejected')
            .map(cand => (
              <button key={cand.id} onClick={() => handleSend(cand.id)} disabled={sending === cand.id}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all
                  bg-gradient-to-br from-indigo-50 to-purple-50 text-indigo-700
                  hover:shadow-md hover:shadow-indigo-500/10 border border-indigo-100/60
                  disabled:opacity-50 disabled:cursor-not-allowed">
                <Send className="w-3.5 h-3.5" />
                {sending === cand.id ? '发送中...' : cand.name}
                <span className="text-[11px] text-gray-400 ml-1">{cand.position}</span>
              </button>
            ))}
          {candidates.filter(c => c.status !== 'hired' && c.status !== 'rejected').length === 0 && (
            <p className="text-sm text-gray-400 py-2">暂无待发送的候选人</p>
          )}
        </div>
      </div>

      {/* 已发送记录 */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <FileText className="w-4 h-4 text-gray-400" /> 发送记录
        </h3>
        <div className="space-y-2">
          {sentRecords.map((q: any) => {
            const cand = candidates.find(c => c.id === q.candidate_id)
            return (
              <div key={q.id} className="glass-card p-4 flex items-center justify-between">
                <div>
                  <span className="font-medium text-gray-800">{cand?.name || `#${q.candidate_id}`}</span>
                  <span className="text-gray-400 mx-2">·</span>
                  <span className="text-sm text-gray-500">{cand?.position || '-'}</span>
                  <span className="text-gray-300 mx-2">·</span>
                  <span className="text-xs text-gray-400">{q.sent_at?.slice(0, 10) || '-'}</span>
                </div>
                <span className={`status-badge ${q.status}`}>
                  {q.status === 'sent' ? '已发送' : q.status}
                </span>
              </div>
            )
          })}
          {sentRecords.length === 0 && !loading && (
            <div className="text-center py-12 text-gray-400">暂无发送记录</div>
          )}
        </div>
      </div>
    </div>
  )
}
