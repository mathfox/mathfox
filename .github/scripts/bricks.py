"""Render the GitHub contribution calendar as a studded brick skyline (animated SVG).

Usage: python bricks.py <login> <out.svg>

Reads the public calendar page (the same data the profile shows, private contributions
included when the profile counts them), so it needs no token and only the standard library.
"""

import datetime as dt
import html
import math
import re
import sys
import urllib.request

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "mathfox"
OUT = sys.argv[2] if len(sys.argv) > 2 else "bricks.svg"

# Screen vectors of one calendar step: along weeks (i) and along weekdays (j).
AX, AY = 14.6, 2.3
BX, BY = -9.0, 8.6
GAP = 1.5  # inset of every brick inside its cell
W, H = 900, 380
X0, Y0 = 92.0, 132.0

# Brick colors per contribution level: (top, front, side).
PALETTE = {
    0: ("#1c2230", "#151a25", "#11151e"),
    1: ("#1f6feb", "#1856b8", "#13448f"),
    2: ("#00b4d8", "#0090ad", "#006f86"),
    3: ("#7bd389", "#5fae6c", "#478552"),
    4: ("#ffb703", "#d99a00", "#b07d00"),
}
MIN_H, MAX_H = 6.0, 46.0


def fetch(login):
    req = urllib.request.Request(
        f"https://github.com/users/{login}/contributions",
        headers={"User-Agent": "bricks-svg"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        page = r.read().decode("utf-8")

    counts = {}
    for m in re.finditer(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', page):
        text = html.unescape(m.group(2))
        n = re.match(r"([\d,]+) contribution", text)
        counts[m.group(1)] = int(n.group(1).replace(",", "")) if n else 0

    days = []
    for m in re.finditer(r"<td[^>]*ContributionCalendar-day[^>]*>", page):
        tag = m.group(0)
        date = re.search(r'data-date="([\d-]+)"', tag)
        level = re.search(r'data-level="(\d)"', tag)
        ident = re.search(r'id="([^"]+)"', tag)
        if not (date and level and ident):
            continue
        days.append(
            {
                "date": dt.date.fromisoformat(date.group(1)),
                "level": int(level.group(1)),
                "count": counts.get(ident.group(1), 0),
            }
        )
    if not days:
        raise SystemExit("no calendar cells found: the page layout changed")
    days.sort(key=lambda d: d["date"])
    return days


def streaks(days):
    longest = run = 0
    for d in days:
        run = run + 1 if d["count"] > 0 else 0
        longest = max(longest, run)
    current = 0
    tail = list(days)
    if tail and tail[-1]["count"] == 0:  # today may be still empty
        tail = tail[:-1]
    for d in reversed(tail):
        if d["count"] == 0:
            break
        current += 1
    return longest, current


def pt(i, j, h=0.0):
    return i * AX + j * BX, i * AY + j * BY - h


def poly(points, fill):
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polygon points="{p}" fill="{fill}"/>'


def brick(level, h):
    """One brick drawn at cell (0, 0); the caller moves it into place with a translate."""
    top, front, side = PALETTE[level]
    g = GAP / max(AX, -BX)
    a, b = g, 1 - g
    t00, t10, t11, t01 = pt(a, a, h), pt(b, a, h), pt(b, b, h), pt(a, b, h)
    b10, b11, b01 = pt(b, a), pt(b, b), pt(a, b)
    parts = [
        poly([t01, t11, b11, b01], front),  # face toward +j (down-left)
        poly([t10, t11, b11, b10], side),  # face toward +i (down-right)
        poly([t00, t10, t11, t01], top),
    ]
    if level > 0:
        cx, cy = pt(0.5, 0.5, h)
        parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy + 1.8:.1f}" rx="4.4" ry="2.5" fill="{front}"/>')
        parts.append(f'<rect x="{cx - 4.4:.1f}" y="{cy - 0.6:.1f}" width="8.8" height="2.4" fill="{front}"/>')
        parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy - 0.6:.1f}" rx="4.4" ry="2.5" fill="{top}" stroke="#ffffff" stroke-opacity=".22" stroke-width=".6"/>')
    return "".join(parts)


def render(days):
    start = days[0]["date"]
    offset = (start.weekday() + 1) % 7  # calendar rows start on Sunday
    cells = []
    for d in days:
        k = (d["date"] - start).days + offset
        cells.append((k // 7, k % 7, d))

    active = sorted(d["count"] for d in days if d["count"] > 0) or [1]
    cuts = [active[int(len(active) * q)] for q in (0.25, 0.5, 0.75)]
    top_count = active[-1]

    def level(c):
        return 0 if c == 0 else 1 + sum(c > k for k in cuts)

    def height(c):
        return 2.0 if c == 0 else MIN_H + (MAX_H - MIN_H) * math.log1p(c) / math.log1p(top_count)

    total = sum(d["count"] for d in days)
    longest, current = streaks(days)
    best = max(days, key=lambda d: d["count"])
    weeks = cells[-1][0] + 1

    out = []
    for i, j, d in sorted(cells, key=lambda c: (c[0] * AY + c[1] * BY, c[0])):
        x, y = pt(i, j)
        lvl = level(d["count"])
        title = f'<title>{d["count"]} on {d["date"]:%b %d, %Y}</title>'
        if lvl == 0:
            out.append(f'<use href="#b0" x="{x:.1f}" y="{y:.1f}">{title}</use>')
            continue
        delay = 0.25 + i * (2.4 / weeks) + j * 0.025
        cls = "d best" if d is best else "d"
        out.append(
            f'<g transform="translate({x:.1f},{y:.1f})"><g class="{cls}" '
            f'style="animation-delay:{delay:.2f}s">{title}{brick(lvl, height(d["count"]))}</g></g>'
        )

    font = "font-family=\"'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif\""
    mono = "font-family=\"ui-monospace,'Cascadia Code',Consolas,Menlo,monospace\""
    stats = [
        (f"{total:,}", "contributions"),
        (f"{longest}d", "longest streak"),
        (f"{current}d", "current streak"),
        (f'{best["count"]}', f'best day · {best["date"]:%b %d}'),
    ]
    stat_svg = []
    for n, (value, label) in enumerate(stats):
        sx = W - 36 - (len(stats) - 1 - n) * 128
        stat_svg.append(
            f'<text x="{sx}" y="50" text-anchor="end" {font} font-size="22" font-weight="700" fill="#e6edf3">{value}</text>'
            f'<text x="{sx}" y="70" text-anchor="end" {mono} font-size="10.5" fill="#7d8590">{label}</text>'
        )

    legend = []
    for lvl in range(5):
        legend.append(f'<rect x="{36 + lvl * 16}" y="{H - 30}" width="11" height="11" rx="2" fill="{PALETTE[lvl][0]}"/>')
    legend.append(f'<text x="{36 + 5 * 16 + 6}" y="{H - 21}" {mono} font-size="10.5" fill="#7d8590">less → more · one brick a day</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{LOGIN}: {total} contributions in the last year">
<style>
.d{{animation:drop .7s cubic-bezier(.25,1.6,.45,1) both}}
@keyframes drop{{0%{{transform:translateY(-140px);opacity:0}}35%{{opacity:1}}100%{{transform:none;opacity:1}}}}
.best{{animation:drop .7s cubic-bezier(.25,1.6,.45,1) both,glow 2.4s ease-in-out 3.6s infinite}}
@keyframes glow{{0%,100%{{filter:none}}50%{{filter:drop-shadow(0 0 6px #ffd166) brightness(1.25)}}}}
.fade{{animation:fade 1s ease .1s both}}
@keyframes fade{{from{{opacity:0}}}}
</style>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0d1117"/><stop offset="1" stop-color="#111a2c"/></linearGradient>
<radialGradient id="spot" cx=".5" cy=".62" r=".6"><stop offset="0" stop-color="#1f6feb" stop-opacity=".16"/><stop offset="1" stop-color="#1f6feb" stop-opacity="0"/></radialGradient>
<g id="b0">{brick(0, 2.0)}</g>
</defs>
<rect width="{W}" height="{H}" rx="14" fill="url(#bg)"/>
<rect width="{W}" height="{H}" rx="14" fill="url(#spot)"/>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="13.5" fill="none" stroke="#30363d"/>
<g class="fade">
<text x="36" y="46" {font} font-size="20" font-weight="700" fill="#e6edf3">Built brick by brick</text>
<text x="36" y="68" {mono} font-size="11" fill="#7d8590">{days[0]["date"]:%b %Y} — {days[-1]["date"]:%b %Y} · @{LOGIN}</text>
{"".join(stat_svg)}
</g>
<g transform="translate({X0},{Y0})">
{chr(10).join(out)}
</g>
<g class="fade">{"".join(legend)}</g>
</svg>
"""


if __name__ == "__main__":
    svg = render(fetch(LOGIN))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT} ({len(svg) // 1024} KB)")
