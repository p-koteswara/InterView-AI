import type { InterviewQuestion } from "@/lib/api";
import type { JobRole } from "@/lib/job-roles";
import { getApiBaseUrl } from "@/lib/api";
import { readErrorMessage } from "@/lib/api";
import { MAX_QUESTION_COUNT } from "@/lib/job-roles";

/**
 * Generates an interview for a candidate (identified by their stored profile)
 * and a job role chosen by the interviewer. The response carries the new
 * session ID the caller resolves to the interview-taking page.
 */
export async function generateInterview(
  candidateId: string,
  role: JobRole,
  questionCount: number,
): Promise<{
  sessionId: string;
  candidateId: string;
  role: JobRole;
  roleTitle: string;
  focusSkills: string[];
  questions: InterviewQuestion[];
}> {
  if (questionCount < 1 || questionCount > MAX_QUESTION_COUNT) {
    throw new Error(
      `questionCount must be between 1 and ${MAX_QUESTION_COUNT}, got ${questionCount}`,
    );
  }

  const response = await fetch(`${getApiBaseUrl()}/api/interviews`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      candidate_id: candidateId,
      role: role.slug,
      question_count: questionCount,
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Generating the interview"));
  }

  const data = (await response.json()) as {
    session_id: string;
    candidate_id: string;
    role: string;
    role_title: string;
    focus_skills: string[];
    questions: InterviewQuestion[];
  };

  return {
    sessionId: data.session_id,
    candidateId: data.candidate_id,
    role: role,
    roleTitle: data.role_title,
    focusSkills: data.focus_skills,
    questions: data.questions,
  };
}