import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  base: "/static/",
  build: { outDir: "../static", emptyOutDir: true },
  server: { port: 3000 },
});
