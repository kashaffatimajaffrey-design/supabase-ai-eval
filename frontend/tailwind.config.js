/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B0F0D",        // page background — near-black, green-tinted
        panel: "#121815",      // card/panel surface
        panelBorder: "#1F2A23",
        signal: {
          green: "#34D399",    // pass / healthy
          blue: "#38BDF8",     // data / latency / info
          coral: "#F87171",    // fail (used sparingly)
        },
        ink2: "#7C9485",       // muted secondary text
        ink1: "#E8F0EB",       // primary text
      },
      fontFamily: {
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["'Inter'", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glowGreen: "0 0 16px rgba(52, 211, 153, 0.25)",
        glowBlue: "0 0 16px rgba(56, 189, 248, 0.25)",
      },
    },
  },
  plugins: [],
};
