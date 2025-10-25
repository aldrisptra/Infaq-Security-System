/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      boxShadow: {
        card: "0 10px 20px rgba(2,12,27,0.06)",
        panel: "inset 0 0 0 1px #ffffff05, 0 14px 30px rgba(2,12,27,0.32)",
      },
    },
  },
  plugins: [],
};
