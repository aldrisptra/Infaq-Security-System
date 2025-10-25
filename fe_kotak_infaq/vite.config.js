import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/camera": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/roi": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
