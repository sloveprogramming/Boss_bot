// ===== 与后端契约对齐的全局类型 =====

export interface User {
  id: number;
  username: string;
  role: "admin" | "hr" | "interviewer" | "candidate" | string;
  email?: string | null;
  /** 显示姓名（可空；空则各展示处回退 username） */
  display_name?: string | null;
  is_active: boolean;
}

export type CandidateStatus =
  | "new" | "analyzed" | "talent_pool" | "q_sent" | "q_done"
  | "scheduled" | "interviewed" | "hired" | "rejected" | "archived";

export interface Candidate {
  id: number;
  name: string;
  phone?: string | null;
  email?: string | null;
  source: string;
  position: string;
  experience_years?: number | null;
  job_category?: string | null;
  status: CandidateStatus;
  match_score?: number | null;
  tags: string[];
  owner_user_id?: number | null; // 归属负责人（HR/管理员）用户 id；null=未指派
  talent_pool_id?: number | null;
  created_at: string;
  updated_at: string;
}

/** 改派候选人负责人（PUT /api/candidates/{id}/owner）的返回 */
export interface OwnerReassignResult {
  previous_owner_user_id: number | null;
  previous_owner_name: string | null;
  owner_user_id: number;
  owner_name: string;
}

export interface Page<T> {
  total: number;
  items: T[];
  page: number;
  page_size: number;
}

export interface MatchAnalysis {
  overall_score: number;
  dimensions: Record<string, unknown>;
  strengths: string[];
  risks: string[];
  recommended_questions: string[];
}

export interface ResumeUploadResponse {
  id: number;
  candidate_id: number;
  original_filename: string;
  status?: string;
  message?: string;
}

export interface ResumeBasicPreview {
  name: string;
  phone: string;
  email: string;
  location: string;
  experience_years?: number | null;
  suggested_position: string;
  skills: string[];
}

export interface ResumeQuickAddResponse {
  candidate_id: number;
  candidate_name: string;
  resume_id: number;
  status: string;
  warning?: string | null;
}

export interface ResumeAnalysis {
  id: number;
  candidate_id: number;
  candidate_name?: string;
  original_filename?: string | null;
  analysis?: {
    basic_info?: Record<string, string>;
    education?: Record<string, string>[];
    work_experience?: Record<string, string>[];
    skills?: string[];
    projects?: Record<string, string>[];
    certifications?: string[];
  } | null;
  match_analysis?: MatchAnalysis | null;
  summary?: string | null;
  analyzed_at?: string | null;
}

export interface DashboardStats {
  total_candidates: number;
  today_new: number;
  average_match_score: number;
  hire_rate: number;
  status_distribution: Record<string, number>;
  weekly_trend: { date: string; count: number }[];
}

export interface TimeSlot {
  date: string;
  start_time: string;
  end_time: string;
}

export interface InterviewSlotResponse {
  interview_id: number;
  proposed_slots: TimeSlot[];
}

export interface Interview {
  id: number;
  candidate_id: number;
  candidate_name?: string;
  round: string;
  status: string;
  interviewers: string[];
  proposed_slots?: TimeSlot[] | null;
  confirmed_start?: string | null;
  confirmed_end?: string | null;
  location?: string | null;
  meeting_link?: string | null;
  feedback?: Record<string, unknown> | null;
  ai_summary?: string | null;
}

export interface CalendarInterviewItem {
  id: number;
  candidate_id: number;
  candidate_name: string;
  position?: string;
  round: string;
  status: string;
  confirmed_start?: string | null;
  confirmed_end?: string | null;
  location?: string | null;
  meeting_link?: string | null;
  interviewers?: string[];
  ai_summary?: string | null;
  feedback?: Record<string, unknown> | null;
  has_feedback: boolean;
}

export interface CalendarInterviewResponse {
  items: CalendarInterviewItem[];
  unconfirmed: {
    id: number;
    candidate_id: number;
    candidate_name: string;
    round: string;
    status: string;
    proposed_slots: TimeSlot[];
  }[];
}

