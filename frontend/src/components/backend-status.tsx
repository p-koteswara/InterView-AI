"use client";

import { useState } from "react";
import { fetchHealth, type HealthResponse } from "@/lib/api";

type BackendStatusProps = {
  initialHealth: HealthResponse | null;
  initialError: string | null;
};

export function BackendStatus({ initialHealth, initialError }: BackendStatusProps) {
  const [health, setHealth] = useState<HealthResponse | null>(initialHealth);
  const [error, setError] = useState<string | null>(initialError);
  const [loading, setLoading] = useState(false);

  async function loadHealth() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err) {
      setHealth(null);
      setError(err instanceof Error ? err.message : "Unable to establish connection to backend service");
    } finally {
      setLoading(false);
    }
  }

  const isConnected = !!health && !error;
  const statusLabel = loading ? "Checking..." : isConnected ? "Operational" : "Unavailable";

  return (
    <div className="w-full max-w-3xl mx-auto space-y-6">
      {/* System Status Card */}
      <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm transition">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-800">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Core Backend Connectivity
            </h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Real-time health check for API gateways and database persistence
            </p>
          </div>
          <span
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold tracking-wide uppercase ${
              isConnected
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
                : error
                ? "bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300 border border-rose-200 dark:border-rose-800"
                : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                isConnected
                  ? "bg-emerald-500 animate-pulse"
                  : error
                  ? "bg-rose-500"
                  : "bg-slate-400"
              }`}
            />
            {statusLabel}
          </span>
        </div>

        <dl className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
            <dt className="text-xs uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
              Service
            </dt>
            <dd className="mt-1 text-base font-semibold text-slate-900 dark:text-slate-100">
              {health?.service ?? "—"}
            </dd>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
            <dt className="text-xs uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
              API Status
            </dt>
            <dd className="mt-1 text-base font-semibold text-slate-900 dark:text-slate-100">
              {health?.status ? (
                <span className="capitalize text-emerald-600 dark:text-emerald-400">
                  {health.status}
                </span>
              ) : (
                "—"
              )}
            </dd>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
            <dt className="text-xs uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
              Database
            </dt>
            <dd className="mt-1 text-base font-semibold text-slate-900 dark:text-slate-100">
              {health?.database ? (
                <span className="capitalize text-indigo-600 dark:text-indigo-400">
                  {health.database}
                </span>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>

        {error && (
          <div className="mt-5 p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-sm text-rose-800 dark:text-rose-200">
            <p className="font-medium">Connection Error</p>
            <p className="mt-1 text-xs text-rose-700 dark:text-rose-300">
              {error}. Ensure the FastAPI server is running on{" "}
              <code className="font-mono bg-rose-100 dark:bg-rose-900/60 px-1 py-0.5 rounded">
                http://127.0.0.1:8000
              </code>
              .
            </p>
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={() => void loadHealth()}
            disabled={loading}
            className="inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg text-white bg-slate-900 hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200 disabled:opacity-50 transition cursor-pointer"
          >
            {loading ? "Checking Connectivity..." : "Check Status"}
          </button>
        </div>
      </section>

      {/* Architecture Readiness Cards */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Resume Intelligence
          </h3>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            Multiformat document parsing (PDF, TXT) with automatic extraction of tech stacks, domain competencies, and seniority indicators.
          </p>
        </div>

        <div className="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            RAG Knowledge Pipeline
          </h3>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            Grounded vector retrieval across role-specific reference literature using ChromaDB and high-dimensional semantic embeddings.
          </p>
        </div>

        <div className="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Adaptive Technical Interview
          </h3>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            Multi-turn contextual question generation customized dynamically to candidate profile, target position, and knowledge chunks.
          </p>
        </div>

        <div className="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Deep Assessment Analytics
          </h3>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            Traceable rubric scoring, response breakdown, comprehensive strengths & improvement reports stored in persistent database.
          </p>
        </div>
      </section>
    </div>
  );
}

