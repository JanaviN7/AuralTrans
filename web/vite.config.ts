import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API runs on 8765 (8000 is commonly taken). /api is proxied so the browser sees one origin,
// which also keeps the SSE progress stream and audio range requests simple.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8765", changeOrigin: false } },
  },
});
