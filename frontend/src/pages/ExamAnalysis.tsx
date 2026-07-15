import { useState, useEffect } from 'react'
import { ClipboardList, Loader2, CheckCircle, XCircle, Clock, AlertCircle, TrendingUp, User, FileText, BarChart3 } from 'lucide-react'
import { examAnalysisApi, type ExamAnalysis } from '../lib/api'

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: any }> = {
  pending:    { label: '待分析',   color: 'text-gray-600',  bg: 'bg-gray-100',           icon: Clock },
  analyzing:  { label: '分析中',   color: 'text-blue-600',  bg: 'bg-blue-100',           icon: Loader2 },
  completed:  { label: '已完成',   color: 'text-emerald-600', bg: 'bg-emerald-100',        icon: CheckCircle },
  failed:     { label: '失败',     color: 'text-red-600',   bg: 'bg-red-100',            icon: XCircle },
}

export default function ExamAnalysisPage() {
  const [data, setData] = useState<ExamAnalysis[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = async (p: number) => {
    setLoading(true)
    setError(null)
    try {
      const res = await examAnalysisApi.list({ page: p, page_size: 20 })
      setData(res.items)
      setTotal(res.total)
    } catch (e: any) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData(page) }, [page])

  const totalPages = Math.max(1, Math.ceil(total / 20))
  const completedCount = data.filter(d => d.analysis_status === 'completed').length
  const failedCount = data.filter(d => d.analysis_status === 'failed').length

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/25">
            <ClipboardList className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-800">试卷分析看板</h1>
            <p className="text-sm text-gray-400">轻速云考试结果 — Dify 智能分析</p>
          </div>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="glass-card rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-100 flex items-center justify-center">
            <BarChart3 className="w-5 h-5 text-indigo-600" />
          </div>
          <div>
            <p className="text-xs text-gray-400">总记录</p>
            <p className="text-xl font-bold text-gray-800">{total}</p>
          </div>
        </div>
        <div className="glass-card rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center">
            <CheckCircle className="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <p className="text-xs text-gray-400">已完成</p>
            <p className="text-xl font-bold text-emerald-600">{completedCount}</p>
          </div>
        </div>
        <div className="glass-card rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
            <AlertCircle className="w-5 h-5 text-red-600" />
          </div>
          <div>
            <p className="text-xs text-gray-400">失败</p>
            <p className="text-xl font-bold text-red-600">{failedCount}</p>
          </div>
        </div>
        <div className="glass-card rounded-xl p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-blue-600" />
          </div>
          <div>
            <p className="text-xs text-gray-400">分析率</p>
            <p className="text-xl font-bold text-gray-800">
              {total > 0 ? Math.round(completedCount / total * 100) : 0}%
            </p>
          </div>
        </div>
      </div>

      {/* 加载状态 */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
            <p className="text-sm text-gray-400">加载中...</p>
          </div>
        </div>
      )}

      {/* 错误状态 */}
      {error && !loading && (
        <div className="glass-card rounded-xl p-8 text-center">
          <XCircle className="w-12 h-12 text-red-400 mx-auto mb-3" />
          <p className="text-gray-600 mb-2">加载失败</p>
          <p className="text-sm text-gray-400 mb-4">{error}</p>
          <button onClick={() => loadData(page)} className="btn-secondary px-4 py-2 rounded-lg text-sm">
            重试
          </button>
        </div>
      )}

      {/* 空状态 */}
      {!loading && !error && data.length === 0 && (
        <div className="glass-card rounded-xl p-12 text-center">
          <ClipboardList className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 font-medium mb-1">暂无试卷分析数据</p>
          <p className="text-sm text-gray-400">等待轻速云回调推送考试结果...</p>
        </div>
      )}

      {/* 列表 */}
      {!loading && data.length > 0 && (
        <div className="space-y-4">
          {data.map(item => (
            <ExamAnalysisCard key={item.id} item={item} />
          ))}
        </div>
      )}

      {/* 分页 */}
      {!loading && totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <button
            disabled={page <= 1}
            onClick={() => setPage(p => Math.max(1, p - 1))}
            className="px-3 py-1.5 rounded-lg text-sm border border-gray-200 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            上一页
          </button>
          <span className="text-sm text-gray-500 px-3">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(p => p + 1)}
            className="px-3 py-1.5 rounded-lg text-sm border border-gray-200 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}

