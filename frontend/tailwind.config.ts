import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{vue,ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        base: "rgb(var(--color-base) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        panel: "rgb(var(--color-panel) / <alpha-value>)",
        text: "rgb(var(--color-text) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        border: "rgb(var(--color-border) / <alpha-value>)",
        accent: "rgb(var(--color-accent) / <alpha-value>)",
        positive: "rgb(var(--color-positive) / <alpha-value>)",
        negative: "rgb(var(--color-negative) / <alpha-value>)",
        warning: "rgb(var(--color-warning) / <alpha-value>)",
        scanner: "rgb(var(--color-scanner) / <alpha-value>)",
        state: "rgb(var(--color-state) / <alpha-value>)",
        prompt: "rgb(var(--color-prompt) / <alpha-value>)",
        llm: "rgb(var(--color-llm) / <alpha-value>)",
        parser: "rgb(var(--color-parser) / <alpha-value>)",
        guard: "rgb(var(--color-guard) / <alpha-value>)",
        circuit: "rgb(var(--color-circuit) / <alpha-value>)",
        execution: "rgb(var(--color-execution) / <alpha-value>)"
      },
      boxShadow: {
        panel: "var(--shadow-panel)",
      },
      borderRadius: {
        lg: "var(--radius-lg)",
        md: "var(--radius-md)",
        sm: "var(--radius-sm)",
      },
      fontFamily: {
        display: "var(--font-display)",
        body: "var(--font-body)",
        mono: "var(--font-mono)",
      },
    },
  },
  plugins: [],
} satisfies Config;
