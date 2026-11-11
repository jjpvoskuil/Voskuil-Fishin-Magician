"""Voskuil Outdoors app icons (John 11-11): dark forest field + patch band + "VO" mark; Fishin Magician = leaping
largemouth in a teal band, Deercast = deer head in an orange band. Writes SVG + PNG sizes with Chrome.
Run: python3 web/tools/make_icons.py OUTDIR [--style top|medal]   (then copy the PNGs into each app's web/public/)"""
import math, sys
from pathlib import Path

BG, CREAM, TEAL, ORANGE = "#1f2b22", "#f4ecd2", "#3d9a88", "#e07b24"

BASS = """<defs><linearGradient id="belly" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5f7f34"/><stop offset=".55" stop-color="#8ea64f"/><stop offset=".8" stop-color="#e4dcae"/></linearGradient></defs>
<g transform="rotate(-28 256 256) translate(0 6)">
 <path d="M155 232 L96 186 C110 228 110 264 96 304 L155 258 Z" fill="#5f7f34"/>
 <path d="M232 190 L238 156 L250 166 L258 150 L270 164 L280 152 L290 168 L298 160 L304 192 Z" fill="#4c6a28"/>
 <path d="M190 206 C196 176 222 172 232 192 Z" fill="#5f7f34"/>
 <path d="M405 245 C390 205 340 188 290 186 C230 184 180 205 150 228 L150 262 C185 292 240 318 300 316 C350 314 390 296 410 274 L368 260 Z" fill="url(#belly)"/>
 <path d="M338 252 C300 250 250 246 200 244 C185 244 168 245 156 246" stroke="#3a5020" stroke-width="13" fill="none" stroke-linecap="round" stroke-dasharray="26 8 18 10 30 6"/>
 <path d="M336 200 C318 236 320 274 342 306" stroke="#3a5020" stroke-width="5" fill="none" stroke-linecap="round" opacity=".7"/>
 <path d="M300 300 L276 338 L322 312 Z" fill="#8ea64f"/>
 <path d="M408 274 L368 260 L404 246" fill="#7a2c1c"/>
 <circle cx="366" cy="228" r="12" fill="#1a1a14"/><circle cx="369" cy="224" r="4" fill="#f4ecd2"/>
</g>
<path d="M120 380 C170 352 210 396 256 372 C300 350 340 394 392 372" stroke="#efe2c4" stroke-width="12" fill="none" stroke-linecap="round"/>
<path d="M150 412 C200 392 230 420 280 404 C320 392 350 414 372 406" stroke="#e07b24" stroke-width="9" fill="none" stroke-linecap="round" opacity=".9"/>
<circle cx="168" cy="338" r="7" fill="#efe2c4"/><circle cx="196" cy="318" r="5" fill="#efe2c4"/><circle cx="360" cy="342" r="6" fill="#efe2c4"/><circle cx="336" cy="322" r="4" fill="#efe2c4"/>"""