function ExamAnalysisCard({ item }: { item: ExamAnalysis }) {
  const StatusIcon = STATUS_CONFIG[item.analysis_status]?.icon || Clock
  const isSpinning = item.analysis_status === 'analyzing'

  return (
    <div className="glass-card rounded-xl overflow-hidden border border-gray-100/60 hover:shadow-md transition-shadow">
      {/* 卡片头部 */}
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-sm font-bold">
            {item.candidate_name?.[0] || '?'}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium text-gray-800">{item.candidate_name}</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium inline-flex items-center gap-1 ${STATUS_CONFIG[item.analysis_status]?.bg} ${STATUS_CONFIG[item.analysis_status]?.color}`}>
                <StatusIcon className={`w-3 h-3 ${isSpinning ? 'animate-spin' : ''}`} />
                {STATUS_CONFIG[item.analysis_status]?.label || item.analysis_status}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-400 mt-0.5">
              <FileText className="w-3 h-3" />
              <span>{item.exam_title}</span>
              {item.exam_score != null && (
                <>
                  <span className="text-gray-300">|</span>
                  <span>得分 {item.exam_score}{item.exam_total != null ? `/${item.exam_total}` : ''}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="text-xs text-gray-400">
          {new Date(item.created_at).toLocaleString('zh-CN')}
        </div>
      </div>

      {/* 分析结果 */}
      {item.analysis_status === 'completed' && item.analysis_result && (
        <div className="p-4 space-y-4">
          {/* 综合评分 */}
          {item.analysis_result.overall_score != null && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500 shrink-0">综合评分</span>
              <div className="flex-1 h-2.5 rounded-full bg-gray-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-purple-500 transition-all"
                  style={{ width: `${item.analysis_result.overall_score}%` }}
                />
              </div>
              <span className="text-sm font-bold text-indigo-600 shrink-0 w-10 text-right">
                {item.analysis_result.overall_score}
              </span>
            </div>
          )}

          {/* 各维度评分 */}
          {item.analysis_result.knowledge_dimensions && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {Object.entries(item.analysis_result.knowledge_dimensions).map(([key, val]) => (
                <div key={key} className="bg-gray-50 rounded-lg p-2.5">
                  <p className="text-xs text-gray-400 mb-1">{key}</p>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-gray-200 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-purple-500"
                        style={{ width: `${val}%` }}
                      />
                    </div>
                    <span className="text-xs font-semibold text-gray-600">{val}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 优势 */}
          {item.analysis_result.strengths && item.analysis_result.strengths.length > 0 && (
            <div>
              <p className="text-xs text-gray-400 mb-1.5">优势</p>
              <div className="flex flex-wrap gap-1.5">
                {item.analysis_result.strengths.map((s, i) => (
                  <span key={i} className="px-2 py-0.5 rounded-md text-xs bg-emerald-50 text-emerald-700 border border-emerald-200">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 薄弱环节 */}
          {item.analysis_result.weaknesses && item.analysis_result.weaknesses.length > 0 && (
            <div>
              <p className="text-xs text-gray-400 mb-1.5">薄弱环节</p>
              <div className="flex flex-wrap gap-1.5">
                {item.analysis_result.weaknesses.map((w, i) => (
                  <span key={i} className="px-2 py-0.5 rounded-md text-xs bg-red-50 text-red-700 border border-red-200">
                    {w}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 建议 */}
          {item.analysis_result.suggestion && (
            <div className="bg-indigo-50/50 rounded-lg p-3 border border-indigo-100/50">
              <p className="text-xs text-indigo-400 mb-1">建议</p>
              <p className="text-sm text-gray-700">{item.analysis_result.suggestion}</p>
            </div>
          )}

          {/* 摘要 */}
          {item.analysis_result.summary && (
            <p className="text-xs text-gray-400 italic">{item.analysis_result.summary}</p>
          )}

          {/* 分析时间 */}
          {item.analyzed_at && (
            <div className="text-xs text-gray-300 text-right">
              分析完成: {new Date(item.analyzed_at).toLocaleString('zh-CN')}
            </div>
          )}
        </div>
      )}

      {/* 失败信息 */}
      {item.analysis_status === 'failed' && item.error_message && (
        <div className="p-4">
          <div className="bg-red-50 rounded-lg p-3 border border-red-100">
            <p className="text-xs text-red-400 mb-1">错误信息</p>
            <p className="text-sm text-red-600">{item.error_message}</p>
          </div>
        </div>
      )}
    </div>
  )
}
