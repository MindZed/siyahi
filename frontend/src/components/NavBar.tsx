"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenCheck, FileUp, LayoutDashboard, SlidersHorizontal } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", shortLabel: "Home", icon: LayoutDashboard },
  { href: "/upload", label: "Upload & OCR", shortLabel: "Upload", icon: FileUp },
  { href: "/setup", label: "Exam Setup", shortLabel: "Setup", icon: SlidersHorizontal },
] as const;

export function NavBar() {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/" || pathname.startsWith("/review");
    return pathname.startsWith(href);
  };

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-3 px-4 py-2.5 sm:px-6 sm:py-3">
          <Link
            href="/"
            className="flex min-h-[44px] items-center gap-2.5 rounded-lg pr-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#1E293B] text-white shadow-sm">
              <BookOpenCheck className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-bold tracking-tight text-[#0F172A]">
                Siyahi Academic Desk
              </div>
              <div className="hidden truncate text-[11px] font-medium text-[#475569] sm:block">
                Pen-to-Print OCR &amp; Auditable Grader
              </div>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav aria-label="Primary navigation" className="hidden items-center gap-2 md:flex">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = isActive(href);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`inline-flex min-h-[44px] items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${
                    active
                      ? "bg-[#1E293B] text-white"
                      : "text-[#334155] hover:bg-slate-100 hover:text-[#0F172A]"
                  }`}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Mobile Quick CTA */}
          <Link
            href="/upload"
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-[#2563EB] px-3.5 py-2 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 md:hidden"
          >
            <FileUp className="h-4 w-4" aria-hidden="true" />
            <span>Scan</span>
          </Link>
        </div>
      </header>

      {/* Mobile Bottom Navigation Bar */}
      <nav
        aria-label="Mobile navigation"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 backdrop-blur md:hidden"
        style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
      >
        <div className="grid grid-cols-3 gap-1 px-2 py-1.5">
          {NAV_ITEMS.map(({ href, shortLabel, icon: Icon }) => {
            const active = isActive(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-[44px] flex-col items-center justify-center gap-0.5 rounded-lg px-2 py-1.5 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${
                  active
                    ? "bg-blue-50 text-[#2563EB]"
                    : "text-[#475569] hover:bg-slate-50 hover:text-[#0F172A]"
                }`}
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
                <span>{shortLabel}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
