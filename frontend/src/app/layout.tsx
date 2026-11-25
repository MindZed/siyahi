import type { Metadata } from "next";
import Link from "next/link";
import { BookOpenCheck, FileUp, LayoutDashboard, SlidersHorizontal } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Siyahi — Pen-to-Print & Auditable Exam Grader",
  description:
    "Pen-to-Print handwritten script transcription (.md/.pdf) and auditable rubric evaluation desk.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-paper-50 text-ink-900 antialiased">
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-[1600px] items-center justify-between px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
                <BookOpenCheck className="h-5 w-5" />
              </div>
              <div>
                <div className="text-sm font-bold tracking-tight text-slate-900">
                  Siyahi Academic Desk
                </div>
                <div className="text-[11px] font-medium text-slate-500">
                  Pen-to-Print OCR &amp; Auditable Grader
                </div>
              </div>
            </Link>

            <nav className="flex items-center gap-1 sm:gap-2">
              <Link
                href="/"
                className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-900"
              >
                <LayoutDashboard className="h-4 w-4" />
                Dashboard
              </Link>
              <Link
                href="/upload"
                className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-900"
              >
                <FileUp className="h-4 w-4" />
                Upload &amp; OCR
              </Link>
              <Link
                href="/setup"
                className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-900"
              >
                <SlidersHorizontal className="h-4 w-4" />
                Exam Setup
              </Link>
            </nav>
          </div>
        </header>

        <main className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6">{children}</main>
      </body>
    </html>
  );
}
