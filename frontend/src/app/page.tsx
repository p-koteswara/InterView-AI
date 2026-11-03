import { Suspense } from "react";
import { BackendStatus } from "@/components/backend-status";
import { fetchHealth, type HealthResponse } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  return (
    <main className="min-h-screen flex flex-col justify-center px-4 py-16 sm:px-6 lg:px-8 bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <div className="max-w-3xl mx-auto text-center mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 mb-4">
          <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" />
          Enterprise AI Talent Screening
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
          InterView <span className="text-indigo-600 dark:text-indigo-400">AI</span>
        </h1>
        <p className="mt-4 text-base sm:text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
          AI-driven candidate screening platform combining automated resume analysis, domain-grounded RAG interview workflows, and deep competency scoring.
        </p>
      </div>

      <Suspense fallback={<HealthFallback />}>
        <HealthSection />
      </Suspense>

      <footer className="mt-16 text-center text-xs text-slate-400 dark:text-slate-600">
        InterView AI Platform &bull; Core Service & System Foundation
      </footer>
    </main>
  );
}

async function HealthSection() {
  let initialHealth: HealthResponse | null = null;
  let initialError: string | null = null;

  try {
    initialHealth = await fetchHealth();
  } catch (error) {
    initialError =
      error instanceof Error ? error.message : "Unable to establish connection to backend service";
  }

  return <BackendStatus initialHealth={initialHealth} initialError={initialError} />;
}

function HealthFallback() {
  return (
    <div className="w-full max-w-3xl mx-auto p-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm animate-pulse">
      <div className="h-6 w-48 bg-slate-200 dark:bg-slate-800 rounded mb-4" />
      <div className="grid grid-cols-3 gap-4">
        <div className="h-16 bg-slate-100 dark:bg-slate-800/60 rounded-xl" />
        <div className="h-16 bg-slate-100 dark:bg-slate-800/60 rounded-xl" />
        <div className="h-16 bg-slate-100 dark:bg-slate-800/60 rounded-xl" />
      </div>
    </div>
  );
}
