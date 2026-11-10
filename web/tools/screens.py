"""Screenshot screens on a simulated iPhone (light + dark) against the demo backend, with Open-Meteo and USGS mocked
from the engine fixtures. Needs `BASE=/Voskuil-Fishin-Magician/ npx vite preview --port 4173` running.
    python3 web/tools/screens.py OUTDIR tab[,tab...] [--click "Button name"]
"""
import gzip, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
fx = json.loads(gzip.open(ROOT / "src/lib/fixtures/engine.fixtures.json.gz").read())
bundle = next(b for b in fx["bundles"] if b["anchor"] == "2026-11-10")["bundle"]
usgs = fx["usgs"]["payload"]
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
tabs = sys.argv[2].split(",")
clicks = [a for i, a in enumerate(sys.argv) if i > 0 and sys.argv[i - 1] == "--click"]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    for theme in ("light", "dark"):
        ctx = b.new_context(**p.devices["iPhone 13"])
        ctx.route("**/api.open-meteo.com/**", lambda r: r.fulfill(json=bundle))
        ctx.route("**/waterservices.usgs.gov/**", lambda r: r.fulfill(json=usgs))
        ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        pg.add_init_script(f"localStorage.setItem('fm.theme', JSON.stringify({{mode:'{theme}',until:null}}))")
        pg.goto("http://localhost:4173/Voskuil-Fishin-Magician/?demo"); pg.wait_for_timeout(800)
        for t in tabs:
            pg.get_by_role("button", name=t, exact=True).last.click(); pg.wait_for_timeout(600)
            shot = out / f"{t}-{theme}.png"
            el = pg.locator(f"#screen-{t.lower()}")
            h = el.evaluate("e => e.scrollHeight")
            pg.set_viewport_size({"width": 390, "height": max(844, h + 70)}); pg.wait_for_timeout(200)
            pg.screenshot(path=str(shot)); pg.set_viewport_size({"width": 390, "height": 844})
            for c in clicks:
                pg.get_by_role("button", name=c).first.click(); pg.wait_for_timeout(300)
                pg.screenshot(path=str(out / f"{t}-{theme}-{c.replace(' ', '_')}.png"))
                pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        print(theme, "errors:", errs)
        ctx.close()
    b.close()
