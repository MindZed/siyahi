import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import { NavBar } from "@/components/NavBar";
import "./globals.css";

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Siyahi — Pen-to-Print & Auditable Exam Grader",
  description:
    "Pen-to-Print handwritten script transcription (.md/.pdf) and auditable rubric evaluation desk.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1E293B",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${plusJakartaSans.variable} ${jetBrainsMono.variable}`}
    >
      <body className="min-h-screen bg-[#F8FAFC] font-sans text-[#0F172A] antialiased">
        <NavBar />
        <main className="mx-auto max-w-[1600px] px-3 pb-24 pt-4 sm:px-6 sm:pt-6 md:pb-8">
          {children}
        </main>
      </body>
    </html>
  );
}