def deer():
    """Deercast's deer (tools/make_icon.py in that repo, 1024 px) redrawn as SVG without its ring."""
    cx, a, w, out = 512, "#efe2c4", 30, []
    line = lambda pts, wd: out.append(f'<polyline points="{" ".join(f"{x},{y}" for x, y in pts)}" stroke="{a}" stroke-width="{wd}" fill="none" stroke-linejoin="round" stroke-linecap="round"/>')
    for s in (1, -1):
        x = lambda v: cx + s * v
        line([(x(70), 470), (x(150), 380), (x(230), 330), (x(290), 260), (x(300), 190)], w)
        line([(x(150), 380), (x(140), 270)], w - 4); line([(x(230), 330), (x(235), 215)], w - 4); line([(x(290), 260), (x(360), 225)], w - 6)
    el = lambda x0, y0, x1, y1, c: out.append(f'<ellipse cx="{(x0+x1)/2}" cy="{(y0+y1)/2}" rx="{(x1-x0)/2}" ry="{(y1-y0)/2}" fill="{c}"/>')
    el(cx - 285, 470, cx - 140, 560, "#9c6f45"); el(cx + 140, 470, cx + 285, 560, "#9c6f45")
    el(cx - 255, 488, cx - 165, 540, "#d9b48f"); el(cx + 165, 488, cx + 255, 540, "#d9b48f")
    el(cx - 150, 430, cx + 150, 700, "#a87a4f")
    out.append(f'<polygon points="{cx-140},600 {cx+140},600 {cx+78},840 {cx-78},840" fill="#a87a4f"/>')
    el(cx - 80, 770, cx + 80, 880, "#a87a4f"); el(cx - 60, 700, cx + 60, 860, "#c9a07a"); el(cx - 52, 815, cx + 52, 875, "#2a2018")
    for s in (1, -1): el(cx + s * 82 - 22, 585, cx + s * 82 + 22, 625, "#1a1410")
    return f'<g transform="translate(0 -6) scale(.5)">{"".join(out)}</g>'


def band(color, style):
    t = [f'<circle cx="256" cy="256" r="214" fill="none" stroke="{color}" stroke-width="46"/>',
         f'<circle cx="256" cy="256" r="191" fill="none" stroke="{BG}" stroke-width="2" opacity=".35"/>']
    star = lambda deg, size=24: f'<text x="{256 + 214 * math.cos(math.radians(deg)):.1f}" y="{256 + 214 * math.sin(math.radians(deg)) + size * .36:.1f}" font-size="{size}" fill="{CREAM}" text-anchor="middle" font-family="DejaVu Sans, Helvetica">★</text>'
    vo = lambda x, y, size, fill: f'<text x="{x}" y="{y}" font-family="DejaVu Serif, Georgia, serif" font-weight="700" font-size="{size}" letter-spacing="1" fill="{fill}" text-anchor="middle">VO</text>'
    if style == "top":   # VO in the band at 12 o'clock, stars at the bottom
        t += [vo(256, 59, 44, CREAM), star(60), star(90), star(120), star(242, 18), star(298, 18)]
    else:                # VO medallion breaking the band at the bottom
        t += [star(210, 20), star(270, 22), star(330, 20),
              f'<circle cx="256" cy="466" r="46" fill="{CREAM}" stroke="{BG}" stroke-width="5"/>', vo(256, 481, 42, BG)]
    return "".join(t)


def icon(app, style):
    art, color = (f'<g transform="translate(256 256) scale(.84) translate(-256 -270)">{BASS}</g>', TEAL) if app == "fishin" else \
                 (f'<g transform="translate(256 256) scale(.86) translate(-256 -256)">{deer()}</g>', ORANGE)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" fill="{BG}"/>{art}{band(color, style)}</svg>'


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    styles = [sys.argv[sys.argv.index("--style") + 1]] if "--style" in sys.argv else ["top", "medal"]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = b.new_page(viewport={"width": 1024, "height": 1024})
        for st in styles:
            for app in ("fishin", "deercast"):
                svg = icon(app, st); (out / f"{app}-{st}.svg").write_text(svg)
                sized = svg.replace("<svg ", '<svg width="1024" height="1024" ', 1)
                pg.set_content(f'<html><body style="margin:0">{sized}</body></html>')
                pg.screenshot(path=str(out / f"{app}-{st}-1024.png"), clip={"x": 0, "y": 0, "width": 1024, "height": 1024})
        b.close()
    from PIL import Image
    for f in out.glob("*-1024.png"):
        im = Image.open(f).convert("RGB"); stem = f.name[:-9]
        for n, s in [("icon-512", 512), ("icon-192", 192), ("apple-touch-icon", 180), ("favicon", 64)]:
            im.resize((s, s), Image.LANCZOS).save(out / f"{stem}-{n}.png")
    print("wrote", len(list(out.iterdir())), "files to", out)
