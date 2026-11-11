"""Walk the Tackle Box on the demo backend (iPhone 13, light + dark): list, scan a photo, save, quantity, open an item.
    python3 web/tools/tackle_flow.py OUTDIR PHOTO.jpg   (needs the BASE vite preview on :4173)"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True); photo = sys.argv[2]
def full(pg, name, sel):
    h = pg.locator(sel).last.evaluate("e => e.scrollHeight")
    pg.set_viewport_size({"width": 390, "height": max(664, h + 140)}); pg.wait_for_timeout(250)
    pg.screenshot(path=str(out / name)); pg.set_viewport_size({"width": 390, "height": 664}); pg.wait_for_timeout(150)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    for theme in ("light", "dark"):
        ctx = b.new_context(**p.devices["iPhone 13"])
        ctx.route("**/api.open-meteo.com/**", lambda r: r.abort()); ctx.route("**/waterservices.usgs.gov/**", lambda r: r.abort())
        ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script(f"localStorage.setItem('fm.theme', JSON.stringify({{mode:'{theme}',until:null}}))")
        pg.goto("http://localhost:4173/Voskuil-Fishin-Magician/?demo#more"); pg.wait_for_timeout(900)
        pg.get_by_role("button", name="Tackle Box").click(); pg.wait_for_timeout(600)
        full(pg, f"t1-list-{theme}.png", "#screen-tackle")
        pg.locator("#screen-tackle input[type=file]").first.set_input_files(photo); pg.wait_for_timeout(1500)
        full(pg, f"t2-scanned-{theme}.png", ".sheet-b")
        pg.get_by_role("button", name="Add to tackle box").click(); pg.wait_for_timeout(1000)
        pg.get_by_label("Search your tackle").fill("squarebill"); pg.wait_for_timeout(400)
        pg.get_by_role("button", name="One more Strike King - KVD Squarebill 1.5 - Sexy Shad, 1/2 oz").click(); pg.wait_for_timeout(800)
        full(pg, f"t3-added-{theme}.png", "#screen-tackle")
        pg.locator(".titem-main").first.click(); pg.wait_for_timeout(500)
        full(pg, f"t4-item-{theme}.png", ".sheet-b")
        print(theme, "errors:", errs)
        ctx.close()
    b.close()
