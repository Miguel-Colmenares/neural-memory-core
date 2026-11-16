import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0b1020", 900: "#111833", 800: "#1a2347", 700: "#27336b" },
        accent: { 500: "#5b7cfa", 600: "#4563e6", 100: "#e4eaff" },
      },
    },
  },
  plugins: [],
};

export default config;
