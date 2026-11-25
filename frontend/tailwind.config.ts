import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#0F172A",
          700: "#334155",
          500: "#64748B",
        },
        paper: {
          50: "#F8FAFC",
          100: "#F1F5F9",
        },
      },
    },
  },
  plugins: [],
};

export default config;
