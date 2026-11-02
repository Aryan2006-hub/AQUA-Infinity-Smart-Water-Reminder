import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: { colors: { aqua: { ink: "#20352F", muted: "#71837A", mint: "#BDE8D5", green: "#27866B", cream: "#F7FAF5", line: "#E7EEE8" } }, boxShadow: { soft: "0 12px 40px rgba(40,75,58,.07)" } } },
  plugins: []
};
export default config;
