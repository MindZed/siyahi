"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenCheck, Cpu, FileUp, LayoutDashboard, SlidersHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import type { ModalUsageSummary } from "@/types/schemas";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", shortLabel: "Home", icon: LayoutDashboard },
  { href: "/upload", label: "Upload & OCR", shortLabel: "Upload", icon: FileUp },
  { href: "/setup", label: "Exam Setup", shortLabel: "Setup", icon: SlidersHorizontal },
] as const;

export function NavBar() {
  const pathname = usePathname();
  const [usage, setUsage] = useState<ModalUsageSummary | null>(null);

  useEffect(() => {
    let active = true;
    const fetchUsage = () => {
      api
        .health()
        .then((h) => {
          if (active && h.usage) setUsage(h.usage);
        })
        .catch(() => {});
    };
    fetchUsage();
    const timer = setInterval(fetchUsage, 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [pathname]);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/" || pathname.startsWith("/review");
    return pathname.startsWith(href);
  };

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-2 px-3 py-2.5 sm:gap-3 sm:px-6 sm:py-3">
          <Link
            href="/"
            className="flex min-h-[44px] min-w-0 items-center gap-2.5 rounded-lg pr-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
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

          <div className="flex items-center gap-2 sm:gap-3">
            {/* Live Modal Billing & Performance Meter */}
            {usage && (
              <div
                title={`Modal ${usage.gpu_name} ($${usage.gpu_rate_per_hr}/hr) · Siyahi tracked: $${usage.siyahi_gpu_cost_usd.toFixed(4)} (${usage.total_pages} pages, avg ${usage.avg_ocr_time_sec.toFixed(1)}s/run)`}
                className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs"
              >
                <Cpu className="hidden h-3.5 w-3.5 shrink-0 text-[#2563EB] sm:block" aria-hidden="true" />
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 whitespace-nowrap font-semibold text-[#0F172A]">
                    <span className="hidden sm:inline">Modal Bill:</span>
                    <span className="font-mono">
                      ${usage.modal_total_bill_usd.toFixed(2)}
                    </span>
                    <span className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] font-bold text-[#2563EB]">
                      {usage.modal_bill_percent.toFixed(1)}%
                    </span>
                  </div>
                  <div className="mt-1 hidden h-1 w-28 overflow-hidden rounded-full bg-slate-200 sm:block">
                    <div
                      className="h-full rounded-full bg-[#2563EB] transition-all"
                      style={{ width: `${Math.min(100, usage.modal_bill_percent)}%` }}
                    />
                  </div>
                </div>
              </div>
            )}

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
              className="inline-flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-lg bg-[#2563EB] px-3 py-2 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 md:hidden"
            >
              <FileUp className="h-4 w-4" aria-hidden="true" />
              <span>Scan</span>
            </Link>
          </div>
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
