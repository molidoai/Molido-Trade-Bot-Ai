import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
          700: "#0e7490",
        },
        gold: {
          400: "#fbbf24",
          500: "#f59e0b",
        },
      },
      boxShadow: {
        glow: "0 0 40px rgba(34, 211, 238, 0.18)",
      },
    },
  },
  plugins: [],
};
export default config;
