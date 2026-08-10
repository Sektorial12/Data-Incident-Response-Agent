/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#ffffff",
        surface: "#ffffff",
        "surface-alt": "#fafafa",
        "surface-hover": "#f5f5f5",
        elevated: "#ffffff",
        border: "#f0f0f0",
        "border-strong": "#d9d9d9",
        primary: {
          DEFAULT: "#533fd1",
          hover: "#4530b8",
          subtle: "#f4f0ff",
          border: "#cec1f7",
        },
        ink: {
          primary: "#000000d9",
          secondary: "#595959",
          tertiary: "#8c8c8c",
          muted: "#bfbfbf",
        },
        amber: {
          DEFAULT: "#faad14",
          subtle: "#fffbe6",
          border: "#ffe58f",
        },
        green: {
          DEFAULT: "#52c41a",
          subtle: "#f6ffed",
          border: "#b7eb8f",
        },
        red: {
          DEFAULT: "#ff4d4f",
          subtle: "#fff2f0",
          border: "#ffccc7",
        },
        blue: {
          DEFAULT: "#1890ff",
          subtle: "#e6f7ff",
          border: "#91d5ff",
        },
      },
      fontFamily: {
        sans: ["Manrope", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "Noto Sans", "sans-serif"],
        mono: ["Roboto Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": "11px",
      },
      borderRadius: {
        DEFAULT: "5px",
      },
    },
  },
  plugins: [],
};
