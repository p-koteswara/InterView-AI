import type { Metadata } from "next";
import Link from "next/link";
import { ResumeUpload } from "@/components/resume-upload";

export const metadata: Metadata = {
  title: "Resume Upload | InterView AI",
  description: "Upload a PDF or TXT resume and review the automatically extracted candidate profile.",
};

export default function UploadPage() {
  return (
    <main className="min-h-screen px-4 py-12 sm:px-6 lg:px-8 bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <div className="max-w-3xl mx-auto mb-8">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition"
        >
          &larr; Back to overview
        </Link>
        <h1 className="mt-4 text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
          Resume <span className="text-indigo-600 dark:text-indigo-400">Screening</span>
        </h1>
        <p className="mt-3 text-base text-slate-600 dark:text-slate-400">
          Upload a candidate resume to extract a structured profile: contact details, skills, domain
          expertise, education, experience, and projects.
        </p>
      </div>

      <div className="max-w-3xl mx-auto">
        <ResumeUpload />
      </div>

      <footer className="mt-16 text-center text-xs text-slate-400 dark:text-slate-600">
        InterView AI Platform &bull; Resume Intelligence
      </footer>
    </main>
  );
}
