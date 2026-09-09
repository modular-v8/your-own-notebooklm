import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev-only proxy: the built app is served by FastAPI itself (same origin,
// no CORS needed -- plan.md), but `vite dev` runs on its own port and needs
// /api forwarded to the backend instead.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
