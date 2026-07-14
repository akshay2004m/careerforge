const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

/** Exposed for error messages / debugging */
export function getApiBase() {
  return API_BASE;
}

export type AtsBreakdown = {
  keyword_coverage?: {
    score?: number;
    max?: number;
    ratio?: number;
    ratio_pct?: number;
    matched?: string[];
    missing?: string[];
    total_keywords?: number;
  };
  sections?: { score?: number; max?: number; present?: string[]; missing?: string[] };
  quantified_impact?: { score?: number; max?: number; evidence_count?: number };
  action_verbs?: { score?: number; max?: number; unique_verbs?: string[] };
  length?: { score?: number; max?: number; word_count?: number; band?: string };
  semantic?: {
    score?: number;
    max?: number;
    avg_similarity?: number;
    best_similarity?: number;
    available?: boolean;
  };
  llm_qualitative?: {
    score?: number;
    max?: number;
    fit?: number;
    available?: boolean;
  };
};

export type OptimizeResult = {
  tailored_resume: string | Record<string, unknown>;
  ats_score: number;
  cover_letter: string;
  key_improvements?: string[];
  missing_keywords?: string[];
  matched_keywords?: string[];
  message: string;
  tailored_resume_id?: number;
  skills?: string[];
  application_id?: number;
  ats_breakdown?: AtsBreakdown;
  ats_summary?: string[];
  ats_method?: string;
  score_before?: number | null;
  score_delta?: number | null;
  layer_scores?: {
    rules?: number;
    semantic?: number;
    llm?: number;
    rules_max?: number;
    semantic_max?: number;
    llm_max?: number;
  };
  /** Interview-friendly score cards */
  display_scores?: {
    overall?: number;
    keyword_match?: number;
    structure_formatting?: number;
    relevance?: number;
    suggestions?: string[];
    cards?: { key: string; label: string; value: number; unit: string }[];
  };
  suggestions?: string[];
  qualitative_summary?: string;
  strengths?: string[];
  rubric_scores?: {
    keyword_alignment?: number;
    structure_clarity?: number;
    role_relevance?: number;
  };
};

export type UserProfile = {
  id: number;
  email: string;
  name: string;
  headline?: string | null;
  location?: string | null;
};

export type ResumeSummary = {
  id: number;
  title?: string | null;
  is_primary?: boolean;
  created_at?: string | null;
  preview?: string | null;
  file_path?: string | null;
};

export type TailoredSummary = {
  id: number;
  resume_id: number;
  ats_score?: number | null;
  job_preview?: string | null;
  created_at?: string | null;
};

