import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Upload, Brain, Send, Calendar, FileText, Loader2, CheckCircle } from 'lucide-react'
import { candidatesApi, resumesApi, questionnairesApi, interviewsApi } from '../lib/api'
import { showToast } from '../components/Toast'

export default function CandidateDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [candidate, setCandidate] = useState<any>(null)
  const [resume, setResume] = useState<any>(null)
  const [questionnaires, setQuestionnaires] = useState<any[]>([])
  const [interviews, setInterviews] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'analysis' | 'questionnaire' | 'interview'>('analysis')
  const [jd, setJd] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeStep, setAnalyzeStep] = useState('')

  const statusLabels: Record<string, string> = {
    new: '新候选人', analyzed: '已分析', talent_pool: '人才池',
    q_sent: '问卷已发', q_done: '问卷完成', scheduled: '已排期',
    interviewed: '已面试', hired: '已录用', rejected: '已拒绝',
    archived: '已归档',
  }

  useEffect(() => {
    if (!id) return
    setAnalyzing(false)
    setAnalyzeStep('')
    const cid = parseInt(id)
    Promise.all([
      candidatesApi.get(cid),
      resumesApi.getByCandidate(cid).catch(() => null),
      questionnairesApi.getByCandidate(cid).catch(() => []),
      interviewsApi.getByCandidate(cid).catch(() => []),
    ]).then(([c, r, qs, ivs]) => {
      setCandidate(c)
      setResume(r)
      setQuestionnaires(qs)
      setInterviews(ivs)
    }).finally(() => setLoading(false))
  }, [id])

  const handleUploadAndAnalyze = async (file: File) => {
    if (!id) return
    setAnalyzing(true)
    setAnalyzeStep('uploading')
    const cid = parseInt(id)
    const safetyTimer = setTimeout(() => { setAnalyzing(false); setAnalyzeStep('') }, 30000)
    try {
      showToast('loading', '正在上传简历...', `${file.name}`)
      const uploadResult = await resumesApi.upload(cid, file)
      setAnalyzeStep('parsing')
      showToast('loading', '简历解析完成，AI 分析中...', '正在提取结构化信息并计算匹配度')
      await resumesApi.analyze(uploadResult.id, jd)
      clearTimeout(safetyTimer)
      setAnalyzeStep('done')
      const r = await resumesApi.getByCandidate(cid)
      setResume(r)
      const c = await candidatesApi.get(cid)
      setCandidate(c)
      showToast('success', 'AI 简历分析完成！',
        r?.match_analysis?.overall_score
          ? `匹配度 ${r.match_analysis.overall_score} 分 — 共识别 ${r.analysis?.skills?.length || 0} 项技能`
          : '分析结果已生成'
      )
    } catch (e: any) {
      clearTimeout(safetyTimer)
      showToast('error', '分析失败', e.message)
    } finally {
      setAnalyzing(false)
      setAnalyzeStep('')
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleSendQuestionnaire = async () => {
    if (!id) return
    showToast('loading', '正在发送问卷链接...')
    try {
      const result = await questionnairesApi.sendLink(parseInt(id))
      showToast('success', '问卷链接已发送',
        `链接: ${result.link}`
      )
      const qs = await questionnairesApi.getByCandidate(parseInt(id))
      setQuestionnaires(qs)
    } catch (e: any) { showToast('error', '发送失败', e.message) }
  }

  const handleScheduleInterview = async () => {
    if (!id) return
    showToast('loading', '正在生成面试时间段...')
    try {
      const today = new Date()
      const end = new Date(today)
      end.setDate(end.getDate() + 7)
      const result = await interviewsApi.generateSlots({
        candidate_id: parseInt(id),
        date_range_start: today.toISOString().slice(0, 10),
        date_range_end: end.toISOString().slice(0, 10),
      })
      showToast('success', '面试时间段已生成', `共 ${result.proposed_slots.length} 个可选时间`)
      const ivs = await interviewsApi.getByCandidate(parseInt(id))
      setInterviews(ivs)
    } catch (e: any) { showToast('error', '排期失败', e.message) }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <div className="relative w-12 h-12 mx-auto mb-3">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 animate-pulse" />
          <Loader2 className="w-5 h-5 text-white absolute inset-0 m-auto animate-spin" />
        </div>
        <p className="text-gray-400 text-sm">加载中...</p>
      </div>
    </div>
  )
  if (!candidate) return <div className="text-center py-12 text-gray-400">候选人不存在</div>

  const matchScore = resume?.match_analysis?.overall_score
  const analysis = resume?.analysis

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* 头部 */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/candidates')} className="p-2 rounded-xl hover:bg-white/80 transition-colors">
          <ArrowLeft className="w-5 h-5 text-gray-400" />
        </button>
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xl font-bold shadow-lg shadow-indigo-500/25">
          {candidate.name[0]}
        </div>
        <div className="flex-1">
          <h2 className="text-xl font-bold text-gray-800">{candidate.name}</h2>
          <p className="text-sm text-gray-400">{candidate.position} · {candidate.email}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`status-badge ${candidate.status}`}>
            {statusLabels[candidate.status] || candidate.status}
          </span>
          {matchScore != null && (
            <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold ${
              matchScore >= 70 ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/60' :
              matchScore >= 50 ? 'bg-amber-50 text-amber-700 ring-1 ring-amber-200/60' :
              'bg-red-50 text-red-700 ring-1 ring-red-200/60'
            }`}>
              {matchScore}%
            </span>
          )}
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex flex-wrap gap-2.5">
        <label className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium cursor-pointer transition-all ${
          analyzing ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-gradient-to-br from-indigo-50 to-blue-50 text-indigo-700 hover:shadow-md hover:shadow-indigo-500/10 border border-indigo-100/60'
        }`}>
          {analyzing && analyzeStep === 'uploading' ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> 上传中...</>
          ) : analyzing && analyzeStep === 'parsing' ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> AI分析中...</>
          ) : analyzing && analyzeStep === 'done' ? (
            <><CheckCircle className="w-4 h-4 text-emerald-500" /> 完成</>
          ) : (
            <><Upload className="w-4 h-4" /> 上传简历</>
          )}
          <input type="file" ref={fileInputRef} className="hidden" accept=".pdf,.docx,.txt" disabled={analyzing}
                 onChange={e => { const f = e.target.files?.[0]; if (f) handleUploadAndAnalyze(f) }} />
        </label>

        <button onClick={handleSendQuestionnaire} disabled={analyzing}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  analyzing ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-gradient-to-br from-purple-50 to-violet-50 text-purple-700 hover:shadow-md hover:shadow-purple-500/10 border border-purple-100/60'
                }`}>
          <Send className="w-4 h-4" /> 发送问卷
        </button>

        <button onClick={handleScheduleInterview} disabled={analyzing}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  analyzing ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-gradient-to-br from-teal-50 to-emerald-50 text-teal-700 hover:shadow-md hover:shadow-teal-500/10 border border-teal-100/60'
                }`}>
          <Calendar className="w-4 h-4" /> 安排面试
        </button>
      </div>

      {/* 岗位描述 */}
      <div className="glass-card p-4">
        <label className="text-xs font-medium text-gray-500 mb-2 block">岗位描述（用于提升匹配度分析准确性）</label>
        <input type="text" value={jd} onChange={e => setJd(e.target.value)}
               placeholder="输入岗位描述，如：需要 3 年以上 Python 后端开发经验，熟悉微服务架构..."
               className="input-field w-full" />
      </div>

      {/* 分析中动画 */}
      {analyzing && (
        <div className="rounded-2xl p-5 bg-gradient-to-r from-indigo-50 via-purple-50 to-blue-50 border border-indigo-100/60">
          <div className="flex items-center gap-4">
            <div className="relative">
              <Loader2 className="w-12 h-12 text-indigo-400 animate-spin" />
              <Brain className="w-6 h-6 text-indigo-600 absolute top-3 left-3" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-gray-800">
                {analyzeStep === 'uploading' && '正在上传简历...'}
                {analyzeStep === 'parsing' && 'AI 正在深度分析简历...'}
                {analyzeStep === 'done' && '分析完成!'}
              </p>
              <div className="mt-3 h-2 bg-white/80 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-700 ${
                  analyzeStep === 'uploading' ? 'w-1/3 bg-indigo-400' :
                  analyzeStep === 'parsing' ? 'w-2/3 bg-indigo-500' : 'w-full bg-emerald-500'
                }`} />
              </div>
              <div className="flex items-center gap-2 mt-2">
                <div className={`flex items-center gap-1 text-xs font-medium ${analyzeStep === 'uploading' ? 'text-indigo-600' : 'text-emerald-600'}`}>
                  <CheckCircle className="w-3 h-3" /> 文件上传
                </div>
                <span className="text-gray-300 text-xs">→</span>
                <div className={`flex items-center gap-1 text-xs font-medium ${
                  analyzeStep === 'parsing' ? 'text-indigo-600' : analyzeStep === 'done' ? 'text-emerald-600' : 'text-gray-400'
                }`}>
                  {analyzeStep === 'parsing' ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                  AI 分析
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-gray-100 w-fit">
        {[
          { key: 'analysis', label: '简历分析', icon: Brain },
          { key: 'questionnaire', label: '问卷', icon: FileText },
          { key: 'interview', label: '面试', icon: Calendar },
        ].map(t => (
          <button key={t.key} onClick={() => setActiveTab(t.key as any)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    activeTab === t.key ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                  }`}>
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {/* Tab: 简历分析 */}
      {activeTab === 'analysis' && (
        <div className="space-y-5">
          {!resume ? (
            <div className="text-center py-16">
              <div className="w-14 h-14 mx-auto mb-3 rounded-2xl bg-gray-100 flex items-center justify-center">
                <Upload className="w-7 h-7 text-gray-300" />
              </div>
              <p className="text-gray-500">尚未上传简历</p>
              <p className="text-sm text-gray-400 mt-1">点击上方"上传简历"按钮开始分析</p>
            </div>
          ) : (
            <>
              {/* 基本信息 */}
              <div className="rounded-2xl p-6 bg-gradient-to-r from-indigo-50 via-purple-50 to-blue-50 border border-indigo-100/60">
                <div className="flex items-center gap-4 mb-4">
                  <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-2xl font-bold shadow-lg shadow-indigo-500/25">
                    {(analysis?.basic_info?.name || candidate.name || '?')[0]}
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-gray-800">{analysis?.basic_info?.name || candidate.name}</h3>
                    <p className="text-gray-500 text-sm">{candidate.position}</p>
                  </div>
                  {resume.match_analysis?.overall_score != null && (
                    <div className="ml-auto text-center">
                      <div className={`text-3xl font-bold ${
                        resume.match_analysis.overall_score >= 70 ? 'text-emerald-600' :
                        resume.match_analysis.overall_score >= 50 ? 'text-amber-600' : 'text-red-600'
                      }`}>{resume.match_analysis.overall_score}</div>
                      <div className="text-xs text-gray-400">匹配度</div>
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-4 text-sm border-t border-indigo-200/60 pt-4">
                  <div><span className="text-xs text-gray-400">电话</span><p className="font-medium text-gray-700 mt-0.5">{analysis?.basic_info?.phone || candidate.phone || '-'}</p></div>
                  <div><span className="text-xs text-gray-400">邮箱</span><p className="font-medium text-gray-700 mt-0.5">{analysis?.basic_info?.email || candidate.email || '-'}</p></div>
                  <div><span className="text-xs text-gray-400">所在地</span><p className="font-medium text-gray-700 mt-0.5">{analysis?.basic_info?.location || '-'}</p></div>
                </div>
              </div>

              {/* 教育经历 */}
              {analysis?.education?.length > 0 && (
                <div className="glass-card p-6">
                  <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
                    <div className="w-1 h-4 rounded-full bg-indigo-500" /> 教育经历
                  </h3>
                  <div className="space-y-3">
                    {analysis.education.map((edu: any, i: number) => (
                      <div key={i} className="flex items-start gap-4 p-3.5 rounded-xl bg-gradient-to-r from-gray-50 to-indigo-50/50 border border-gray-100">
                        <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center flex-shrink-0">
                          <span className="text-sm font-bold text-indigo-600">{edu.degree?.[0] || '学'}</span>
                        </div>
                        <div className="flex-1">
                          <p className="font-medium text-gray-800">{edu.school}</p>
                          <p className="text-sm text-gray-500">{edu.degree} · {edu.major}</p>
                          <p className="text-xs text-gray-400 mt-0.5">{edu.start} - {edu.end}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 工作经历 */}
              {analysis?.work_experience?.length > 0 && (
                <div className="glass-card p-6">
                  <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
                    <div className="w-1 h-4 rounded-full bg-blue-500" /> 工作经历
                  </h3>
                  <div className="space-y-4">
                    {analysis.work_experience.map((exp: any, i: number) => (
                      <div key={i} className="relative border-l-2 border-indigo-200 pl-5 ml-2">
                        <div className="absolute -left-[5px] top-1 w-2 h-2 rounded-full bg-indigo-400" />
                        <div className="flex items-center gap-2 mb-1">
                          <p className="font-medium text-gray-800">{exp.company}</p>
                          <span className="text-gray-300">|</span>
                          <p className="text-sm text-gray-500">{exp.position}</p>
                        </div>
                        <p className="text-xs text-gray-400 mb-1.5">{exp.start} - {exp.end}</p>
                        <p className="text-sm text-gray-600">{exp.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 项目经验 */}
              {analysis?.projects?.length > 0 && (
                <div className="glass-card p-6">
                  <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
                    <div className="w-1 h-4 rounded-full bg-purple-500" /> 项目经验
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {analysis.projects.map((proj: any, i: number) => (
                      <div key={i} className="p-4 rounded-xl bg-white border border-gray-100 hover:shadow-md transition-shadow">
                        <p className="font-medium text-gray-800 mb-1">{proj.name}</p>
                        <p className="text-xs text-gray-500 mb-2">{proj.description}</p>
                        {proj.technologies?.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {proj.technologies.map((t: string) => (
                              <span key={t} className="px-2 py-0.5 rounded-md bg-purple-50 text-purple-600 text-[11px] font-medium">{t}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 技能 */}
              {analysis?.skills?.length > 0 && (
                <div className="glass-card p-6">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <div className="w-1 h-4 rounded-full bg-emerald-500" /> 技能标签
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {analysis.skills.map((s: string) => (
                      <span key={s} className="px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 text-xs font-medium border border-emerald-100/60">{s}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* 匹配度分析 */}
              {resume.match_analysis && (
                <div className="glass-card p-6">
                  <h3 className="text-sm font-semibold text-gray-700 mb-5 flex items-center gap-2">
                    <div className="w-1 h-4 rounded-full bg-amber-500" /> 匹配度分析
                  </h3>
                  <div className="space-y-4">
                    {Object.entries(resume.match_analysis.dimensions || {}).map(([key, val]) => (
                      <div key={key}>
                        <div className="flex justify-between text-sm mb-1.5">
                          <span className="text-gray-600">{key}</span>
                          <span className="font-semibold text-gray-800">{val}分</span>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-2">
                          <div className="h-2 rounded-full bg-gradient-to-r from-amber-400 via-orange-400 to-indigo-500 transition-all duration-1000" style={{ width: `${val}%`, maxWidth: '100%' }} />
                        </div>
                      </div>
                    ))}
                  </div>

                  {resume.match_analysis.strengths?.length > 0 && (
                    <div className="mt-4 p-4 rounded-xl bg-emerald-50 border border-emerald-100/60">
                      <h4 className="text-sm font-medium text-emerald-700 mb-2">优势</h4>
                      <ul className="space-y-1.5">
                        {resume.match_analysis.strengths.map((s: string, i: number) => (
                          <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                            <span className="w-5 h-5 rounded-full bg-emerald-200 text-emerald-700 flex items-center justify-center text-[11px] flex-shrink-0 mt-0.5 font-bold">✓</span>
                            {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {resume.match_analysis.risks?.length > 0 && (
                    <div className="mt-3 p-4 rounded-xl bg-red-50 border border-red-100/60">
                      <h4 className="text-sm font-medium text-red-700 mb-2">潜在风险</h4>
                      <ul className="space-y-1.5">
                        {resume.match_analysis.risks.map((r: string, i: number) => (
                          <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                            <span className="w-5 h-5 rounded-full bg-red-200 text-red-700 flex items-center justify-center text-[11px] flex-shrink-0 mt-0.5 font-bold">!</span>
                            {r}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {resume.match_analysis.recommended_questions?.length > 0 && (
                    <div className="mt-3 p-4 rounded-xl bg-indigo-50 border border-indigo-100/60">
                      <h4 className="text-sm font-medium text-indigo-700 mb-3">推荐面试问题</h4>
                      <ol className="space-y-2">
                        {resume.match_analysis.recommended_questions.map((q: string, i: number) => (
                          <li key={i} className="text-sm text-gray-600 flex gap-2">
                            <span className="w-6 h-6 rounded-lg bg-indigo-200 text-indigo-700 flex items-center justify-center text-xs flex-shrink-0 font-bold">{i + 1}</span>
                            {q}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                </div>
              )}

              {/* AI 总结 */}
              {resume.summary && (
                <div className="rounded-2xl p-6 bg-gradient-to-r from-gray-50 to-indigo-50 border border-gray-200">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                    <div className="w-1 h-4 rounded-full bg-indigo-500" /> AI 总结
                  </h3>
                  <p className="text-sm text-gray-600 leading-relaxed">{resume.summary}</p>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {activeTab === 'questionnaire' && (
        <div className="space-y-4">
          {questionnaires.length === 0 ? (
            <div className="text-center py-16">
              <div className="w-14 h-14 mx-auto mb-3 rounded-2xl bg-gray-100 flex items-center justify-center">
                <FileText className="w-7 h-7 text-gray-300" />
              </div>
              <p className="text-gray-500">尚未发送问卷</p>
              <p className="text-sm text-gray-400 mt-1">点击上方"发送问卷"按钮</p>
            </div>
          ) : (
            questionnaires.map((q: any) => (
              <div key={q.id} className="glass-card p-6">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <h3 className="font-semibold text-gray-800">{q.title}</h3>
                    <p className="text-xs text-gray-400">
                      状态: {q.status} · 发送: {q.sent_at?.slice(0, 10) || '-'} · 截止: {q.deadline?.slice(0, 10) || '-'}
                    </p>
                  </div>
                  <span className={`status-badge ${q.status}`}>{q.status}</span>
                </div>
                {q.questions?.length > 0 && (
                  <div className="space-y-2">
                    {q.questions.map((qq: any, i: number) => (
                      <div key={qq.id} className="p-3.5 rounded-xl bg-gray-50 border border-gray-100">
                        <p className="text-sm text-gray-800"><span className="text-gray-400">Q{i + 1}.</span> {qq.question}</p>
                        {qq.type === 'choice' && qq.options && (
                          <div className="mt-1.5 space-y-0.5">
                            {qq.options.map((o: string) => <p key={o} className="text-xs text-gray-500 pl-4">· {o}</p>)}
                          </div>
                        )}
                        <span className="text-xs text-gray-400 mt-1.5 inline-block">{qq.type}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'interview' && (
        <div className="space-y-4">
          {interviews.length === 0 ? (
            <div className="text-center py-16">
              <div className="w-14 h-14 mx-auto mb-3 rounded-2xl bg-gray-100 flex items-center justify-center">
                <Calendar className="w-7 h-7 text-gray-300" />
              </div>
              <p className="text-gray-500">尚未安排面试</p>
              <p className="text-sm text-gray-400 mt-1">点击上方"安排面试"按钮</p>
            </div>
          ) : (
            interviews.map((iv: any) => (
              <div key={iv.id} className="glass-card p-6">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <h3 className="font-semibold text-gray-800">{iv.round}面试</h3>
                    <p className="text-xs text-gray-400">面试官: {iv.interviewers?.join(', ') || '-'}</p>
                  </div>
                  <span className={`status-badge ${iv.status}`}>{iv.status}</span>
                </div>
                {iv.confirmed_start && (
                  <div className="p-3.5 rounded-xl bg-gradient-to-r from-emerald-50 to-green-50 border border-emerald-100/60 text-sm">
                    <span className="font-medium text-gray-700">已确认: {new Date(iv.confirmed_start).toLocaleString('zh-CN')}</span>
                    {iv.location && <span className="text-gray-500 ml-2">· {iv.location}</span>}
                    {iv.meeting_link && <span className="ml-2">· <a href={iv.meeting_link} className="text-blue-500 hover:underline">会议链接</a></span>}
                  </div>
                )}
                {iv.proposed_slots?.length > 0 && !iv.confirmed_start && (
                  <div className="space-y-2">
                    <p className="text-sm text-gray-500">建议时间段:</p>
                    {iv.proposed_slots.map((s: any, i: number) => (
                      <div key={i} className="p-2.5 rounded-xl bg-gray-50 border border-gray-100 text-sm text-gray-600">
                        {s.date} {s.start_time} - {s.end_time}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
