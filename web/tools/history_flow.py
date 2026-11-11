"""Walk Trip History on the demo backend (iPhone 13, light + dark): list, filters, open a session, edit, save.
    python3 web/tools/history_flow.py OUTDIR      (needs the BASE vite preview on :4173)"""
import gzip, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
fx = json.loads(gzip.open(ROOT / "src/lib/fixtures/engine.fixtures.json.gz").read())
bundle = next(b for b in fx["bundles"] if b["anchor"] == "2026-11-10")["bundle"]
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
def full(pg, name, sel="#screen-history"):
    h = pg.locator(sel).evaluate("e => e.scrollHeight")
    pg.set_viewport_size({"width": 390, "height": max(664, h + 70)}); pg.wait_for_timeout(250)
    pg.screenshot(path=str(out / name)); pg.set_viewport_size({"width": 390, "height": 664}); pg.wait_for_timeout(150)
def sheet(pg, name):
    h = pg.locator(".sheet-b").last.evaluate("e => e.scrollHeight")
    pg.set_viewport_size({"width": 390, "height": max(664, h + 140)}); pg.wait_for_timeout(250)
    pg.screenshot(path=str(out / name)); pg.set_viewport_size({"width": 390, "height": 664}); pg.wait_for_timeout(150)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    for theme in ("light", "dark"):
        ctx = b.new_context(**p.devices["iPhone 13"])
        ctx.route("**/api.open-meteo.com/**", lambda r: r.fulfill(json=bundle))
        ctx.route("**/waterservices.usgs.gov/**", lambda r: r.abort())
        ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and "ERR_FAILED" not in m.text and errs.append(m.text))
        pg.add_init_script(f"localStorage.setItem('fm.theme', JSON.stringify({{mode:'{theme}',until:null}}))")
        pg.goto("http://localhost:4173/Voskuil-Fishin-Magician/?demo#more"); pg.wait_for_timeout(1000)
        pg.get_by_role("button", name="Trip History").click(); pg.wait_for_timeout(600)
        full(pg, f"h1-list-{theme}.png")
        pg.get_by_role("button", name="More filters").click(); pg.wait_for_timeout(300)
        full(pg, f"h2-filters-{theme}.png")
        pg.get_by_role("button", name="More filters").first.click() if False else None
        pg.locator("button.card.hist").nth(1).click(); pg.wait_for_timeout(500)
        sheet(pg, f"h3-detail-{theme}.png")
        pg.get_by_role("button", name="Edit", exact=True).click(); pg.wait_for_timeout(400)
        sheet(pg, f"h4-edit-{theme}.png")
        eb = pg.get_by_role("button", name="Edit this fish")
        if eb.count():
            eb.first.click(); pg.wait_for_timeout(400)
            pg.screenshot(path=str(out / f"h5-fish-{theme}.png"))
            pg.get_by_role("button", name="Save changes").last.click(); pg.wait_for_timeout(300)
        pg.get_by_role("button", name="Save changes").last.click(); pg.wait_for_timeout(1500)
        sheet(pg, f"h6-saved-{theme}.png")
        print(theme, "errors:", errs)
        ctx.close()
    b.close()