export interface Questionnaire {
  id: number;
  candidate_id: number;
  title: string;
  questions: { id: string; type: string; question: string; options?: string[] }[];
  status: string;
  sent_at?: string | null;
  completed_at?: string | null;
  deadline?: string | null;
}

export interface QuestionnaireOverviewItem {
  id: number;
  candidate_id: number;
  candidate_name: string;
  candidate_phone?: string | null;
  position: string;
  title: string;
  status: string;
  sent_at?: string | null;
  completed_at?: string | null;
  deadline?: string | null;
}

export interface TalentPoolItem {
  id: number;
  candidate_id: number;
  original_position: string;
  match_score?: number | null;
  strengths: string[];
  risks: string[];
  pool_reason?: string | null;
  suitable_positions: string[];
  skills: string[];
  status: string;
  contacted_at?: string | null;
  contact_note?: string | null;
  created_at: string;
}

export interface PipelineOverview {
  total: number;
  status_counts: Record<string, number>;
  stages: Record<string, number>;
  recent: {
    id: number; name: string; position: string;
    status: CandidateStatus; match_score?: number | null; created_at: string;
  }[];
}

export interface ExamAnalysisItem {
  id: number;
  candidate_name: string;
  candidate_phone?: string | null;
  candidate_position?: string | null;
  external_id?: string | null;
  exam_title: string;
  exam_score?: number | null;
  exam_total?: number | null;
  exam_duration?: number | null;
  analysis_status: string;
  analysis_result?: Record<string, unknown> | null;
  raw_data?: { eventBody?: unknown; answerDetail?: ExamAnswerDetail } | null;
  error_message?: string | null;
  created_at: string;
  analyzed_at?: string | null;
}

/** 试卷逐题作答明细（来自 Workmenul answerDetail） */
export interface ExamAnswerQuestion {
  questionContent?: string;
  questionType?: string;
  options?: Record<string, string> | null;
  score?: number | null;
  rightAnswers?: string | string[] | null;
  userAnswer?: string | null;
  realScore?: number | null;
  isCorrect?: boolean | null;
}

export interface ExamAnswerDetail {
  totalQuestions?: number;
  correctCount?: number;
  wrongCount?: number;
  questions?: ExamAnswerQuestion[];
}

// ===== 评分优化（原 LLM 监控栏） =====
export interface DimensionStat {
  key: string;
  label: string;
  weight: number;
  pass_n: number;
  reject_n: number;
  pass_avg?: number | null;
  reject_avg?: number | null;
  gap?: number | null;
}

export interface BucketRow {
  bucket: string;
  total: number;
  passed: number;
  pass_rate: number;
}

export interface InversionInfo {
  lower_bucket: string;
  upper_bucket: string;
  detail: string;
}

export interface ScoringSample {
  candidate_id: number;
  candidate_name: string;
  position: string;
  job_category?: string | null;
  outcome: "pass" | "reject";
  score?: number | null;
  dims: Record<string, number>;
  source?: string;
}

export interface ScoringInsights {
  generated_at: string;
  labeled_total: number;
  passed: number;
  pass_rate?: number | null;
  current_weights: Record<string, number>;
  suggested_weights?: Record<string, number> | null;
  dimension_stats: DimensionStat[];
  buckets: BucketRow[];
  inversions: InversionInfo[];
  recent_samples: ScoringSample[];
  suggestions: string[];
  note: string;
}

export interface ScoringIteration {
  id: number;
  category: string;
  from_weights: Record<string, number>;
  to_weights: Record<string, number>;
  note?: string | null;
  applied_by?: string | null;
  created_at: string;
}

