"""Render a punch card of commit times (weekday x hour) as an animated SVG.

Usage: GH_TOKEN=... python activity.py <login> <out.svg> [utc_offset_hours]

With a personal token the script sees every repository the account can read, private ones
included; only counts end up in the SVG, never repository names. With the Actions token it
sees public repositories only, so the workflow uses it only when the STATS_TOKEN secret is set.
"""

import datetime as dt
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

LOGIN = sys.argv[1]
OUT = sys.argv[2]
OFFSET = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
API = "https://api.github.com"


def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "activity-svg"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r), r.headers.get("Link", "")


def pages(url):
    while url:
        try:
            data, link = get(url)
        except urllib.error.HTTPError as e:
            if e.code in (404, 409, 451):  # empty, disabled or blocked repository
                return
            raise
        yield from data
        url = ""
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part[part.index("<") + 1 : part.index(">")]


def repositories():
    try:
        me, _ = get(f"{API}/user")
        own = me.get("login", "").lower() == LOGIN.lower()
    except urllib.error.HTTPError:
        own = False
    if own:
        url = f"{API}/user/repos?per_page=100&affiliation=owner,collaborator,organization_member"
    else:
        url = f"{API}/users/{LOGIN}/repos?per_page=100&type=owner"
    seen = set()
    for r in pages(url):
        if r["fork"] or r["full_name"] in seen:
            continue
        seen.add(r["full_name"])
        yield r["full_name"]


def commit_times():
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tz = dt.timezone(dt.timedelta(hours=OFFSET))
    shas = set()
    for repo in repositories():
        q = urllib.parse.urlencode({"author": LOGIN, "since": since, "per_page": 100})
        for c in pages(f"{API}/repos/{repo}/commits?{q}"):
            if c["sha"] in shas:
                continue
            shas.add(c["sha"])
            stamp = c["commit"]["author"]["date"]
            yield dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(tz)


