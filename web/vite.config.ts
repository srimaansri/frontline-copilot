import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const page = (name: string) => fileURLToPath(new URL(name, import.meta.url));

/**
 * The `?theme=light|dark` hook, applied before the first paint. Each page
 * already sets its theme from storage in an inline script; this adds a second
 * one after it that lets the URL win. src/lib/devHooks.ts does the same for
 * the React state. Only the dev server and mock builds get it.
 */
function themeFromUrl(): Plugin {
  const script =
    '(function(){var t=new URLSearchParams(window.location.search).get("theme");' +
    'if(t==="light"||t==="dark"){document.documentElement.classList.toggle("dark",t==="dark");}})();';
  return {
    name: "theme-from-url",
    transformIndexHtml: () => [{ tag: "script", injectTo: "head", children: script }],
  };
}

// The Python server serves the built files at "/" and the API under "/api".
// In development the API runs on its own port, so "/api" is proxied to it.
//
// `--mode mock` (npm run dev:mock, npm run build:mock) loads .env.mock, which
// makes the API client answer from fixtures. Only that build also contains the
// component gallery (gallery.html). A normal build has the app alone, and none
// of the query-string hooks for screenshots.
export default defineConfig(({ command, mode }) => {
  const mock = mode === "mock";
  const pages: Record<string, string> = { index: page("./index.html") };
  if (mock) {
    pages.gallery = page("./gallery.html");
  }

  return {
    base: "/",
    plugins: [react(), tailwindcss(), ...(command === "serve" || mock ? [themeFromUrl()] : [])],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      proxy: {
        "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
      rolldownOptions: {
        input: pages,
        output: {
          // Libraries change far less often than the app, so they get their own
          // long-cached files: React in one, every other library in another.
          codeSplitting: {
            groups: [
              {
                name: "react",
                test: /node_modules[\\/](?:react|react-dom|scheduler)[\\/]/,
                priority: 2,
              },
              { name: "vendor", test: /node_modules[\\/]/, priority: 1 },
            ],
          },
        },
      },
    },
  };
});
