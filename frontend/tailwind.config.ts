import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        pixel: ['"Press Start 2P"', "monospace"],
        mono: ['"VT323"', "monospace"],
      },
      colors: {
        "pixel-bg": "#1a1a2e",
        "pixel-panel": "#16213e",
        "pixel-border": "#0f3460",
        "pixel-accent": "#e94560",
        "pixel-green": "#00ff88",
        "pixel-yellow": "#ffd700",
        "pixel-blue": "#4fc3f7",
        "pixel-purple": "#bb86fc",
        "pixel-idle": "#555577",
        "pixel-working": "#ffd700",
        "pixel-done": "#00ff88",
        "pixel-error": "#ff4444",
      },
      animation: {
        "pixel-blink": "blink 0.8s step-start infinite",
        "pixel-work": "workbounce 0.5s steps(2) infinite",
        "scanline": "scanline 8s linear infinite",
      },
      keyframes: {
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        workbounce: {
          "0%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-4px)" },
          "100%": { transform: "translateY(0px)" },
        },
        scanline: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
      },
    },
  },
  plugins: [],
};
export default config;
