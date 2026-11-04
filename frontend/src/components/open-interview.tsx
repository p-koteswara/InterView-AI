"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

/** Lets a user jump to an existing interview session, including revisiting past answers. */
export function OpenInterview() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = sessionId.trim();

    if (!trimmed) {
      setError("Enter the interview session ID shown when the interview was generated.");
      return;
    }

    setError(null);
    router.push(`/interview/${encodeURIComponent(trimmed)}`);
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-md mx-auto text-left">
      <label
        htmlFor="session-id"
        className="block text-xs font-medium text-slate-500 dark:text-slate-400"
      >
        Revisit an interview by session ID
      </label>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
        <input
          id="session-id"
          value={sessionId}
          onChange={(event) => {
            setSessionId(event.target.value);
            setError(null);
          }}
          placeholder="e.g. 6078150f-ab1a-4e54-a6ef-0118f820bb76"
          className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm font-mono text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
        <button
          type="submit"
          className="inline-flex shrink-0 items-center justify-center px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
        >
          Open interview
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-xs text-rose-600 dark:text-rose-400">
          {error}
        </p>
      )}
    </form>
  );
}
