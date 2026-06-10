import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // Output goes to tools/team-dashboard/web/dist/
    // FastAPI will serve this in --prod mode
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // In dev mode, proxy /events/* and /task/* to the FastAPI backend
    proxy: {
      "/events": {
        target: "http://localhost:8765",
        changeOrigin: true,
      },
      "/task": {
        target: "http://localhost:8765",
        changeOrigin: true,
        // Don't proxy /task/* HTML — only the SSE events need proxying.
        // The redirect from / → /task/<sid> comes from FastAPI.
        // In dev mode, the SPA handles /task/:sid routing client-side.
        bypass(req) {
          // Let Vite serve the SPA for all /task/* routes
          if (req.headers?.accept?.includes("text/html")) {
            return "/index.html";
          }
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
