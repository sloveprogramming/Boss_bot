import axios from "axios";
import type {
  Candidate, Page, ResumeAnalysis, ResumeUploadResponse, DashboardStats,
  Questionnaire, Interview, InterviewSlotResponse, TalentPoolItem,
  PipelineOverview, ExamAnalysisItem, CalendarInterviewResponse,
  QuestionnaireOverviewItem, ScoringInsights, ScoringIteration, User,
} from "../types";

export const TOKEN_KEY = "recruit_token";
export const USER_KEY = "recruit_user";

export const getToken = () => localStorage.getItem(TOKEN_KEY) ?? "";
export const setAuth = (token: string, user: User) => {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
};
export const clearAuth = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
};
export const getCachedUser = (): User | null => {
  try { return JSON.parse(localStorage.getItem(USER_KEY) ?? "null"); } catch { return null; }
};

// ===== 主后端 axios 实例（前后端分离：所有数据只走 HTTP API） =====
export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "", // 开发态走 Vite 代理；生产可配环境变量
  timeout: 60_000,
});

http.interceptors.request.use((cfg) => {
  const t = getToken();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401 && location.pathname !== "/login") {
      clearAuth();
      location.href = "/login";
    }
    return Promise.reject(err);
  },
);

export const errDetail = (e: unknown): string => {
  const r = (e as { response?: { data?: { detail?: string } } })?.response?.data;
  if (typeof r?.detail === "string") return r.detail;
  try { return JSON.stringify(r ?? e); } catch { return String(e); }
};

// ===== RAG 服务（独立 :18003） =====
const RAG_BASE = import.meta.env.VITE_RAG_BASE || "/rag-api";

/** POST SSE 流式请求，逐块回调；返回完整文本 */
export async function postSSE(
  url: string,
  body: Record<string, unknown>,
  onDelta: (text: string) => void,
): Promise<string> {
  const full = url.startsWith("/api/") ? RAG_BASE + url.slice(4) : url; // /api/chat/... → RAG 服务
  const res = await fetch(full, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) throw new Error(`请求失败 (${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = ""; let answer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const s = line.trim();
      if (!s.startsWith("data:")) continue;
      const payload = s.slice(5).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        const j = JSON.parse(payload);
        // 兼容多种字段：answer / delta / content / token
        const delta = j.answer ?? j.delta ?? j.content ?? j.token ?? "";
        if (delta) { answer += delta; onDelta(answer); }
        if (j.sources) onDelta(answer); // 触发重绘
      } catch { /* 非 JSON 心跳忽略 */ }
    }
  }
  return answer;
}

// ===== Auth =====
export const api = {
  login: (username: string, password: string) =>
    http.post<{ access_token: string; username: string; role: string }>("/api/auth/login", { username, password }),
  register: (data: { username: string; password: string; role?: string; email?: string }) =>
    http.post<User>("/api/auth/register", data),
  me: () => http.get<User>("/api/auth/me"),

  dashboardStats: () => http.get<DashboardStats>("/api/dashboard/stats"),

  candidates: {
    list: (params: { page?: number; page_size?: number; status?: string; search?: string }) =>
      http.get<Page<Candidate>>("/api/candidates", { params }),
    get: (id: number) => http.get<Candidate>(`/api/candidates/${id}`),
    create: (data: Partial<Candidate>) => http.post<Candidate>("/api/candidates", data),
    update: (id: number, data: Partial<Candidate>) => http.put<Candidate>(`/api/candidates/${id}`, data),
    remove: (id: number) => http.delete(`/api/candidates/${id}`),
  },

  resumes: {
    upload: (candidateId: number, file: File) => {
      const fd = new FormData();
      fd.append("candidate_id", String(candidateId));
      fd.append("file", file);
      return http.post<ResumeUploadResponse>("/api/resumes/upload", fd);
    },
    analyze: (resumeId: number, jd = "") => {
      const fd = new FormData();
      fd.append("job_description", jd);
      return http.post<ResumeAnalysis>(`/api/resumes/${resumeId}/analyze`, fd);
    },
    getByCandidate: (cid: number) =>
      http.get<ResumeAnalysis>(`/api/resumes/candidate/${cid}`),
  },

  workflow: {
    start: (cid: number) => http.post(`/api/workflow/start/${cid}`),
    autoProcess: (cid: number) => http.post(`/api/workflow/auto-process/${cid}`),
    pipeline: () => http.get<PipelineOverview>("/api/workflow/pipeline"),
    talentPool: (params: { page?: number; page_size?: number }) =>
      http.get<Page<TalentPoolItem>>("/api/workflow/talent-pool", { params }),
    reactivate: (data: { talent_pool_id: number; position: string }) =>
      http.post<TalentPoolItem>("/api/workflow/talent-pool/reactivate", data),
    contact: (poolId: number, note: string) =>
      http.put(`/api/workflow/talent-pool/${poolId}/contact`, { contact_note: note }),
  },

  interviews: {
    generateSlots: (data: Record<string, unknown>) =>
      http.post<InterviewSlotResponse>("/api/interviews/generate-slots", data),
    confirmSlot: (data: Record<string, unknown>) =>
      http.post<Interview>("/api/interviews/confirm-slot", data),
    feedback: (data: Record<string, unknown>) => http.post("/api/interviews/feedback", data),
    cancel: (id: number) => http.post(`/api/interviews/${id}/cancel`),
    byCandidate: (cid: number) => http.get<Interview[]>(`/api/interviews/candidate/${cid}`),
    calendar: (params: { start: string; end: string; candidate_id?: number }) =>
      http.get<CalendarInterviewResponse>("/api/interviews/calendar", { params }),
  },

  questionnaires: {
    sendLink: (candidateId: number) =>
      http.post("/api/questionnaires/send-link", { candidate_id: candidateId }),
    byCandidate: (cid: number) => http.get<Questionnaire[]>(`/api/questionnaires/candidate/${cid}`),
    list: (params: { page?: number; page_size?: number; status?: string; search?: string }) =>
      http.get<Page<QuestionnaireOverviewItem>>("/api/questionnaires", { params }),
  },

  policyDocs: {
    upload: (title: string, category: string, file: File) => {
      const fd = new FormData();
      fd.append("title", title);
      fd.append("category", category);
      fd.append("file", file);
      return http.post("/api/policy/documents/upload", fd);
    },
    list: () => http.get("/api/policy/documents"),
    remove: (id: number) => http.delete(`/api/policy/documents/${id}`),
  },
  ragChatStream: "/api/chat/stream",

  exam: {
    list: (params: { page?: number; page_size?: number }) =>
      http.get<Page<ExamAnalysisItem>>("/api/exam-analysis", { params }),
  },

  scoring: {
    insights: () => http.get<ScoringInsights>("/api/scoring/insights"),
    iterations: (limit = 20) =>
      http.get<ScoringIteration[]>("/api/scoring/iterations", { params: { limit } }),
    applyIteration: (data: { to_weights: Record<string, number>; category?: string; note?: string }) =>
      http.post<ScoringIteration & { warning?: string }>("/api/scoring/iterations", data),
  },
};