COLORS = ["#1f6feb", "#00b4d8", "#7bd389", "#ffb703"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SANS = "font-family=\"'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif\""
MONO = "font-family=\"ui-monospace,'Cascadia Code',Consolas,Menlo,monospace\""


def sky(h):
    """Sky color of an hour: night, dawn, day, dusk."""
    stops = [(0, (12, 18, 40)), (5, (20, 30, 70)), (7, (255, 160, 90)), (10, (90, 170, 255)),
             (16, (90, 170, 255)), (19, (255, 120, 80)), (21, (40, 40, 100)), (24, (12, 18, 40))]
    for (h0, c0), (h1, c1) in zip(stops, stops[1:]):
        if h0 <= h <= h1:
            t = (h - h0) / (h1 - h0)
            return "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
    return "#0c1228"


def render(grid, total):
    W, H = 900, 440
    X0, Y0, CW, RH = 96, 178, 31, 26
    hours = [sum(grid[d][h] for d in range(7)) for h in range(24)]
    days = [sum(row) for row in grid]
    peak_h = max(range(24), key=lambda h: hours[h])
    peak_d = max(range(7), key=lambda d: days[d])
    top = max(max(row) for row in grid) or 1
    night = sum(hours[h] for h in list(range(0, 5)) + [22, 23])
    weekend = days[5] + days[6]
    if peak_h >= 21 or peak_h <= 4:
        persona = "🦉 night owl"
    elif peak_h <= 10:
        persona = "🐦 early bird"
    else:
        persona = "☀️ daytime shipper"

    peak_cell = max(((d, h) for d in range(7) for h in range(24)), key=lambda p: grid[p[0]][p[1]])
    out = []
    # hourly bars
    hmax = max(hours) or 1
    for h in range(24):
        bh = 4 + 52 * hours[h] / hmax
        x = X0 + h * CW + 6
        delay = 0.2 + h * 0.05
        fill = COLORS[min(3, int(4 * hours[h] / (hmax + 1)))]
        out.append(
            f'<rect class="bar" x="{x}" y="{Y0 - 14 - bh:.1f}" width="{CW - 12}" height="{bh:.1f}" rx="3" fill="{fill}" '
            f'style="animation-delay:{delay:.2f}s"><title>{h:02d}:00 · {hours[h]} commits</title></rect>'
        )
    # punch card
    for d in range(7):
        out.append(f'<text x="{X0 - 16}" y="{Y0 + d * RH + RH / 2 + 4}" text-anchor="end" {MONO} font-size="11" fill="#7d8590">{DAYS[d]}</text>')
        for h in range(24):
            n = grid[d][h]
            cx, cy = X0 + h * CW + CW / 2, Y0 + d * RH + RH / 2
            if n == 0:
                out.append(f'<circle cx="{cx}" cy="{cy}" r="1.6" fill="#30363d"/>')
                continue
            k = math.sqrt(n / top)
            r = 2.5 + 9.5 * k
            fill = COLORS[min(3, int(k * 4))]
            delay = 0.5 + h * 0.06 + d * 0.03
            if (d, h) == peak_cell:
                out.append(
                    f'<circle class="ring" cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="#ffd166" stroke-width="2" '
                    f'style="transform-origin:{cx}px {cy}px"/>'
                )
            out.append(
                f'<circle class="dot" cx="{cx}" cy="{cy}" r="{r:.1f}" fill="{fill}" style="animation-delay:{delay:.2f}s;transform-origin:{cx}px {cy}px">'
                f'<title>{DAYS[d]} {h:02d}:00 · {n} commits</title></circle>'
            )
    # sky strip and hour labels
    ys = Y0 + 7 * RH + 8
    stops = "".join(f'<stop offset="{h / 24:.3f}" stop-color="{sky(h)}"/>' for h in range(25))
    out.append(f'<defs><linearGradient id="sky" x1="0" x2="1">{stops}</linearGradient></defs>')
    out.append(f'<rect x="{X0}" y="{ys}" width="{24 * CW}" height="6" rx="3" fill="url(#sky)"/>')
    for h in range(0, 24, 3):
        out.append(f'<text x="{X0 + h * CW + CW / 2}" y="{ys + 22}" text-anchor="middle" {MONO} font-size="11" fill="#7d8590">{h:02d}</text>')
    # sweeping light over the hours
    sweep = (
        f'<rect class="sweep" x="{X0 - 40}" y="{Y0 - 72}" width="40" height="{7 * RH + 80}" fill="url(#beam)"/>'
    )

    stats = [
        (f"{peak_h:02d}:00", "peak hour"),
        (DAYS[peak_d], "busiest day"),
        (f"{round(100 * night / max(total, 1))}%", "22:00–05:00"),
        (f"{round(100 * weekend / max(total, 1))}%", "on weekends"),
    ]
    stat_svg = []
    for n, (value, label) in enumerate(stats):
        sx = W - 36 - (len(stats) - 1 - n) * 112
        stat_svg.append(
            f'<text x="{sx}" y="50" text-anchor="end" {SANS} font-size="22" font-weight="700" fill="#e6edf3">{value}</text>'
            f'<text x="{sx}" y="70" text-anchor="end" {MONO} font-size="10.5" fill="#7d8590">{label}</text>'
        )

    utc = f"UTC{OFFSET:+g}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{LOGIN}: commit times by weekday and hour, peak at {peak_h:02d}:00">
<style>
.bar{{animation:grow .8s cubic-bezier(.2,1.3,.4,1) both;transform-box:fill-box;transform-origin:50% 100%}}
@keyframes grow{{from{{transform:scaleY(0)}}}}
.dot{{animation:pop .6s cubic-bezier(.2,1.6,.4,1) both}}
@keyframes pop{{from{{transform:scale(0)}}}}
.ring{{animation:ring 2.4s ease-out 3s infinite;opacity:0}}
@keyframes ring{{0%{{transform:scale(1);opacity:.9}}100%{{transform:scale(2.6);opacity:0}}}}
.sweep{{animation:sweep 7s linear 2.5s infinite;opacity:0}}
@keyframes sweep{{0%{{transform:translateX(0);opacity:0}}8%{{opacity:1}}92%{{opacity:1}}100%{{transform:translateX({24 * CW + 40}px);opacity:0}}}}
.fade{{animation:fade 1s ease .1s both}}
@keyframes fade{{from{{opacity:0}}}}
</style>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0d1117"/><stop offset="1" stop-color="#14112a"/></linearGradient>
<linearGradient id="beam" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#cfe3ff" stop-opacity=".09"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
</defs>
<rect width="{W}" height="{H}" rx="14" fill="url(#bg)"/>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="13.5" fill="none" stroke="#30363d"/>
<g class="fade">
<text x="36" y="46" {SANS} font-size="20" font-weight="700" fill="#e6edf3">When I ship</text>
<text x="36" y="68" {MONO} font-size="11" fill="#7d8590">{total:,} commits · last 12 months · {utc}</text>
<rect x="36" y="80" width="{12 + 8.2 * len(persona)}" height="22" rx="11" fill="#1f6feb" fill-opacity=".16" stroke="#1f6feb" stroke-opacity=".5"/>
<text x="48" y="95" {SANS} font-size="12" font-weight="600" fill="#a5d6ff">{persona}</text>
{"".join(stat_svg)}
</g>
{sweep}
{chr(10).join(out)}
</svg>
"""


if __name__ == "__main__":
    grid = [[0] * 24 for _ in range(7)]
    total = 0
    for t in commit_times():
        grid[t.weekday()][t.hour] += 1
        total += 1
    if total == 0:
        raise SystemExit("no commits found: check the token")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(grid, total))
    print(f"wrote {OUT}: {total} commits")
