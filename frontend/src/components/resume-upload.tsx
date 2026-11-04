"use client";

import { useRef, useState, useEffect, useMemo, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  ALLOWED_RESUME_EXTENSIONS,
  MAX_RESUME_SIZE_BYTES,
  uploadResume,
  type EducationItem,
  type ExperienceItem,
  type ProjectItem,
  type ResumeUploadResponse,
} from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import {
  DEFAULT_QUESTION_COUNT,
  MAX_QUESTION_COUNT,
  MIN_QUESTION_COUNT,
  fetchJobRoles,
  type JobRole,
} from "@/lib/job-roles";
import { generateInterview } from "@/lib/generate-interview";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function validateFile(file: File): string | null {
  const lowerName = file.name.toLowerCase();
  const extensionSupported = ALLOWED_RESUME_EXTENSIONS.some((ext) => lowerName.endsWith(ext));

  if (!extensionSupported) {
    return `Unsupported file format "${file.name}". Only PDF and TXT files are accepted.`;
  }
  if (file.size === 0) {
    return "The selected file is empty (0 bytes).";
  }
  if (file.size > MAX_RESUME_SIZE_BYTES) {
    return `File size exceeds the 10 MB limit (${formatBytes(file.size)}).`;
  }
  return null;
}

export function ResumeUpload() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResumeUploadResponse | null>(null);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setFile(selected);
    setError(null);
    setResult(null);
  }

  function handleClear() {
    setFile(null);
    setError(null);
    setResult(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || uploading) return;

    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setResult(null);
      return;
    }

    setUploading(true);
    setError(null);
    setResult(null);

    try {
      const data = await uploadResume(file);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume upload failed unexpectedly.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="w-full space-y-6">
      <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <div className="pb-4 border-b border-slate-100 dark:border-slate-800">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Upload Resume
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            PDF or TXT, up to 10 MB. Text is extracted and the candidate profile is generated
            automatically.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div className="rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                  {file ? file.name : "No file selected"}
                </p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {file
                    ? `${formatBytes(file.size)} · ${file.name.split(".").pop()?.toUpperCase() ?? ""}`
                    : "Accepted formats: .pdf, .txt"}
                </p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <label
                  htmlFor="resume-file"
                  className={`inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer ${
                    uploading ? "opacity-50 pointer-events-none" : ""
                  }`}
                >
                  Choose file
                </label>
                <input
                  id="resume-file"
                  ref={inputRef}
                  type="file"
                  accept=".pdf,.txt,application/pdf,text/plain"
                  onChange={handleFileChange}
                  disabled={uploading}
                  className="sr-only"
                />

                {file && !uploading && (
                  <button
                    type="button"
                    onClick={handleClear}
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>
          </div>

          {error && (
            <div
              role="alert"
              className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-sm text-rose-800 dark:text-rose-200"
            >
              <p className="font-medium">Upload failed</p>
              <p className="mt-1 text-xs text-rose-700 dark:text-rose-300">{error}</p>
            </div>
          )}

          {uploading && (
            <div
              role="status"
              className="p-4 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-900"
            >
              <div className="flex items-center gap-3">
                <span className="h-3.5 w-3.5 rounded-full border-2 border-indigo-300 border-t-indigo-600 dark:border-indigo-800 dark:border-t-indigo-400 animate-spin" />
                <div>
                  <p className="text-sm font-medium text-indigo-800 dark:text-indigo-200">
                    Parsing resume and extracting profile…
                  </p>
                  <p className="mt-0.5 text-xs text-indigo-700 dark:text-indigo-300">
                    This can take up to 30 seconds.
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!file || uploading}
              className="inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg text-white bg-indigo-600 hover:bg-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed transition cursor-pointer"
            >
              {uploading ? "Analyzing…" : "Upload & Extract Profile"}
            </button>
          </div>
        </form>
      </section>

      {result && <ProfileView result={result} />}
    </div>
  );
}

export function ProfileView({ result }: { result: ResumeUploadResponse }) {
  const router = useRouter();
  const { profile } = result;
  const displayName = profile.name?.trim() || "Unnamed Candidate";
  const initial = displayName.charAt(0).toUpperCase();
  const createdLabel = formatTimestamp(result.created_at);

  const [roles, setRoles] = useState<JobRole[] | null>(null);
  const [role, setRole] = useState<JobRole | null>(null);
  const [questionCount, setQuestionCount] = useState(DEFAULT_QUESTION_COUNT);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchJobRoles().then(setRoles);
  }, []);

  /** Skills mentioned anywhere in the extracted profile, normalised for matching. */
  const candidateSkills = useMemo(() => {
    const skills = new Set<string>();
    const groups: string[][] = [
      profile.programming_languages,
      profile.frameworks_and_tools,
      profile.technical_skills,
      profile.relevant_domains,
    ];
    for (const group of groups) {
      for (const skill of group) {
        const key = (skill ?? "").trim().toLowerCase();
        if (key) skills.add(key);
      }
    }
    return skills;
  }, [profile]);

  /** Roles whose key skills overlap with the candidate's extracted skills. */
  const suggestedRoles = useMemo<JobRole[]>(() => {
    if (!roles) return [];
    return roles
      .map((candidateRole) => {
        const normalizedKeySkills = (candidateRole.keySkills ?? []).map((skill) =>
          skill.trim().toLowerCase(),
        );
        const score = normalizedKeySkills.filter((skill) => candidateSkills.has(skill)).length;
        return { candidateRole, score };
      })
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 2)
      .map((entry) => entry.candidateRole);
  }, [roles, candidateSkills]);

  // Pre-select the best-matching suggested role once the catalog loads.
  useEffect(() => {
    if (roles && roles.length > 0 && !role) {
      const topSuggestion = suggestedRoles[0] ?? roles[0];
      setRole(topSuggestion);
    }
  }, [roles, suggestedRoles, role]);

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!role || generating) return;

    setError(null);
    setGenerating(true);

    try {
      const { sessionId } = await generateInterview(result.candidate_id, role, questionCount);
      router.push(`/interview/${encodeURIComponent(sessionId)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Interview generation failed.");
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <div className="flex flex-col gap-4 pb-5 border-b border-slate-100 dark:border-slate-800 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4 min-w-0">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-800 text-lg font-semibold text-indigo-700 dark:text-indigo-300">
              {initial}
            </div>
            <div className="min-w-0">
              <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 break-words">
                {displayName}
              </h2>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 break-words">
                {result.filename} · Uploaded {createdLabel}
              </p>
              <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 font-mono break-all">
                {result.candidate_id}
              </p>
            </div>
          </div>

          <span className="inline-flex shrink-0 items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold tracking-wide uppercase bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Profile extracted
          </span>
        </div>

        <dl className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <InfoTile label="Email" value={profile.email} />
          <InfoTile label="Phone" value={profile.phone} />
          <InfoTile label="Location" value={profile.location} />
        </dl>

        <div className="mt-5 p-5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Skills &amp; Competencies
          </h3>
          <dl className="mt-4 space-y-4">
            <ChipGroup label="Programming Languages" items={profile.programming_languages} />
            <ChipGroup label="Technical Skills" items={profile.technical_skills} />
            <ChipGroup label="Frameworks & Tools" items={profile.frameworks_and_tools} />
            <ChipGroup label="Relevant Domains" items={profile.relevant_domains} />
          </dl>
        </div>

        <ResultSection title="Education">
          {profile.education.length === 0 ? (
            <EmptyNote label="education history" />
          ) : (
            <ul className="space-y-4">
              {profile.education.map((item, index) => (
                <EducationRow key={`${item.institution}-${index}`} item={item} />
              ))}
            </ul>
          )}
        </ResultSection>

        <ResultSection title="Work Experience">
          {profile.work_experience.length === 0 ? (
            <EmptyNote label="work experience" />
          ) : (
            <ul className="space-y-4">
              {profile.work_experience.map((item, index) => (
                <ExperienceRow key={`${item.company}-${index}`} item={item} />
              ))}
            </ul>
          )}
        </ResultSection>

        <ResultSection title="Projects">
          {profile.projects.length === 0 ? (
            <EmptyNote label="projects" />
          ) : (
            <ul className="space-y-4">
              {profile.projects.map((item, index) => (
                <ProjectRow key={`${item.title}-${index}`} item={item} />
              ))}
            </ul>
          )}
        </ResultSection>

        <ResultSection title="Certifications">
          {profile.certifications.length === 0 ? (
            <EmptyNote label="certifications" />
          ) : (
            <ul className="space-y-2">
              {profile.certifications.map((certification, index) => (
                <li
                  key={`${certification}-${index}`}
                  className="text-sm text-slate-700 dark:text-slate-300"
                >
                  {certification}
                </li>
              ))}
            </ul>
          )}
        </ResultSection>

        <details className="mt-6 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
          <summary className="px-4 py-3 text-sm font-medium text-slate-700 dark:text-slate-300 cursor-pointer select-none">
            Extracted resume text ({result.extracted_text.length.toLocaleString()} characters)
          </summary>
          <pre className="px-4 pb-4 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-600 dark:text-slate-400 font-mono">
            {result.extracted_text}
          </pre>
        </details>
      </section>

      <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <div className="pb-4 border-b border-slate-100 dark:border-slate-800">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            2. Choose the job role
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Pick the role you want to screen for. Each track is drawn from its own knowledge base.
          </p>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-4 p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-sm text-rose-800 dark:text-rose-300"
          >
            <p className="font-medium">Generation failed</p>
            <p className="mt-1 text-xs text-rose-700 dark:text-rose-300">{error}</p>
          </div>
        )}

        {suggestedRoles.length > 0 && (
          <div className="mt-4">
            <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
              Suggested for this profile
            </p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Based on the skills detected in the extracted resume.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {suggestedRoles.map((suggested) => (
                <button
                  key={suggested.slug}
                  type="button"
                  onClick={() => setRole(suggested)}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border transition cursor-pointer ${
                    role?.slug === suggested.slug
                      ? "bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800"
                      : "bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
                  }`}
                >
                  {suggested.title}
                  {role?.slug === suggested.slug && (
                    <span aria-hidden="true">✓</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {!roles ? (
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">Loading roles…</p>
        ) : roles.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">No roles are available yet.</p>
        ) : (
          <ul className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {roles.map((candidateRole) => (
              <li
                key={candidateRole.slug}
                className={`cursor-pointer rounded-xl border p-4 transition ${role?.slug === candidateRole.slug ? "border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-950/40 ring-2 ring-indigo-500" : "border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700"}`}
                onClick={() => setRole(candidateRole)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                        {candidateRole.title}
                      </p>
                      {suggestedRoles.some((suggested) => suggested.slug === candidateRole.slug) && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                          Suggested
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                      {candidateRole.category}
                    </p>
                    <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 line-clamp-2">
                      {candidateRole.description}
                    </p>
                  </div>
                  {role?.slug === candidateRole.slug && (
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-white">
                      <svg
                        className="h-3 w-3"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={3}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <form onSubmit={handleGenerate} className="space-y-4">
          <div className="pb-4 border-b border-slate-100 dark:border-slate-800">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              3. Generate the interview
            </h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Questions are drawn from the role's knowledge base and tailored to your profile.
            </p>
          </div>

          <div>
            <label htmlFor="question-count" className="block text-xs font-medium text-slate-500 dark:text-slate-400">
              Questions
            </label>
            <div className="mt-2 flex flex-wrap gap-2">
              {Array.from({ length: MAX_QUESTION_COUNT - MIN_QUESTION_COUNT + 1 }, (_, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => setQuestionCount(MIN_QUESTION_COUNT + index)}
                  className={`h-9 w-9 rounded-lg text-sm font-semibold transition ${questionCount === MIN_QUESTION_COUNT + index ? "bg-indigo-600 text-white shadow-sm" : "border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"}`}
                  aria-label={`Generate ${MIN_QUESTION_COUNT + index} questions`}
                  aria-pressed={questionCount === MIN_QUESTION_COUNT + index}
                >
                  {MIN_QUESTION_COUNT + index}
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!role || generating}
              className="inline-flex items-center px-5 py-2.5 text-sm font-medium rounded-lg text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition cursor-pointer"
            >
              {generating ? (
                <>
                  <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin mr-2" />
                  Generating…
                </>
              ) : (
                "Generate Interview"
              )}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
      <dt className="text-xs uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100 break-words">
        {value?.trim() || "—"}
      </dd>
    </div>
  );
}

function ChipGroup({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd className="mt-2">
        {items.length === 0 ? (
          <p className="text-xs text-slate-400 dark:text-slate-500">Not detected</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {items.map((item, index) => (
              <li
                key={`${item}-${index}`}
                className="px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800"
              >
                {item}
              </li>
            ))}
          </ul>
        )}
      </dd>
    </div>
  );
}

function ResultSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-5">
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function EmptyNote({ label }: { label: string }) {
  return <p className="text-sm text-slate-400 dark:text-slate-500">No {label} detected.</p>;
}

function EducationRow({ item }: { item: EducationItem }) {
  const degreeLine = [item.degree, item.field_of_study].filter(Boolean).join(" · ");
  const years = [item.start_year, item.end_year].filter(Boolean).join(" – ");

  return (
    <li className="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
      <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item.institution}</p>
      {degreeLine && (
        <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">{degreeLine}</p>
      )}
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
        {years && <span>{years}</span>}
        {item.grade && <span>{item.grade}</span>}
      </div>
    </li>
  );
}

function ExperienceRow({ item }: { item: ExperienceItem }) {
  return (
    <li className="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          {item.role} · <span className="font-normal text-slate-600 dark:text-slate-400">{item.company}</span>
        </p>
        {item.duration && (
          <p className="text-xs text-slate-500 dark:text-slate-400 shrink-0">{item.duration}</p>
        )}
      </div>
      {item.description.length > 0 && (
        <ul className="mt-2 space-y-1 list-disc pl-5">
          {item.description.map((line, index) => (
            <li key={`${line}-${index}`} className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              {line}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function ProjectRow({ item }: { item: ProjectItem }) {
  return (
    <li className="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
      <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item.title}</p>
      {item.description && (
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
          {item.description}
        </p>
      )}
      {item.technologies.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {item.technologies.map((technology, index) => (
            <li
              key={`${technology}-${index}`}
              className="px-2 py-0.5 rounded text-xs font-medium bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700"
            >
              {technology}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
