import type { Metadata } from "next";
import Link from "next/link";
import { InterviewSessionView } from "@/components/interview-session";

export const metadata: Metadata = {
  title: "Interview | InterView AI",
  description: "Answer the generated interview questions and review the answers you have saved.",
};

export default async function InterviewPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;

  return (
    <main className="min-h-screen px-4 py-12 sm:px-6 lg:px-8 bg-gradient-to-b from-slate-50 via-slate-50 to-indigo-50/40 dark:from-slate-950 dark:via-slate-950 dark:to-slate-900">
      <div className="max-w-3xl mx-auto mb-8">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition"
        >
          &larr; Back to overview
        </Link>
        <h1 className="mt-4 text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
          Interview <span className="text-indigo-600 dark:text-indigo-400">Session</span>
        </h1>
        <p className="mt-3 text-base text-slate-600 dark:text-slate-400 max-w-2xl">
          Answer the interview questions generated for you. Each answer is saved as you submit it,
          and you can come back to this page any time to see everything you have already saved.
        </p>
      </div>

      <div className="max-w-3xl mx-auto">
        <InterviewSessionView sessionId={decodeURIComponent(sessionId)} />
      </div>
    </main>
  );
}
