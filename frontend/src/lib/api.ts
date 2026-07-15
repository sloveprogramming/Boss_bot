/** API 客户端 */
const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ========== 候选人 ==========
export interface Candidate {
  id: number; name: string; phone?: string; email?: string
  position: string; source: string; status: string
  match_score?: number; tags: string[]
  experience_years?: number; job_category?: string
  talent_pool_id?: number; talent_pool_reason?: string
  created_at: string; updated_at: string
}

export const candidatesApi = {
  list: (params?: { page?: number; page_size?: number; status?: string; search?: string }) => {
    const q = new URLSearchParams()
    if (params?.page) q.set('page', String(params.page))
    if (params?.page_size) q.set('page_size', String(params.page_size))
    if (params?.status) q.set('status', params.status)
    if (params?.search) q.set('search', params.search)
    return request<{ total: number; items: Candidate[]; page: number; page_size: number }>(
      `/candidates?${q}`
    )
  },
  get: (id: number) => request<Candidate>(`/candidates/${id}`),
  create: (data: Partial<Candidate>) =>
    request<Candidate>('/candidates', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: Partial<Candidate>) =>
    request<Candidate>(`/candidates/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: number) =>
    request<{ status: string }>(`/candidates/${id}`, { method: 'DELETE' }),
}

// ========== 简历 ==========
export interface ResumeAnalysis {
  id: number; candidate_id: number; candidate_name: string
  original_filename?: string
  analysis?: {
    basic_info: any; education: any[]; work_experience: any[]
    skills: string[]; projects: any[]; certifications: string[]
  }
  match_analysis?: {
    overall_score: number; dimensions: Record<string, number>
    strengths: string[]; risks: string[]; recommended_questions: string[]
  }
  summary?: string; analyzed_at?: string
}

export const resumesApi = {
  upload: async (candidateId: number, file: File) => {
    const form = new FormData()
    form.append('candidate_id', String(candidateId))
    form.append('file', file)
    const res = await fetch(`${BASE}/resumes/upload`, { method: 'POST', body: form })
    return res.json()
  },
  analyze: (resumeId: number, jobDescription: string = '') => {
    const form = new FormData()
    form.append('job_description', jobDescription)
    return fetch(`${BASE}/resumes/${resumeId}/analyze`, { method: 'POST', body: form }).then(r => r.json()) as Promise<ResumeAnalysis>
  },
  getByCandidate: (candidateId: number) =>
    request<ResumeAnalysis>(`/resumes/candidate/${candidateId}`),
}

// ========== 问卷 ==========
export interface Questionnaire {
  id: number; candidate_id: number; title: string
  questions: any[]; status: string
  sent_at?: string; completed_at?: string; deadline?: string
}

export const questionnairesApi = {
  sendLink: (candidateId: number) =>
    request<{ status: string; questionnaire_id: number; link: string }>('/questionnaires/send-link', {
      method: 'POST', body: JSON.stringify({ candidate_id: candidateId })
    }),
  getByCandidate: (candidateId: number) =>
    request<Questionnaire[]>(`/questionnaires/candidate/${candidateId}`),
}

// ========== 面试 ==========
export interface Interview {
  id: number; candidate_id: number; candidate_name: string
  round: string; status: string; interviewers: string[]
  proposed_slots?: any[]; confirmed_start?: string; confirmed_end?: string
  location?: string; meeting_link?: string; feedback?: any
}

export const interviewsApi = {
  generateSlots: (data: {
    candidate_id: number; date_range_start: string; date_range_end: string
    duration_minutes?: number; round?: string
    working_hours_start?: string; working_hours_end?: string
  }) => request<{ interview_id: number; proposed_slots: any[] }>('/interviews/generate-slots', {
    method: 'POST', body: JSON.stringify({ interviewers: ['面试官'], date_range_start: data.date_range_start, date_range_end: data.date_range_end, ...data })
  }),
  confirmSlot: (data: { interview_id: number; selected_slot: any; location?: string; meeting_link?: string }) =>
    request<Interview>('/interviews/confirm-slot', { method: 'POST', body: JSON.stringify(data) }),
  submitFeedback: (data: { interview_id: number; interviewer: string; rating: number; strengths: string[]; weaknesses: string[]; decision: string; detail: string }) =>
    request('/interviews/feedback', { method: 'POST', body: JSON.stringify(data) }),
  getByCandidate: (candidateId: number) =>
    request<Interview[]>(`/interviews/candidate/${candidateId}`),
}

// ========== 制度 Agent ==========
export const policyApi = {
  chat: (data: { message: string; session_id?: string; candidate_id?: number }) =>
    request<{ session_id: string; answer: string; confidence: string; cited_sources: any[]; disclaimer?: string }>('/policy/chat', { method: 'POST', body: JSON.stringify(data) }),

  /** SSE 流式聊天 — 对接后端 /api/policy/chat/stream */
  chatStream: (data: { message: string; session_id?: string }, onToken: (text: string) => void, onEvent?: (type: string, payload: any) => void): Promise<void> => {
    return new Promise((resolve, reject) => {
      fetch(`${BASE}/policy/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).then(async (response) => {
        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: 'SSE error' }))
          reject(new Error(err.detail || `HTTP ${response.status}`))
          return
        }
        const reader = response.body?.getReader()
        if (!reader) { reject(new Error('No reader')); return }
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              // 存储事件类型，下一个 data 行配对使用
              const eventType = line.slice(7).trim()
              // 简单实现：event 和 data 配对
              ;(line as any)._eventType = eventType
            } else if (line.startsWith('data: ')) {
              try {
                const dataStr = line.slice(6)
                const payload = JSON.parse(dataStr)
                if (onEvent) {
                  onEvent('token', payload) // fallback, 用 token 类型
                }
                if (payload.text) {
                  onToken(payload.text)
                }
              } catch {
                // skip invalid JSON
              }
            }
          }
        }
        resolve()
      }).catch(reject)
    })
  },

  documents: {
    list: () => request<any[]>('/policy/documents'),
    upload: async (title: string, category: string, file: File) => {
      const form = new FormData()
      form.append('title', title); form.append('category', category); form.append('file', file)
      const res = await fetch(`${BASE}/policy/documents/upload`, { method: 'POST', body: form })
      return res.json()
    },
    delete: (id: number) => request(`/policy/documents/${id}`, { method: 'DELETE' }),
  },
  history: (sessionId: string) =>
    request<{ session_id: string; messages: any[] }>(`/policy/history/${sessionId}`),
}

