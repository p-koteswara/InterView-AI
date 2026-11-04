export type HealthResponse = {
  status: string;
  service: string;
  database: string;
};

export type EducationItem = {
  institution: string;
  degree: string | null;
  field_of_study: string | null;
  start_year: string | null;
  end_year: string | null;
  grade: string | null;
};

export type ExperienceItem = {
  company: string;
  role: string;
  duration: string | null;
  description: string[];
};

export type ProjectItem = {
  title: string;
  description: string | null;
  technologies: string[];
};

export type CandidateProfile = {
  name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  education: EducationItem[];
  work_experience: ExperienceItem[];
  technical_skills: string[];
  programming_languages: string[];
  frameworks_and_tools: string[];
  projects: ProjectItem[];
  certifications: string[];
  relevant_domains: string[];
};

export type ResumeUploadResponse = {
  candidate_id: string;
  filename: string;
  extracted_text: string;
  profile: CandidateProfile;
  created_at: string;
};

export type QuestionType = "technical" | "conceptual";
export type DifficultyLevel = "easy" | "medium" | "hard";

export type InterviewQuestion = {
  id: string;
  position: number;
  text: string;
  question_type: QuestionType;
  difficulty: DifficultyLevel;
  topic: string;
  rationale: string | null;
  source_document: string | null;
  source_section: string | null;
};

export type InterviewSession = {
  session_id: string;
  candidate_id: string;
  role: string;
  role_title: string;
  focus_skills: string[];
  created_at: string;
  questions: InterviewQuestion[];
};

export type AnswerRecord = {
  id: string;
  session_id: string;
  question_id: string;
  question_position: number;
  answer_text: string;
  created_at: string;
  updated_at: string;
};

export type SessionAnswers = {
  session_id: string;
  total_questions: number;
  answered_count: number;
  answers: AnswerRecord[];
};

/** Mirrors the limits enforced by the backend resume parser. */
export const MAX_RESUME_SIZE_BYTES = 10 * 1024 * 1024;
/** Mirrors MAX_ANSWER_LENGTH in the backend answer schema. */
export const MAX_ANSWER_LENGTH = 20000;
export const ALLOWED_RESUME_EXTENSIONS = [".pdf", ".txt"] as const;

export function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  return baseUrl.replace(/\/$/, "");
}

export async function readErrorMessage(response: Response, action: string): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail;
      }
      // FastAPI validation errors return an array of { msg, loc, ... } objects.
      if (Array.isArray(detail)) {
        const messages = detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : null,
          )
          .filter((message): message is string => Boolean(message));
        if (messages.length > 0) {
          return messages.join("; ");
        }
      }
    }
  } catch {
    // Response had no JSON body; fall back to the generic message below.
  }

  return `${action} failed with status ${response.status}`;
}

/** Fetch a JSON endpoint, turning transport and API errors into readable messages. */
async function requestJson<T>(url: string, init: RequestInit, action: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error(
      `Unable to reach the backend service at ${getApiBaseUrl()}. Ensure the FastAPI server is running.`,
    );
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, action));
  }

  return response.json() as Promise<T>;
}

export async function uploadResume(file: File): Promise<ResumeUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/api/resume/upload`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new Error(
      `Unable to reach the backend service at ${getApiBaseUrl()}. Ensure the FastAPI server is running.`,
    );
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Resume upload"));
  }

  return response.json() as Promise<ResumeUploadResponse>;
}

export async function fetchInterviewSession(sessionId: string): Promise<InterviewSession> {
  return requestJson<InterviewSession>(
    `${getApiBaseUrl()}/api/interviews/${encodeURIComponent(sessionId)}`,
    { cache: "no-store" },
    "Loading the interview",
  );
}

export async function fetchSessionAnswers(sessionId: string): Promise<SessionAnswers> {
  return requestJson<SessionAnswers>(
    `${getApiBaseUrl()}/api/interviews/${encodeURIComponent(sessionId)}/answers`,
    { cache: "no-store" },
    "Loading saved answers",
  );
}

export async function submitAnswer(
  sessionId: string,
  questionId: string,
  answerText: string,
): Promise<AnswerRecord> {
  return requestJson<AnswerRecord>(
    `${getApiBaseUrl()}/api/interviews/${encodeURIComponent(sessionId)}/questions/${encodeURIComponent(questionId)}/answers`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_text: answerText }),
    },
    "Saving the answer",
  );
}

export type AnswerEvaluation = {
  id: string;
  answer_id: string;
  session_id: string;
  question_id: string;
  question_position: number;
  technical_score: number;
  relevance_score: number;
  depth_score: number;
  clarity_score: number;
  overall_score: number;
  feedback: string;
  improvements: string[];
  created_at: string;
  updated_at: string;
};

export type InterviewReport = {
  id: string;
  session_id: string;
  candidate_id: string;
  candidate_name: string;
  role: string;
  role_title: string;
  interview_date: string | null;
  question_count: number;
  answered_count: number;
  overall_score: number;
  strengths: string[];
  weaknesses: string[];
  recommended_topics: string[];
  assessment: string;
  evaluations: AnswerEvaluation[];
};

export type SessionEvaluationsResponse = {
  session_id: string;
  total_questions: number;
  answered_count: number;
  evaluated_count: number;
  evaluations: AnswerEvaluation[];
};

export async function fetchInterviewEvaluations(sessionId: string): Promise<SessionEvaluationsResponse> {
  return requestJson<SessionEvaluationsResponse>(
    `${getApiBaseUrl()}/api/interviews/${encodeURIComponent(sessionId)}/evaluations`,
    { cache: "no-store" },
    "Loading answer evaluations",
  );
}

export async function evaluateInterview(sessionId: string): Promise<SessionEvaluationsResponse> {
  let response: Response;
  try {
    response = await fetch(
      `${getApiBaseUrl()}/api/interviews/${encodeURIComponent(sessionId)}/evaluations`,
      { method: "POST" },
    );
  } catch {
    throw new Error(
      `Unable to reach the backend service at ${getApiBaseUrl()}. Ensure the FastAPI server is running.`,
    );
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Evaluating the interview answers"));
  }

  return response.json() as Promise<SessionEvaluationsResponse>;
}

export async function fetchInterviewReport(sessionId: string): Promise<InterviewReport> {
  return requestJson<InterviewReport>(
    `${getApiBaseUrl()}/api/interviews/${encodeURIComponent(sessionId)}/report`,
    { cache: "no-store" },
    "Loading the interview report",
  );
}

export async function generateInterviewReport(sessionId: string): Promise<InterviewReport> {
  let response: Response;
  try {
    response = await fetch(
      `${getApiBaseUrl()}/api/interviews/${encodeURIComponent(sessionId)}/report`,
      { method: "POST" },
    );
  } catch {
    throw new Error(
      `Unable to reach the backend service at ${getApiBaseUrl()}. Ensure the FastAPI server is running.`,
    );
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Generating the interview report"));
  }

  return response.json() as Promise<InterviewReport>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const url = `${getApiBaseUrl()}/api/health`;
  const response = await fetch(url, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }

  return response.json() as Promise<HealthResponse>;
}

