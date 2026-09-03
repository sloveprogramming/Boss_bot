/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system", "BlinkMacSystemFont", "Segoe UI", "PingFang SC",
          "Hiragino Sans GB", "Microsoft YaHei", "sans-serif",
        ],
        display: [
          "Outfit", "-apple-system", "BlinkMacSystemFont", "Segoe UI",
          "PingFang SC", "Microsoft YaHei", "sans-serif",
        ],
      },
      colors: {
        brand: {
          50: "#eef2ff", 100: "#e0e7ff", 200: "#c7d2fe", 300: "#a5b4fc",
          400: "#818cf8", 500: "#6366f1", 600: "#4f46e5", 700: "#4338ca",
          800: "#3730a3", 900: "#312e81",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)",
        glass: "0 4px 24px rgba(31,38,135,.06), inset 0 1px 0 rgba(255,255,255,.6)",
        "glass-hover": "0 16px 48px rgba(79,70,229,.14), inset 0 1px 0 rgba(255,255,255,.6)",
        "glow-brand": "0 8px 24px rgba(99,102,241,.35)",
        "glow-lg": "0 12px 32px rgba(99,102,241,.45)",
        pop: "0 12px 32px rgba(16,24,40,.14)",
      },
      transitionTimingFunction: {
        fluid: "cubic-bezier(.22,.8,.3,1)",
      },
    },
  },
  plugins: [],
};
