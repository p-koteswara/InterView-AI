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

/** Mirrors the limits enforced by the backend resume parser. */
export const MAX_RESUME_SIZE_BYTES = 10 * 1024 * 1024;
export const ALLOWED_RESUME_EXTENSIONS = [".pdf", ".txt"] as const;

export function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  return baseUrl.replace(/\/$/, "");
}

async function readErrorMessage(response: Response): Promise<string> {
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

  return `Resume upload failed with status ${response.status}`;
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
    throw new Error(await readErrorMessage(response));
  }

  return response.json() as Promise<ResumeUploadResponse>;
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

