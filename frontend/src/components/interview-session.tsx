"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  MAX_ANSWER_LENGTH,
  evaluateInterview,
  fetchInterviewEvaluations,
  fetchInterviewReport,
  fetchSessionAnswers,
  fetchInterviewSession,
  generateInterviewReport,
  submitAnswer,
  type AnswerEvaluation,
  type AnswerRecord,
  type InterviewQuestion,
  type InterviewReport,
  type InterviewSession,
} from "@/lib/api";
import { formatTimestamp } from "@/lib/format";

export function InterviewSessionView({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [submitted, setSubmitted] = useState<Record<string, AnswerRecord>>({});
  const [evaluations, setEvaluations] = useState<AnswerEvaluation[]>([]);
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evaluatingError, setEvaluatingError] = useState<string | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [generatingReportError, setGeneratingReportError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);

    try {
      const [sessionData, answersData] = await Promise.all([
        fetchInterviewSession(sessionId),
        fetchSessionAnswers(sessionId),
      ]);
      setSession(sessionData);
      setSubmitted(
        Object.fromEntries(answersData.answers.map((answer) => [answer.question_id, answer])),
      );
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : "Unable to load this interview session.",
      );
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const answeredCount = session?.questions.filter((question) => submitted[question.id]).length ?? 0;
  const total = session?.questions.length ?? 0;
  const allAnswered = total > 0 && answeredCount === total;

  async function handleSubmitForEvaluation() {
    setEvaluating(true);
    setEvaluatingError(null);

    try {
      const evaluationsResponse = await evaluateInterview(sessionId);
      setEvaluations(evaluationsResponse.evaluations);
      const finalReport = await generateInterviewReport(sessionId);
      setReport(finalReport);
      router.push("/");
    } catch (error) {
      setEvaluatingError(
        error instanceof Error ? error.message : "The interview could not be evaluated.",
      );
      setEvaluating(false);
    }
  }

  async function handleGenerateFinalReport() {
    setGeneratingReport(true);
    setGeneratingReportError(null);

    try {
      const finalReport = await generateInterviewReport(sessionId);
      setReport(finalReport);
      router.push("/");
    } catch (error) {
      setGeneratingReportError(
        error instanceof Error ? error.message : "The final interview report could not be generated.",
      );
      setGeneratingReport(false);
    }
  }

  if (loading) {
    return <LoadingState />;
  }

  if (loadError || !session) {
    return (
      <ErrorState
        title="Could not load this interview"
        message={loadError ?? "The interview session could not be loaded."}
        onRetry={load}
      />
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-indigo-200 dark:border-indigo-900 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 break-words">
              {session.role_title}
            </h2>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Generated {formatTimestamp(session.created_at)} ·{" "}
              {total === 1 ? "1 question" : `${total} questions`}
            </p>
            <p className="mt-1 text-xs font-mono text-slate-400 dark:text-slate-500 break-all">
              Session {session.session_id}
            </p>
          </div>

          <span className="inline-flex shrink-0 items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
            {answeredCount} of {total} answered
          </span>
        </div>

        {session.focus_skills.length > 0 && (
          <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800">
            <p className="text-xs uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
              Personalised on
            </p>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {session.focus_skills.map((skill) => (
                <li
                  key={skill}
                  className="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-50 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700"
                >
                  {skill}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-5 border-t border-slate-100 dark:border-slate-800 pt-4">
          <div
            className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"
            role="progressbar"
            aria-valuenow={answeredCount}
            aria-valuemin={0}
            aria-valuemax={total}
            aria-label="Answers submitted"
          >
            <div
              className="h-full rounded-full bg-indigo-600 dark:bg-indigo-500 transition-all"
              style={{ width: `${(answeredCount / total) * 100}%` }}
            />
          </div>
          {allAnswered && (
            <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              All questions answered. Answers are saved and cannot be edited.
            </p>
          )}
        </div>
      </section>

      <ol className="space-y-5">
        {session.questions.map((question) => (
          <li key={question.id}>
            <QuestionCard
              sessionId={session.session_id}
              question={question}
              answer={submitted[question.id]}
              onSubmitted={(answer) =>
                setSubmitted((current) => ({ ...current, [answer.question_id]: answer }))
              }
            />
          </li>
        ))}
      </ol>

      {allAnswered && (
        <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <div className="pb-4 border-b border-slate-100 dark:border-slate-800">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              AI Interview Evaluation
            </h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {evaluating
                ? "Submitting the interview for AI evaluation…"
                : "All questions are answered. Submit the interview for AI evaluation to receive scores, feedback and the final report."}
            </p>
          </div>

          {evaluating && (
            <div className="mt-4 flex items-center gap-3" role="status" aria-live="polite">
              <span className="h-3.5 w-3.5 rounded-full border-2 border-indigo-300 border-t-indigo-600 dark:border-indigo-800 dark:border-t-indigo-400 animate-spin" />
              <p className="text-sm text-indigo-800 dark:text-indigo-200">
                Evaluating answers against the knowledge base…
              </p>
            </div>
          )}

          {evaluatingError && (
            <div
              role="alert"
              className="mt-4 p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-sm text-rose-800 dark:text-rose-300"
            >
              <p className="font-medium">Evaluation failed</p>
              <p className="mt-1 text-xs text-rose-700 dark:text-rose-300">{evaluatingError}</p>
            </div>
          )}

          {!evaluating && !evaluatingError && !report && evaluations.length === 0 && (
            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-slate-600 dark:text-slate-400">
                The AI will score technical correctness, relevance, depth and clarity, then build
                the final interview report.
              </p>
              <button
                type="button"
                onClick={handleSubmitForEvaluation}
                className="inline-flex items-center justify-center px-5 py-2.5 text-sm font-medium rounded-lg text-white bg-indigo-600 hover:bg-indigo-500 transition cursor-pointer"
              >
                Submit for evaluation
              </button>
            </div>
          )}

          {!evaluating && !evaluatingError && !report && evaluations.length > 0 && (
            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-slate-600 dark:text-slate-400">
                Answer evaluations are ready. Generate the final interview report.
              </p>
              <button
                type="button"
                onClick={handleGenerateFinalReport}
                disabled={generatingReport}
                className="inline-flex items-center justify-center px-5 py-2.5 text-sm font-medium rounded-lg text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition cursor-pointer"
              >
                {generatingReport ? "Generating report…" : "Generate final report"}
              </button>
            </div>
          )}

          {report && (
            <div className="mt-4 space-y-5">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                  <p className="text-xs uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
                    Overall score
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">
                    {report.overall_score.toFixed(1)}
                    <span className="text-sm font-medium text-slate-400">/ 10</span>
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                  <p className="text-xs uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
                    Answered
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">
                    {report.answered_count}
                    <span className="text-sm font-medium text-slate-400"> / {report.question_count}</span>
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
                  <p className="text-xs uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
                    Interview date
                  </p>
                  <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {report.interview_date ? formatTimestamp(report.interview_date) : "—"}
                  </p>
                </div>
              </div>

              {report.strengths.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    Strengths
                  </h3>
                  <ul className="mt-2 list-disc pl-5 text-sm text-slate-700 dark:text-slate-300">
                    {report.strengths.map((strength) => (
                      <li key={strength}>{strength}</li>
                    ))}
                  </ul>
                </div>
              )}

              {report.weaknesses.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    Weaknesses &amp; knowledge gaps
                  </h3>
                  <ul className="mt-2 list-disc pl-5 text-sm text-slate-700 dark:text-slate-300">
                    {report.weaknesses.map((weakness) => (
                      <li key={weakness}>{weakness}</li>
                    ))}
                  </ul>
                </div>
              )}

              {report.recommended_topics.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    Recommended topics for improvement
                  </h3>
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {report.recommended_topics.map((topic) => (
                      <li
                        key={topic}
                        className="px-2.5 py-1 rounded-md text-xs font-medium bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
                      >
                        {topic}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {report.assessment && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    Overall assessment
                  </h3>
                  <p className="mt-2 text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
                    {report.assessment}
                  </p>
                </div>
              )}

              {report.evaluations.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    Answer evaluations
                  </h3>
                  <ul className="mt-3 space-y-3">
                    {report.evaluations.map((evaluation) => (
                      <li
                        key={evaluation.id}
                        className="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50"
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                            Question {evaluation.question_position}
                          </p>
                          <p className="text-xs font-medium text-indigo-700 dark:text-indigo-300">
                            {evaluation.overall_score.toFixed(1)} / 10
                          </p>
                        </div>
                        <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
                          {evaluation.feedback}
                        </p>
                        {evaluation.improvements.length > 0 && (
                          <ul className="mt-2 space-y-1 list-disc pl-5">
                            {evaluation.improvements.map((improvement) => (
                              <li
                                key={improvement}
                                className="text-xs text-slate-600 dark:text-slate-400"
                              >
                                {improvement}
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <button
                type="button"
                onClick={() => router.push("/")}
                className="inline-flex items-center px-5 py-2.5 text-sm font-medium rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
              >
                Back to home
              </button>
            </div>
          )}
        </section>
      )}

      <footer className="text-center text-xs text-slate-400 dark:text-slate-600">
        InterView AI Platform &bull; Interview Session
      </footer>
    </div>
  );
}

function QuestionCard({
  sessionId,
  question,
  answer,
  onSubmitted,
}: {
  sessionId: string;
  question: InterviewQuestion;
  answer: AnswerRecord | undefined;
  onSubmitted: (answer: AnswerRecord) => void;
}) {
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = draft.trim();
  const tooLong = draft.length > MAX_ANSWER_LENGTH;
  const canSubmit = trimmed.length > 0 && !tooLong && !saving;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;

    setSaving(true);
    setError(null);

    try {
      const saved = await submitAnswer(sessionId, question.id, trimmed);
      onSubmitted(saved);
      setDraft("");
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "The answer could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-800 text-xs font-semibold text-indigo-700 dark:text-indigo-300">
            {question.position}
          </span>
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
            {question.topic}
          </span>
          <Badge label={question.question_type} tone="indigo" />
          <Badge label={question.difficulty} tone={difficultyTone(question.difficulty)} />
        </div>

        <p className="mt-3 text-base font-medium leading-relaxed text-slate-900 dark:text-slate-100">
          {question.text}
        </p>

        {question.rationale && (
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{question.rationale}</p>
        )}

        {question.source_document && (
          <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
            Grounded in{" "}
            <span className="font-mono">
              {question.source_document}
              {question.source_section ? ` › ${question.source_section}` : ""}
            </span>
          </p>
        )}
      </header>

      {answer ? (
        <div className="mt-4 rounded-xl bg-emerald-50/60 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Answer saved
            </span>
            <span className="text-xs text-emerald-700/80 dark:text-emerald-500">
              {formatTimestamp(answer.created_at)}
            </span>
          </div>
          <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-800 dark:text-slate-200">
            {answer.answer_text}
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <label
            htmlFor={`answer-${question.id}`}
            className="block text-xs font-medium text-slate-500 dark:text-slate-400"
          >
            Your answer
          </label>
          <textarea
            id={`answer-${question.id}`}
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              setError(null);
            }}
            disabled={saving}
            rows={5}
            placeholder="Type your answer here. Explain your reasoning, trade-offs and any examples."
            className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 px-4 py-3 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-60"
          />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p
              className={`text-xs ${
                tooLong
                  ? "text-rose-600 dark:text-rose-400"
                  : "text-slate-400 dark:text-slate-500"
              }`}
            >
              {draft.length.toLocaleString()} / {MAX_ANSWER_LENGTH.toLocaleString()} characters
              &middot; answers cannot be edited after submission
            </p>

            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg text-white bg-indigo-600 hover:bg-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed transition cursor-pointer"
            >
              {saving ? "Saving…" : "Submit answer"}
            </button>
          </div>

          {error && (
            <div
              role="alert"
              className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-sm text-rose-800 dark:text-rose-200"
            >
              <p className="font-medium">Answer not saved</p>
              <p className="mt-1 text-xs text-rose-700 dark:text-rose-300">{error}</p>
            </div>
          )}
        </form>
      )}
    </article>
  );
}

function Badge({
  label,
  tone,
}: {
  label: string;
  tone: "indigo" | "emerald" | "amber" | "slate";
}) {
  const tones = {
    indigo:
      "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800",
    emerald:
      "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800",
    amber:
      "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300 border-amber-200 dark:border-amber-800",
    slate:
      "bg-slate-50 text-slate-600 dark:bg-slate-800/60 dark:text-slate-300 border-slate-200 dark:border-slate-700",
  } as const;

  return (
    <span
      className={`px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wide border ${tones[tone]}`}
    >
      {label}
    </span>
  );
}

function difficultyTone(difficulty: InterviewQuestion["difficulty"]) {
  if (difficulty === "hard") return "amber" as const;
  if (difficulty === "medium") return "indigo" as const;
  return "slate" as const;
}

function LoadingState() {
  return (
    <div
      role="status"
      className="space-y-5"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm animate-pulse">
        <div className="h-6 w-56 bg-slate-200 dark:bg-slate-800 rounded" />
        <div className="mt-3 h-4 w-40 bg-slate-100 dark:bg-slate-800/60 rounded" />
        <div className="mt-5 h-1.5 w-full bg-slate-100 dark:bg-slate-800/60 rounded-full" />
      </div>

      {[0, 1, 2].map((index) => (
        <div
          key={index}
          className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm animate-pulse"
        >
          <div className="h-4 w-40 bg-slate-200 dark:bg-slate-800 rounded" />
          <div className="mt-4 h-4 w-full bg-slate-100 dark:bg-slate-800/60 rounded" />
          <div className="mt-2 h-4 w-3/4 bg-slate-100 dark:bg-slate-800/60 rounded" />
          <div className="mt-5 h-24 w-full bg-slate-50 dark:bg-slate-800/40 rounded-xl" />
        </div>
      ))}

      <p className="text-center text-xs text-slate-500 dark:text-slate-400">
        Loading the interview and any saved answers…
      </p>
    </div>
  );
}

function ErrorState({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry: () => void;
}) {
  return (
    <section
      role="alert"
      className="rounded-2xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 p-6"
    >
      <h2 className="text-base font-semibold text-rose-800 dark:text-rose-200">{title}</h2>
      <p className="mt-1 text-sm text-rose-700 dark:text-rose-300 break-words">{message}</p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg text-white bg-rose-600 hover:bg-rose-500 dark:bg-rose-500 dark:hover:bg-rose-400 transition cursor-pointer"
        >
          Try again
        </button>
        <Link
          href="/"
          className="text-sm font-medium text-rose-700 dark:text-rose-300 underline underline-offset-2"
        >
          Back to overview
        </Link>
      </div>
    </section>
  );
}