// ========== 工作流 ==========
export const workflowApi = {
  status: (candidateId: number) => request<any>(`/workflow/status/${candidateId}`),
  autoProcess: (candidateId: number, jobDescription?: string) =>
    request<any>(`/workflow/auto-process/${candidateId}`, {
      method: 'POST', body: JSON.stringify({ job_description: jobDescription || '' })
    }),
  pipeline: () => request<any>('/workflow/pipeline'),
  talentPool: {
    list: (params?: { page?: number; page_size?: number; status?: string }) => {
      const q = new URLSearchParams()
      if (params?.page) q.set('page', String(params.page))
      if (params?.page_size) q.set('page_size', String(params.page_size))
      if (params?.status) q.set('status', params.status)
      return request<any>(`/workflow/talent-pool?${q}`)
    },
    get: (id: number) => request<any>(`/workflow/talent-pool/${id}`),
    contact: (id: number, note: string = '') =>
      request<any>(`/workflow/talent-pool/${id}/contact`, {
        method: 'PUT', body: JSON.stringify({ note })
      }),
    reactivate: (talentPoolId: number, position: string) =>
      request<any>('/workflow/talent-pool/reactivate', {
        method: 'POST', body: JSON.stringify({ talent_pool_id: talentPoolId, position })
      }),
  },
}

// ========== 试卷分析 ==========
export interface ExamAnalysis {
  id: number
  candidate_name: string
  candidate_phone?: string
  exam_title: string
  exam_score?: number
  exam_total?: number
  exam_duration?: number
  analysis_status: string  // pending / analyzing / completed / failed
  analysis_result?: {
    overall_score?: number
    knowledge_dimensions?: Record<string, number>
    strengths?: string[]
    weaknesses?: string[]
    suggestion?: string
    summary?: string
  }
  error_message?: string
  created_at: string
  analyzed_at?: string
}

export const examAnalysisApi = {
  list: (params?: { page?: number; page_size?: number }) => {
    const q = new URLSearchParams()
    if (params?.page) q.set('page', String(params.page))
    if (params?.page_size) q.set('page_size', String(params.page_size))
    return request<{ total: number; items: ExamAnalysis[]; page: number; page_size: number }>(`/exam-analysis?${q}`)
  },
}
export const dashboardApi = {
  stats: () => request<any>('/dashboard/stats'),
}