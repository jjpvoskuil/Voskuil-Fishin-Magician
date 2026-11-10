import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// BUILD = when this copy was built (shown in the menu and under More, to check the phone has the latest version)
const BUILD = new Date().toLocaleString("en-US", { timeZone: "America/Chicago", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
// BASE = the folder the site is served from: "/Voskuil-Fishin-Magician/" on GitHub Pages (set by .github/workflows/pages.yml), "/" elsewhere
export default defineConfig({ base: process.env.BASE || "/", plugins: [react()], define: { __BUILD__: JSON.stringify(BUILD) } });