// 候选人状态 → 中文标签 & 颜色
export const STATUS_META: Record<CandidateStatus, { label: string; cls: string }> = {
  new:         { label: "新候选人",   cls: "bg-slate-100 text-slate-600" },
  analyzed:    { label: "已分析",     cls: "bg-blue-50 text-blue-600" },
  talent_pool: { label: "人才池",     cls: "bg-amber-50 text-amber-600" },
  q_sent:      { label: "问卷已发",   cls: "bg-purple-50 text-purple-600" },
  q_done:      { label: "问卷完成",   cls: "bg-violet-50 text-violet-700" },
  scheduled:   { label: "已排期",     cls: "bg-cyan-50 text-cyan-600" },
  interviewed: { label: "已面试",     cls: "bg-indigo-50 text-indigo-600" },
  hired:       { label: "已录用",     cls: "bg-emerald-50 text-emerald-600" },
  rejected:    { label: "已拒绝",     cls: "bg-rose-50 text-rose-600" },
  archived:    { label: "已归档",     cls: "bg-slate-100 text-slate-400" },
};

export const statusMeta = (s: string) =>
  STATUS_META[s as CandidateStatus] ?? { label: s, cls: "bg-slate-100 text-slate-600" };

// ===== 制度问答：账号会话历史（后端 /api/policy） =====
export interface PolicyChatSession {
  session_id: string;
  title: string;
  last_preview: string;
  count: number;
}

export interface PolicyChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

// ===== 可配置邮件模板 =====
export type TemplateCategory = "questionnaire" | "interview" | "result" | "other";

export interface EmailTemplate {
  id: number;
  code: string;
  name: string;
  category: TemplateCategory;
  subject: string;
  body: string;
  is_system: boolean;
  is_active: boolean;
  created_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TemplateDraft {
  name: string;
  code?: string | null;
  category: TemplateCategory;
  subject: string;
  body: string;
  used_variables: string[];
}

export interface TemplatePreviewResult {
  subject: string;
  body: string;
  remaining_placeholders: string[];
}

export const TEMPLATE_CATEGORY_META: Record<TemplateCategory, { label: string; cls: string }> = {
  questionnaire: { label: "问卷类",   cls: "bg-purple-50 text-purple-600" },
  interview:     { label: "面试类",   cls: "bg-cyan-50 text-cyan-600" },
  result:        { label: "结果通知", cls: "bg-emerald-50 text-emerald-600" },
  other:         { label: "其他",     cls: "bg-slate-100 text-slate-600" },
};

export const templateCategoryLabel = (c: string): string =>
  (TEMPLATE_CATEGORY_META[c as TemplateCategory]?.label) ?? c;

// ===== 可配置岗位 JD 库（简历分析自动套用） =====
export interface PositionJd {
  id: number;
  position: string;
  aliases: string;
  category: string;
  responsibilities: string;
  requirements: string;
  salary: string;
  is_system: boolean;
  is_active: boolean;
  created_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PositionJdMatch {
  matched: boolean;
  position: string;
  jd: string;
  row: PositionJd | null;
}

/** 岗位 JD 内置分类配色（自定义分类在前端回退为「其他」样式） */
export const JD_CATEGORY_META: Record<string, { label: string; cls: string }> = {
  "采购供应链": { label: "采购供应链", cls: "bg-orange-50 text-orange-600" },
  "销售":       { label: "销售",       cls: "bg-cyan-50 text-cyan-600" },
  "市场":       { label: "市场",       cls: "bg-violet-50 text-violet-600" },
  "运营":       { label: "运营",       cls: "bg-blue-50 text-blue-600" },
  "研发":       { label: "研发",       cls: "bg-amber-50 text-amber-600" },
  "职能":       { label: "职能",       cls: "bg-slate-100 text-slate-600" },
  "other":      { label: "其他",       cls: "bg-slate-100 text-slate-600" },
};

export const JD_CATEGORY_KEYS = ["采购供应链", "销售", "市场", "运营", "研发", "职能"];

export const jdCategoryLabel = (c: string): string =>
  JD_CATEGORY_META[c]?.label ?? (c && c !== "other" ? c : "未分类");
