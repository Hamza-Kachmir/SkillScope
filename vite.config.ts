import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(() => {
  const buildId = Date.now().toString();

  return {
    define: {
      "import.meta.env.VITE_BUILD_ID": JSON.stringify(buildId),
    },
    plugins: [
      react(),
      {
        name: "skillscope-build-version",
        configureServer(server) {
          server.middlewares.use("/version.json", (_, response) => {
            response.setHeader("Content-Type", "application/json");
            response.setHeader("Cache-Control", "no-store");
            response.end(JSON.stringify({ buildId }));
          });
        },
        generateBundle() {
          this.emitFile({
            type: "asset",
            fileName: "version.json",
            source: JSON.stringify({ buildId }),
          });
        },
      },
    ],
    server: { proxy: { "/api": "http://localhost:8000" } },
  };
});