export type Application = {
  id: number;
  company: string;
  role: string;
  status: string;
  job_description?: string | null;
  notes?: string | null;
  resume_id?: number | null;
  tailored_resume_id?: number | null;
  ats_score?: number | null;
  skills?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type AnalyticsSummary = {
  total_applications: number;
  by_status: Record<string, number>;
  total_resumes: number;
  total_optimizations: number;
  average_ats: number;
  best_ats: number;
  success_rate: number;
  top_companies: { company: string; count: number }[];
  recent_activity: {
    type: string;
    id: number;
    title: string;
    status: string;
    at?: string | null;
  }[];
};

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function clearAuth() {
  localStorage.removeItem("token");
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join(", ");
    }
    return data.message || res.statusText || "Request failed";
  } catch {
    return res.statusText || "Request failed";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  const isAuthForm =
    path === "/api/auth/login" || path === "/api/auth/signup";

  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  // Never attach a stale token to login/signup — it confuses debugging and
  // can interact badly with intermediate proxies.
  if (token && !isAuthForm) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
  } catch {
    throw new Error(
      `Cannot reach the API at ${API_BASE}. Start the backend (port 8002) and try again.`
    );
  }

  if (res.status === 401) {
    // Don't treat failed login/signup as "session expired"
    if (!isAuthForm) {
      clearAuth();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/auth")) {
        window.location.href = "/auth/login";
      }
      throw new Error("Session expired. Please log in again.");
    }
    throw new Error(await parseError(res));
  }

  if (!res.ok) {
    throw new Error(await parseError(res));
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  signup: (body: { name: string; email: string; password: string }) =>
    request<{ access_token: string; token_type: string }>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  login: (body: { email: string; password: string }) =>
    request<{ access_token: string; token_type: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  me: () => request<UserProfile>("/api/auth/me"),

  updateProfile: (body: { name?: string; headline?: string; location?: string }) =>
    request<UserProfile>("/api/auth/me", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  changePassword: (body: { current_password: string; new_password: string }) =>
    request<{ message: string }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  uploadResume: async (file: File, opts?: { title?: string; set_primary?: boolean }) => {
    const formData = new FormData();
    formData.append("file", file);
    if (opts?.title) formData.append("title", opts.title);
    if (opts?.set_primary != null) formData.append("set_primary", String(opts.set_primary));
    return request<{
      resume_id: number;
      message: string;
      preview?: string;
      title?: string;
      is_primary?: boolean;
    }>("/api/resume/upload", { method: "POST", body: formData });
  },

  listResumes: () => request<ResumeSummary[]>("/api/resume/list"),

  updateResume: (id: number, body: { title?: string; is_primary?: boolean }) =>
    request<ResumeSummary>(`/api/resume/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteResume: (id: number) =>
    request<{ message: string }>(`/api/resume/${id}`, { method: "DELETE" }),

  optimize: (body: {
    resume_id: number;
    job_description: string;
    create_application?: boolean;
    company?: string;
    role?: string;
  }) =>
    request<OptimizeResult>("/api/optimize", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  history: () => request<TailoredSummary[]>("/api/history"),

  interviewQuestions: (body: {
    job_description: string;
    count?: number;
    include_common?: boolean;
  }) =>
    request<{
      questions: string[];
      common?: string[];
      role_specific?: string[];
    }>("/api/interview/questions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  interviewFeedback: (body: { job_description: string; transcript: string }) =>
    request<{
      feedback: string;
      score: number;
      strengths: string[];
      improvements: string[];
    }>("/api/interview/feedback", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** STT health (faster-whisper + ffmpeg availability) */
  sttHealth: () =>
    request<{
      ok: boolean;
      engine: string;
      model?: string;
      device?: string;
      loaded?: boolean;
      ffmpeg?: boolean;
      ws_path?: string;
    }>("/api/interview/stt/health"),

  /** Preload Whisper model (first call may be slow) */
  sttWarmup: () =>
    request<{ ok: boolean; message?: string; model?: string }>(
      "/api/interview/stt/warmup",
      { method: "POST" }
    ),

  extractSkills: (job_description: string) =>
    request<{ skills: string[]; must_have: string[]; nice_to_have: string[] }>(
      "/api/skills/extract",
      {
        method: "POST",
        body: JSON.stringify({ job_description }),
      }
    ),

  listApplications: (status?: string) =>
    request<Application[]>(
      status ? `/api/applications?status=${encodeURIComponent(status)}` : "/api/applications"
    ),

  createApplication: (body: {
    company: string;
    role: string;
    status?: string;
    job_description?: string;
    notes?: string;
    resume_id?: number;
    ats_score?: number;
    skills?: string[];
  }) =>
    request<Application>("/api/applications", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateApplication: (
    id: number,
    body: Partial<{
      company: string;
      role: string;
      status: string;
      job_description: string;
      notes: string;
      resume_id: number;
      ats_score: number;
      skills: string[];
    }>
  ) =>
    request<Application>(`/api/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteApplication: (id: number) =>
    request<{ message: string }>(`/api/applications/${id}`, { method: "DELETE" }),

  analytics: () => request<AnalyticsSummary>("/api/analytics/summary"),


  deleteOptimization: async (id: number) => {
    return request<{ message: string }>(`/api/optimize/${id}`, {
      method: "DELETE",
    });
  },
};

export function asResumeText(value: string | Record<string, unknown> | undefined): string {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (typeof value.tailored_resume === "string") return value.tailored_resume;
  return JSON.stringify(value, null, 2);
}
