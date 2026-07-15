import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Search, Upload, Loader2, Trash2, UserPlus, Filter } from 'lucide-react'
import { candidatesApi, resumesApi } from '../lib/api'
import { showToast } from '../components/Toast'

const statusLabels: Record<string, string> = {
  new: '新候选人', analyzed: '已分析', talent_pool: '人才池',
  q_sent: '问卷已发', q_done: '问卷完成', scheduled: '已排期',
  interviewed: '已面试', hired: '已录用', rejected: '已拒绝',
  archived: '已归档',
}

export default function Candidates() {
  const [data, setData] = useState<any>({ items: [], total: 0 })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [uploadingId, setUploadingId] = useState<number | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ name: '', phone: '', email: '', position: '', source: 'manual' })
  const navigate = useNavigate()

  const load = () => {
    setLoading(true)
    return candidatesApi.list({ page, page_size: 20, search }).then(setData).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [page, search])

  const handleAdd = async () => {
    await candidatesApi.create(form)
    setShowAdd(false)
    setForm({ name: '', phone: '', email: '', position: '', source: 'manual' })
    load()
    showToast('success', '候选人添加成功')
  }

  const handleUploadResume = async (candidateId: number, file: File) => {
    setUploadingId(candidateId)
    const candidate = data.items.find((c: any) => c.id === candidateId)
    showToast('loading', '正在上传简历...', `${file.name}`)
    const timeoutId = setTimeout(() => {
      setUploadingId(null)
      showToast('error', '分析超时', '网络较慢，请稍后重试')
    }, 30000)
    try {
      const uploadResult = await resumesApi.upload(candidateId, file)
      showToast('loading', '简历解析完成，正在进行 AI 分析...', `${candidate?.name || ''}`)
      await resumesApi.analyze(uploadResult.id, candidate?.position || '')
      showToast('success', 'AI 简历分析完成！', '匹配度评分已生成，点击候选人查看详情')
      await load()
    } catch (e: any) {
      showToast('error', '分析失败', e.message || '请检查文件格式后重试')
    } finally {
      clearTimeout(timeoutId)
      setUploadingId(null)
    }
  }

  const handleDelete = async (id: number, name: string) => {
    if (!window.confirm(`确定要删除候选人「${name}」吗？此操作不可恢复。`)) return
    try {
      await candidatesApi.delete(id)
      showToast('success', '已删除', `候选人「${name}」已删除`)
      load()
    } catch (e: any) {
      showToast('error', '删除失败', e.message)
    }
  }

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-800">候选人管理</h2>
          <p className="text-sm text-gray-400 mt-0.5">共 {data.total} 位候选人</p>
        </div>
        <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2">
          <UserPlus className="w-4 h-4" /> 添加候选人
        </button>
      </div>

      {/* 搜索栏 */}
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text" placeholder="搜索姓名、邮箱或岗位..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
            className="input-field w-full pl-10"
          />
        </div>
        <button className="btn-secondary flex items-center gap-2">
          <Filter className="w-4 h-4" /> 筛选
        </button>
      </div>

      {/* 新增弹窗 */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setShowAdd(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-5">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                <UserPlus className="w-4 h-4 text-white" />
              </div>
              <h3 className="text-lg font-semibold text-gray-800">添加候选人</h3>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">姓名 *</label>
                <input placeholder="请输入姓名" value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  className="input-field w-full" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">电话</label>
                  <input placeholder="请输入电话" value={form.phone}
                    onChange={e => setForm({ ...form, phone: e.target.value })}
                    className="input-field w-full" />
                </div>
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">邮箱</label>
                  <input placeholder="请输入邮箱" value={form.email}
                    onChange={e => setForm({ ...form, email: e.target.value })}
                    className="input-field w-full" />
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">应聘岗位 *</label>
                <input placeholder="请输入应聘岗位" value={form.position}
                  onChange={e => setForm({ ...form, position: e.target.value })}
                  className="input-field w-full" />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setShowAdd(false)} className="btn-secondary flex-1">取消</button>
              <button onClick={handleAdd} disabled={!form.name || !form.position}
                      className="btn-primary flex-1">确认添加</button>
            </div>
          </div>
        </div>
      )}

      {/* 表格 */}
      <div className="glass-card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 bg-gray-50/50">
              <th className="px-6 py-3.5 text-xs font-semibold uppercase tracking-wider">候选人</th>
              <th className="px-6 py-3.5 text-xs font-semibold uppercase tracking-wider">岗位</th>
              <th className="px-6 py-3.5 text-xs font-semibold uppercase tracking-wider">状态</th>
              <th className="px-6 py-3.5 text-xs font-semibold uppercase tracking-wider">匹配度</th>
              <th className="px-6 py-3.5 text-xs font-semibold uppercase tracking-wider">来源</th>
              <th className="px-6 py-3.5 text-xs font-semibold uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100/80">
            {loading ? (
              <tr><td colSpan={6} className="px-6 py-16 text-center">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-400 mx-auto mb-2" />
                <p className="text-gray-400 text-sm">加载中...</p>
              </td></tr>
            ) : data.items.length === 0 ? (
              <tr><td colSpan={6} className="px-6 py-16 text-center text-gray-400">
                {search ? '没有找到匹配的候选人' : '暂无候选人，点击上方按钮添加'}
              </td></tr>
            ) : (
              data.items.map((c: any) => (
                <tr key={c.id}
                    onClick={() => navigate(`/candidates/${c.id}`)}
                    className="hover:bg-indigo-50/40 transition-colors cursor-pointer">
                  <td className="px-6 py-3.5">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                        {c.name?.[0] || '?'}
                      </div>
                      <div>
                        <p className="font-medium text-gray-800">{c.name}</p>
                        <p className="text-xs text-gray-400">{c.email || '-'}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-3.5 text-gray-600">{c.position}</td>
                  <td className="px-6 py-3.5">
                    <span className={`status-badge ${c.status}`}>{statusLabels[c.status] || c.status}</span>
                  </td>
                  <td className="px-6 py-3.5">
                    {c.match_score != null ? (
                      <div className="flex items-center gap-2">
                        <div className="w-14 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              c.match_score >= 70 ? 'bg-emerald-500' : c.match_score >= 50 ? 'bg-amber-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${c.match_score}%` }}
                          />
                        </div>
                        <span className={`text-xs font-semibold ${
                          c.match_score >= 70 ? 'text-emerald-600' : c.match_score >= 50 ? 'text-amber-600' : 'text-red-600'
                        }`}>{c.match_score}</span>
                      </div>
                    ) : <span className="text-xs text-gray-300">-</span>}
                  </td>
                  <td className="px-6 py-3.5 text-gray-500 text-xs">{c.source}</td>
                  <td className="px-6 py-3.5" onClick={e => e.stopPropagation()}>
                    <div className="flex items-center gap-1">
                      {uploadingId === c.id ? (
                        <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-indigo-600 bg-indigo-50 rounded-lg">
                          <Loader2 className="w-3 h-3 animate-spin" /> 分析中
                        </span>
                      ) : (
                        <>
                          <label className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg cursor-pointer transition-colors">
                            <Upload className="w-3 h-3" /> 上传简历
                            <input type="file" className="hidden" accept=".pdf,.docx,.txt"
                                   onChange={e => {
                                     const f = e.target.files?.[0]
                                     if (f) handleUploadResume(c.id, f)
                                   }} />
                          </label>
                          <button onClick={() => handleDelete(c.id, c.name)}
                                  className="flex items-center gap-1 px-3 py-1.5 text-xs text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      {data.total > 20 && (
        <div className="flex items-center justify-center gap-2">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                  className="btn-secondary px-4 py-2 text-sm disabled:opacity-40">上一页</button>
          <span className="px-4 py-2 text-sm text-gray-500 font-medium">
            第 {page} / {Math.ceil(data.total / 20)} 页
          </span>
          <button onClick={() => setPage(p => p + 1)} disabled={page >= Math.ceil(data.total / 20)}
                  className="btn-secondary px-4 py-2 text-sm disabled:opacity-40">下一页</button>
        </div>
      )}
    </div>
  )
}
