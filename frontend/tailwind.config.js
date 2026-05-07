/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg:     "#050507",
        panel:  "#0B0D10",
        text:   "#E6EAF0",
        dim:    "#5A6070",
        "accent-blue": "#3BA7FF",
        // accent-red is the primary brand colour; index.css sets --accent-red-rgb
        // and StatusBar overrides it based on the user's themeAccent setting.
        "accent-red":  "rgb(var(--accent-red-rgb) / <alpha-value>)",
        "night-red":   "#FF2A2A",
        // legacy aliases — keep so existing className refs keep working
        space: {
          950: "#050507",
          900: "#0B0D10",
          800: "#13161C",
          700: "#1C2030",
          600: "#2A3050",
        },
        star:   "#E6EAF0",
        nebula: "#3BA7FF",
        aurora: "#34d399",
      },
      fontFamily: {
        sans: ["'Inter Tight'", "'IBM Plex Sans Condensed'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "'JetBrains Mono'", "monospace"],
      },
    },
  },
  plugins: [],
};
