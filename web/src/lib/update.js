// Is a newer copy published? GitHub Pages lets phones reuse the page for ~10 min and home-screen apps hold on longer,
// so on open and whenever the app comes back to the screen (at most once a minute) fetch version.json past every cache.
// update() reloads with a fresh ?v= so the phone has to fetch the new page.
import { useEffect, useState } from "react";
import { BUILD } from "../Shell.jsx";

export function useNewVersion() {
  const [fresh, setFresh] = useState(false);
  useEffect(() => {
    if (BUILD === "dev") return;
    let last = 0;
    const check = () => {
      if (document.visibilityState !== "visible" || Date.now() - last < 60e3) return;
      last = Date.now();
      fetch(`${import.meta.env.BASE_URL}version.json?t=${Date.now()}`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null)).then((v) => { if (v?.build && v.build !== BUILD) setFresh(true); }).catch(() => {});
    };
    check();
    document.addEventListener("visibilitychange", check); window.addEventListener("focus", check);
    return () => { document.removeEventListener("visibilitychange", check); window.removeEventListener("focus", check); };
  }, []);
  return fresh;
}

export function update() {
  const q = new URLSearchParams(location.search); q.set("v", Date.now().toString(36));
  location.replace(`${location.pathname}?${q}${location.hash}`);
}
