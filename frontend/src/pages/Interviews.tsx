// 面试排期管理页面
import { useState, useEffect } from 'react'
import { Calendar, Clock, MapPin, Video, User, RefreshCw, Check } from 'lucide-react'
import { candidatesApi, interviewsApi } from '../lib/api'

export default function Interviews() {
  const [candidates, setCandidates] = useState<any[]>([])
  const [selectedCand, setSelectedCand] = useState<number | null>(null)
  const [interviews, setInterviews] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [dateRange, setDateRange] = useState({ start: '', end: '' })

  useEffect(() => {
    const today = new Date()
    const end = new Date(today); end.setDate(end.getDate() + 7)
    setDateRange({
      start: today.toISOString().slice(0, 10),
      end: end.toISOString().slice(0, 10),
    })
    candidatesApi.list({ page_size: 100 }).then(d => setCandidates(d.items))
      .finally(() => setLoading(false))
  }, [])

  const handleGenerateSlots = async () => {
    if (!selectedCand || !dateRange.start || !dateRange.end) return
    try {
      const result = await interviewsApi.generateSlots({
        candidate_id: selectedCand,
        date_range_start: dateRange.start,
        date_range_end: dateRange.end,
      })
      alert(`已生成 ${result.proposed_slots.length} 个可选时间段`)
      loadInterviews()
    } catch (e: any) {
      alert('生成失败: ' + e.message)
    }
  }

  const loadInterviews = async () => {
    const all: any[] = []
    for (const c of candidates) {
      try {
        const ivs = await interviewsApi.getByCandidate(c.id)
        all.push(...(Array.isArray(ivs) ? ivs : [ivs]))
      } catch {}
    }
    setInterviews(all.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))
  }

  const handleConfirmSlot = async (interviewId: number, slot: any) => {
    try {
      await interviewsApi.confirmSlot({ interview_id: interviewId, selected_slot: slot })
      alert('时间已确认')
      loadInterviews()
    } catch (e: any) {
      alert('确认失败: ' + e.message)
    }
  }

  const statusLabels: Record<string, string> = {
    pending: '待排期', awaiting_confirm: '待确认', confirmed: '已确认',
    completed: '已完成', cancelled: '已取消', no_show: '未出席',
  }

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div>
        <h2 className="text-xl font-bold text-gray-800">面试排期管理</h2>
        <p className="text-sm text-gray-400 mt-0.5">智能生成可选时间段，一键确认面试时间</p>
      </div>

      {/* 排期表单 */}
      <div className="glass-card p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <div className="w-1 h-4 rounded-full bg-teal-500" />
          生成面试时间段
        </h3>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="text-xs text-gray-500 mb-1.5 block font-medium">候选人</label>
            <select value={selectedCand ?? ''} onChange={e => setSelectedCand(Number(e.target.value) || null)}
                    className="input-field w-full">
              <option value="">请选择候选人...</option>
              {candidates.filter(c => c.status === 'q_done' || c.status === 'scheduled').map(c => (
                <option key={c.id} value={c.id}>{c.name} - {c.position}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block font-medium">开始日期</label>
            <input type="date" value={dateRange.start}
                   onChange={e => setDateRange({ ...dateRange, start: e.target.value })}
                   className="input-field" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block font-medium">结束日期</label>
            <input type="date" value={dateRange.end}
                   onChange={e => setDateRange({ ...dateRange, end: e.target.value })}
                   className="input-field" />
          </div>
          <button onClick={handleGenerateSlots} disabled={!selectedCand}
                  className="btn-primary flex items-center gap-2 bg-gradient-to-r from-teal-500 to-emerald-500 hover:shadow-teal-500/25">
            <Calendar className="w-4 h-4" /> 生成时间段
          </button>
          <button onClick={loadInterviews} className="btn-secondary flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 面试记录 */}
      <div className="glass-card overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100/80">
          <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <div className="w-1 h-4 rounded-full bg-blue-500" />
            面试记录
          </h3>
        </div>
        {interviews.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-gray-100 flex items-center justify-center">
              <Calendar className="w-6 h-6 text-gray-300" />
            </div>
            <p className="text-gray-400 text-sm">暂无面试记录</p>
          </div>
        ) : (
          interviews.map((iv: any) => {
            const cand = candidates.find(c => c.id === iv.candidate_id)
            return (
              <div key={iv.id} className="p-5 border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-xs font-bold">
                      {cand?.name?.[0] || '?'}
                    </div>
                    <div>
                      <h4 className="font-medium text-gray-800">{cand?.name || `#${iv.candidate_id}`}</h4>
                      <p className="text-xs text-gray-400">{cand?.position} · {iv.round}面试</p>
                    </div>
                  </div>
                  <span className={`status-badge ${iv.status}`}>{statusLabels[iv.status] || iv.status}</span>
                </div>

                {iv.confirmed_start && (
                  <div className="p-3.5 rounded-xl bg-gradient-to-r from-emerald-50 to-green-50 border border-emerald-100/60 mb-3">
                    <div className="flex items-center gap-2 text-sm">
                      <Calendar className="w-4 h-4 text-emerald-500" />
                      <span className="font-medium text-gray-700">
                        {new Date(iv.confirmed_start).toLocaleString('zh-CN')}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      {iv.location && (
                        <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {iv.location}</span>
                      )}
                      {iv.meeting_link && (
                        <a href={iv.meeting_link} className="flex items-center gap-1 text-blue-500 hover:underline">
                          <Video className="w-3 h-3" /> 会议链接
                        </a>
                      )}
                    </div>
                  </div>
                )}

                {iv.proposed_slots?.length > 0 && !iv.confirmed_start && (
                  <div>
                    <p className="text-xs text-gray-400 mb-2">可选时间段（点击确认）：</p>
                    <div className="flex flex-wrap gap-2">
                      {iv.proposed_slots.map((s: any, i: number) => (
                        <button key={i} onClick={() => handleConfirmSlot(iv.id, s)}
                                className="flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-xl text-xs font-medium text-gray-600 hover:border-teal-300 hover:text-teal-600 hover:bg-teal-50 transition-all">
                          <Check className="w-3 h-3" />
                          {s.date} {s.start_time}-{s.end_time}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {iv.feedback && (
                  <div className="mt-3 p-3.5 rounded-xl bg-gray-50 border border-gray-100">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm">{'⭐'.repeat(iv.feedback.rating || 0)}</span>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-md ${
                        iv.feedback.decision === 'pass' ? 'bg-emerald-50 text-emerald-600' :
                        iv.feedback.decision === 'reject' ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-600'
                      }`}>
                        决策: {iv.feedback.decision}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600">{iv.feedback.detail}</p>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
