import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, ArrowRight, RefreshCw, Zap } from 'lucide-react'
import { workflowApi, candidatesApi } from '../lib/api'

const stageConfig = [
  { key: 'new', label: '新候选人', color: 'from-blue-500 to-cyan-400', dot: 'bg-blue-500' },
  { key: 'analyzed', label: '已分析', color: 'from-purple-500 to-pink-400', dot: 'bg-purple-500' },
  { key: 'talent_pool', label: '人才池', color: 'from-amber-500 to-orange-400', dot: 'bg-amber-500' },
  { key: 'q_sent', label: '问卷已发', color: 'from-yellow-500 to-amber-400', dot: 'bg-yellow-500' },
  { key: 'q_done', label: '问卷完成', color: 'from-indigo-500 to-blue-400', dot: 'bg-indigo-500' },
  { key: 'scheduled', label: '已排期', color: 'from-teal-500 to-emerald-400', dot: 'bg-teal-500' },
  { key: 'interviewed', label: '已面试', color: 'from-cyan-500 to-sky-400', dot: 'bg-cyan-500' },
  { key: 'hired', label: '已录用', color: 'from-emerald-500 to-green-400', dot: 'bg-emerald-500' },
]

export default function Pipeline() {
  const [pipeline, setPipeline] = useState<any>(null)
  const [candidates, setCandidates] = useState<any[]>([])
  const [processing, setProcessing] = useState<number | null>(null)
  const navigate = useNavigate()

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    const [p, c] = await Promise.all([
      workflowApi.pipeline(),
      candidatesApi.list({ page_size: 100 }).then(d => d.items),
    ])
    setPipeline(p)
    setCandidates(c)
  }

  const handleAutoProcess = async (candidateId: number) => {
    setProcessing(candidateId)
    try {
      const result = await workflowApi.autoProcess(candidateId)
      alert(`${result.action}: ${result.message}`)
      loadData()
    } catch (e: any) {
      alert('自动处理失败: ' + e.message)
    } finally {
      setProcessing(null)
    }
  }

  const grouped = candidates.reduce((acc: any, c: any) => {
    const found = stageConfig.find(s => s.key === c.status)
    const stage = found ? c.status : 'other'
    if (!acc[stage]) acc[stage] = []
    acc[stage].push(c)
    return acc
  }, {} as Record<string, any[]>)

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-800">招聘流程管道</h2>
          <p className="text-sm text-gray-400 mt-0.5">拖拽式看板，一目了然的招聘进度</p>
        </div>
        <button onClick={loadData} className="btn-secondary flex items-center gap-2">
          <RefreshCw className="w-4 h-4" /> 刷新
        </button>
      </div>

      {/* 看板 */}
      <div className="flex gap-4 overflow-x-auto pb-4 snap-x snap-mandatory">
        {stageConfig.map((stage, idx) => {
          const items = grouped[stage.key] || []
          const count = pipeline?.status_counts?.[stage.key] || 0
          return (
            <div key={stage.key} className="flex-shrink-0 w-72 snap-start">
              <div className="glass-card overflow-hidden">
                {/* 阶段头 */}
                <div className={`px-4 py-3 bg-gradient-to-r ${stage.color} bg-opacity-10`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${stage.dot} ring-2 ring-white`} />
                      <span className="text-sm font-semibold text-gray-700">{stage.label}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-medium text-gray-500">{count}</span>
                      {idx < stageConfig.length - 1 && (
                        <ArrowRight className="w-3 h-3 text-gray-300" />
                      )}
                    </div>
                  </div>
                </div>

                {/* 卡片列表 */}
                <div className="p-3 space-y-2 max-h-[520px] overflow-auto">
                  {items.map((c: any) => (
                    <div key={c.id}
                         onClick={() => navigate(`/candidates/${c.id}`)}
                         className="p-3 rounded-xl bg-white border border-gray-100 hover:border-indigo-200 hover:shadow-md hover:shadow-indigo-500/5 cursor-pointer transition-all duration-200 group">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0">
                            {c.name?.[0] || '?'}
                          </div>
                          <div>
                            <p className="text-sm font-medium text-gray-800 group-hover:text-indigo-600 transition-colors">{c.name}</p>
                            <p className="text-[11px] text-gray-400">{c.position}</p>
                          </div>
                        </div>
                        {c.match_score != null && (
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${
                            c.match_score >= 70
                              ? 'bg-emerald-50 text-emerald-600'
                              : c.match_score >= 50
                              ? 'bg-amber-50 text-amber-600'
                              : 'bg-red-50 text-red-600'
                          }`}>
                            {c.match_score}
                          </span>
                        )}
                      </div>

                      {/* 操作按钮 */}
                      <div onClick={e => e.stopPropagation()}>
                        {c.status !== 'hired' && c.status !== 'rejected' && (
                          <button onClick={() => handleAutoProcess(c.id)} disabled={processing === c.id}
                                  className="flex items-center justify-center gap-1.5 w-full px-3 py-1.5 text-xs font-medium rounded-lg transition-all duration-200
                                    bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-600
                                    hover:from-indigo-100 hover:to-purple-100
                                    disabled:opacity-50 disabled:cursor-not-allowed">
                            {processing === c.id ? (
                              <><RefreshCw className="w-3 h-3 animate-spin" /> 处理中</>
                            ) : (
                              <><Zap className="w-3 h-3" /> 自动推进</>
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                  {items.length === 0 && (
                    <div className="py-8 text-center">
                      <div className="w-10 h-10 mx-auto mb-2 rounded-xl bg-gray-100 flex items-center justify-center">
                        <Play className="w-4 h-4 text-gray-300" />
                      </div>
                      <p className="text-xs text-gray-400">暂无</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* 统计概览 */}
      {pipeline && (
        <div className="glass-card p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <div className="w-1 h-4 rounded-full bg-indigo-500" />
            管道统计
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: '总候选人', value: pipeline.total, color: 'from-indigo-50 to-blue-50', textColor: 'text-indigo-700' },
              { label: '已录用', value: pipeline.status_counts?.hired || 0, color: 'from-emerald-50 to-green-50', textColor: 'text-emerald-700' },
              { label: '面试中', value: (pipeline.status_counts?.scheduled || 0) + (pipeline.status_counts?.interviewed || 0), color: 'from-blue-50 to-cyan-50', textColor: 'text-blue-700' },
              { label: '已拒绝', value: pipeline.status_counts?.rejected || 0, color: 'from-red-50 to-pink-50', textColor: 'text-red-700' },
            ].map(s => (
              <div key={s.label} className={`rounded-xl bg-gradient-to-br ${s.color} p-4`}>
                <p className="text-xs text-gray-500 mb-1">{s.label}</p>
                <p className={`text-2xl font-bold ${s.textColor}`}>{s.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
