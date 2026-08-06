/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "oklch(16% 0.01 250)",
        surface: "oklch(20% 0.01 250)",
        elevated: "oklch(23% 0.01 250)",
        border: "oklch(100% 0 0 / 0.08)",
        "border-strong": "oklch(100% 0 0 / 0.12)",
        ink: {
          primary: "oklch(92% 0 0)",
          secondary: "oklch(65% 0 0)",
          tertiary: "oklch(50% 0 0)",
          muted: "oklch(40% 0 0)",
        },
        amber: {
          DEFAULT: "oklch(70% 0.15 60)",
          subtle: "oklch(70% 0.15 60 / 0.12)",
        },
        green: {
          DEFAULT: "oklch(65% 0.15 145)",
          subtle: "oklch(65% 0.15 145 / 0.12)",
        },
        red: {
          DEFAULT: "oklch(60% 0.18 25)",
          subtle: "oklch(60% 0.18 25 / 0.12)",
        },
        blue: {
          DEFAULT: "oklch(65% 0.15 250)",
          subtle: "oklch(65% 0.15 250 / 0.12)",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": "11px",
      },
    },
  },
  plugins: [],
};
