import { getApiBaseUrl } from "./api";

import type { CandidateProfile, EducationItem, ExperienceItem, ProjectItem, ResumeUploadResponse } from "./api";

/** A job role from the backend role catalog. */
export type JobRole = {
  slug: string;
  title: string;
  category: string;
  description: string;
  keySkills: string[];
};

/** Raw role shape as serialised by the backend (snake_case ``key_skills``). */
type RawJobRole = {
  slug: string;
  title: string;
  category: string;
  description: string;
  keySkills?: string[];
  key_skills?: string[];
};

/** Fetches the role catalog from the backend. */
export async function fetchJobRoles(): Promise<JobRole[]> {
  return fetch(`${getApiBaseUrl()}/api/roles`, { method: "GET" })
    .then((resp) => {
      if (!resp.ok) throw new Error(`Failed to load roles: ${resp.status}`);
      return resp.json();
    })
    .then((data) => {
      const rawRoles: RawJobRole[] = Array.isArray(data?.roles) ? data.roles : [];
      return rawRoles.map((raw) => ({
        slug: raw.slug,
        title: raw.title,
        category: raw.category,
        description: raw.description,
        keySkills: raw.keySkills ?? raw.key_skills ?? [],
      })) as JobRole[];
    })
    .catch((err) => {
      console.error(err);
      return [];
    });
}

/** Resolves the @/* path alias to the real src/* directory. */
export const srcAlias = "../../src";

/** Default number of interview questions to generate. */
export const DEFAULT_QUESTION_COUNT = 6;
/** Minimum allowed question count. */
export const MIN_QUESTION_COUNT = 1;
/** Maximum allowed question count. */
export const MAX_QUESTION_COUNT = 15;