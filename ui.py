"""
The look of Datalyst: a light, frosted-glass design (inspired by Apple's
visionOS / macOS). Colours, glass cards, sidebar, buttons, charts and the
page-change animation all live here, so app.py stays about the product.
"""

from safe_numbers import is_whole
import re

import altair as alt
import pandas as pd


# ------------------------------------------------------------
# Colours
# ------------------------------------------------------------

PALETTE = [
    "#0a84ff", "#5e5ce6", "#bf5af2", "#ff375f",
    "#ff9f0a", "#30d158", "#64d2ff", "#ac8e68",
]

FONT = (
    "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', "
    "'Inter', 'Helvetica Neue', Arial, sans-serif"
)


# ------------------------------------------------------------
# Icons (simple line icons, 24x24, drawn with a stroke)
# ------------------------------------------------------------

ICON_PATHS = {
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>',
    "chat": '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "chart": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    "sliders": '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "scale": '<line x1="12" y1="3" x2="12" y2="21"/><path d="M5 7l-3 8a4 4 0 0 0 6 0z"/><path d="M19 7l-3 8a4 4 0 0 0 6 0z"/><line x1="7" y1="21" x2="17" y2="21"/><line x1="5" y1="7" x2="19" y2="7"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
    "sparkle": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
    "alert": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
}


def icon_svg(name, size=20, stroke=2):
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{ICON_PATHS[name]}</svg>'
    )


def _mask_url(name):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="black" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{ICON_PATHS[name]}</svg>'
    )
    encoded = (
        svg.replace("%", "%25").replace("<", "%3C").replace(">", "%3E")
        .replace("#", "%23").replace('"', "'")
    )
    return f'url("data:image/svg+xml,{encoded}")'


# The sidebar menu, in order: (page name, icon)
NAV = [
    ("Dashboard", "grid"),
    ("Ask AI", "chat"),
    ("Insights", "zap"),
    ("Visualize", "chart"),
    ("Report", "file"),
    ("Data", "database"),
    ("Clean", "sliders"),
]


def _nav_icon_css():
    rules = []

    for position, (_, icon) in enumerate(NAV, start=1):
        rules.append(
            f'[data-testid="stSidebar"] [role="radiogroup"] > label:nth-of-type({position})::before,'
            f'[data-testid="stSidebar"] [role="radiogroup"] > div:nth-of-type({position}) > label::before'
            f"{{--icon:{_mask_url(icon)};}}"
        )

    return "\n".join(rules)


# ------------------------------------------------------------
# The stylesheet
# ------------------------------------------------------------

CSS = r"""
:root {
  color-scheme: light;
  --ink: #1d1d1f;
  --ink2: #515154;
  --ink3: #86868b;
  --accent: #0a84ff;
  --accent2: #5e5ce6;
  --glass: rgba(255, 255, 255, 0.58);
  --glass-strong: rgba(255, 255, 255, 0.80);
  --stroke: rgba(255, 255, 255, 0.88);
  --line: rgba(60, 72, 120, 0.10);
  --shadow: 0 10px 40px rgba(60, 72, 120, 0.10), 0 2px 8px rgba(60, 72, 120, 0.05);
  --shadow-hover: 0 22px 60px rgba(60, 72, 120, 0.18), 0 4px 14px rgba(60, 72, 120, 0.08);
  --ease: cubic-bezier(0.2, 0.8, 0.2, 1);
}

/* ---------- page background: a soft colour mesh ---------- */
html, body, .stApp,
.stApp :is(div, p, span, label, button, input, textarea, select, h1, h2, h3, h4, h5, h6, a, li, td, th, summary, small, strong, em, code):not([data-testid="stIconMaterial"]):not([class*="material"]) {
  font-family: __FONT__ !important;
}
html, body, .stApp {
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
}
[data-testid="stPopoverBody"], [data-testid="stPopoverBody"] :is(div, p, span, button, label) { font-family: __FONT__ !important; }
.stApp :is(code, pre, .codeblock) { font-family: 'SF Mono', ui-monospace, Menlo, Consolas, monospace !important; }
.stApp {
  background:
    radial-gradient(1100px 700px at 6% -8%, #cfe2ff 0%, transparent 62%),
    radial-gradient(900px 620px at 98% 2%, #e6dcff 0%, transparent 58%),
    radial-gradient(1000px 700px at 96% 102%, #ffdcec 0%, transparent 58%),
    radial-gradient(900px 700px at -4% 104%, #d5f6ea 0%, transparent 58%),
    #f4f6fb;
  background-attachment: fixed;
}
.stApp::before {
  content: "";
  position: fixed;
  inset: -10%;
  z-index: 0;
  pointer-events: none;
  background:
    radial-gradient(420px 420px at 70% 20%, rgba(10, 132, 255, 0.10), transparent 70%),
    radial-gradient(520px 520px at 20% 80%, rgba(191, 90, 242, 0.09), transparent 70%);
  animation: drift 26s ease-in-out infinite alternate;
}
@keyframes drift {
  from { transform: translate3d(-2%, -1%, 0) scale(1); }
  to   { transform: translate3d(3%, 2%, 0) scale(1.08); }
}

/* ---------- hide Streamlit's own chrome ---------- */
#MainMenu, footer { visibility: hidden; }
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stAppDeployButton"] { display: none !important; }
[data-testid="stHeader"] { background: transparent !important; }

/* ---------- the page: fades and slides in when you change pages ---------- */
[data-testid="stMainBlockContainer"] {
  max-width: 1240px;
  padding: 2.4rem 2.6rem 4rem !important;
  margin: 0 auto;
  animation: pageIn___PAGE__ 0.6s var(--ease) both;
}
@keyframes pageIn___PAGE__ {
  from { opacity: 0; transform: translateY(16px) scale(0.994); filter: blur(5px); }
  to   { opacity: 1; transform: none; filter: blur(0); }
}
[data-stale="true"] { opacity: 0.6 !important; transition: opacity 0.25s ease; }

/* ---------- sidebar: frosted glass ---------- */
[data-testid="stSidebar"] {
  min-width: 276px !important;
  max-width: 276px !important;
  width: 276px !important;
  background: rgba(255, 255, 255, 0.46) !important;
  backdrop-filter: blur(36px) saturate(185%);
  -webkit-backdrop-filter: blur(36px) saturate(185%);
  border-right: 1px solid rgba(255, 255, 255, 0.75);
  box-shadow: 10px 0 50px rgba(60, 72, 120, 0.07);
}
[data-testid="stSidebar"] > div:first-child { background: transparent !important; }
[data-testid="stSidebarHeader"] { height: 0; padding: 0; }
[data-testid="stSidebarUserContent"] { padding: 1.6rem 1.1rem 1.2rem !important; }

.brand { display: flex; align-items: center; gap: 12px; padding: 4px 8px 22px; }
.brand-logo {
  width: 42px; height: 42px; border-radius: 13px; flex: none;
  display: grid; place-items: center; color: #fff;
  background: linear-gradient(145deg, #4fa3ff 0%, #0a6cf5 45%, #5e5ce6 100%);
  box-shadow: 0 10px 24px rgba(10, 108, 245, 0.38), inset 0 1.5px 0 rgba(255, 255, 255, 0.6);
  position: relative; overflow: hidden;
}
.brand-logo::after {
  content: ""; position: absolute; left: 0; right: 0; top: 0; height: 52%;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.45), rgba(255, 255, 255, 0));
}
.brand-name { font-size: 20px; font-weight: 750; letter-spacing: -0.03em; line-height: 1.1; }
.brand-tag { font-size: 11.5px; color: var(--ink3); font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; }

.nav-label {
  font-size: 11px; font-weight: 700; color: var(--ink3); letter-spacing: 0.09em;
  text-transform: uppercase; padding: 4px 12px 8px;
}

/* the menu: radio buttons turned into glass pills */
[data-testid="stSidebar"] [data-testid="stRadio"] > label { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 5px; flex-direction: column; }
[data-testid="stSidebar"] [role="radiogroup"] > div { width: 100%; }   /* newer Streamlit wraps each option */
[data-testid="stSidebar"] [role="radiogroup"] label {
  width: 100%; margin: 0; padding: 11px 14px; border-radius: 15px;
  display: flex; align-items: center; gap: 13px; cursor: pointer; position: relative;
  border: 1px solid transparent; background: transparent;
  transition: background 0.28s var(--ease), border-color 0.28s var(--ease),
              transform 0.28s var(--ease), box-shadow 0.28s var(--ease);
}
[data-testid="stSidebar"] [role="radiogroup"] label > div:not(:has([data-testid="stMarkdownContainer"])),
[data-testid="stSidebar"] [role="radiogroup"] label > div > div:first-child:not([data-testid="stMarkdownContainer"]):not(:has([data-testid="stMarkdownContainer"])) { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] label::before {
  content: ""; width: 19px; height: 19px; flex: none; background-color: #8e8e93;
  -webkit-mask: var(--icon) center / contain no-repeat;
  mask: var(--icon) center / contain no-repeat;
  transition: background-color 0.28s var(--ease), transform 0.28s var(--ease);
}
[data-testid="stSidebar"] [role="radiogroup"] label p {
  font-size: 14.5px !important; font-weight: 550; color: var(--ink2); margin: 0;
  transition: color 0.28s var(--ease);
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {
  background: rgba(255, 255, 255, 0.62); border-color: rgba(255, 255, 255, 0.9);
  transform: translateX(3px); box-shadow: 0 6px 18px rgba(60, 72, 120, 0.08);
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover::before { transform: scale(1.1); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(255, 255, 255, 0.72));
  border-color: #fff;
  box-shadow: 0 10px 26px rgba(10, 132, 255, 0.20), inset 0 1px 0 #fff;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked)::before { background-color: var(--accent); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p { color: var(--accent); font-weight: 650; }
__NAV_ICONS__

.dataset-card { padding: 14px 16px; margin: 20px 0 6px; border-radius: 18px; }
.dataset-card .name { font-weight: 650; font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dataset-card .meta { font-size: 12.5px; color: var(--ink3); margin-top: 2px; }
.dataset-card .dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:#30d158; margin-right:7px; box-shadow:0 0 0 4px rgba(48,209,88,.18); }
.ai-status { display:flex; align-items:flex-start; gap:8px; margin:10px 4px 0; padding:9px 12px; border-radius:14px; font-size:12.5px; font-weight:600; background:rgba(255,255,255,.55); border:1px solid rgba(255,255,255,.7); }
.ai-status .dot { width:8px; height:8px; border-radius:50%; flex:none; margin-top:4px; }
.ai-status.green .dot { background:#30d158; box-shadow:0 0 0 4px rgba(48,209,88,.18); }
.ai-status.red .dot { background:#ff453a; box-shadow:0 0 0 4px rgba(255,69,58,.16); }
.ai-status.amber .dot { background:#ff9f0a; box-shadow:0 0 0 4px rgba(255,159,10,.18); }
.ai-status .hint { display:block; font-weight:500; color:#6e6e73; font-size:11.5px; margin-top:2px; }
.problem ol { margin:8px 0 0 18px; padding:0; color:#3a3a3c; font-size:14.5px; line-height:1.6; }
.problem .eyebrow { color:#ff9f0a; }

/* Clean page */
.kpi .delta { display:inline-block; margin-top:10px; font-size:12px; font-weight:700; padding:3px 10px; border-radius:999px; }
.kpi .delta.good { color:#1f9d46; background:rgba(48,209,88,.14); }
.kpi .delta.same { color:#6e6e73; background:rgba(120,120,128,.12); }
.kpi .delta.worse { color:#c77700; background:rgba(255,159,10,.15); }
.changes { display:flex; flex-direction:column; gap:10px; margin:10px 0 6px; }
.change { display:flex; gap:12px; align-items:flex-start; padding:12px 16px; border-radius:16px; font-size:14.5px; line-height:1.45;
  background:rgba(255,255,255,.62); border:1px solid rgba(255,255,255,.85); box-shadow:0 6px 18px rgba(31,38,135,.06), inset 0 1px 0 rgba(255,255,255,.9); }
.change .tick { flex:none; width:24px; height:24px; border-radius:50%; display:grid; place-items:center; color:#fff;
  background:linear-gradient(145deg,#5ee07f,#1fb24f); box-shadow:0 5px 12px rgba(48,209,88,.32); }
.change.none { color:#6e6e73; }
.sev { display:inline-block; font-size:10.5px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; padding:3px 9px; border-radius:999px; margin-right:9px; vertical-align:1px; }
.sev.high { color:#d63a2f; background:rgba(255,69,58,.12); }
.sev.medium { color:#c77700; background:rgba(255,159,10,.15); }
.sev.info { color:#0a6cf5; background:rgba(10,132,255,.11); }
.sev.advice { color:#6e6e73; background:rgba(120,120,128,.14); }
.issue-detail { font-size:13.5px; color:var(--ink3); line-height:1.5; margin:-4px 0 8px 34px; }
.issue-title { font-size:15px; font-weight:650; margin:4px 0 6px; }
[class*="st-key-issue-"] { background:rgba(255,255,255,.55); border:1px solid rgba(255,255,255,.85); border-radius:18px;
  padding:12px 18px 6px; margin-bottom:10px; box-shadow:0 6px 18px rgba(31,38,135,.05), inset 0 1px 0 rgba(255,255,255,.9); }
[class*="st-key-issue-"] label p { font-weight:650; }
button[role="tab"][aria-selected="true"], button[role="tab"][aria-selected="true"] p { color:#0058c0 !important; }
.st-key-glass-tour { margin-bottom: 14px; }
.st-key-glass-tour .stButton { margin-top: 6px; }

/* ---------- glass cards ---------- */
.glass, [class*="st-key-glass-"] {
  background: var(--glass);
  backdrop-filter: blur(22px) saturate(175%);
  -webkit-backdrop-filter: blur(22px) saturate(175%);
  border: 1px solid var(--stroke);
  border-radius: 26px;
  box-shadow: var(--shadow), inset 0 1px 0 rgba(255, 255, 255, 0.95);
  transition: transform 0.35s var(--ease), box-shadow 0.35s var(--ease);
}
[class*="st-key-glass-"] { padding: 22px 24px !important; }
[class*="st-key-glass-"]:hover { box-shadow: var(--shadow-hover), inset 0 1px 0 rgba(255, 255, 255, 0.95); }

.card-title { font-size: 15px; font-weight: 650; letter-spacing: -0.01em; margin: 0 0 2px; }
.card-sub { font-size: 12.5px; color: var(--ink3); margin: 0 0 8px; }

/* hero */
.hero { margin: 2px 0 26px; }
.hero .eyebrow { font-size: 12px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); margin-bottom: 8px; }
.hero .title { font-size: 40px; font-weight: 760; letter-spacing: -0.04em; line-height: 1.08; margin: 0; text-wrap: balance; }
.hero .subtitle { color: var(--ink2); font-size: 16.5px; margin: 10px 0 0; max-width: 720px; line-height: 1.5; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.chip {
  display: inline-flex; align-items: center; gap: 7px; padding: 6px 13px; border-radius: 999px;
  background: rgba(255, 255, 255, 0.72); border: 1px solid rgba(255, 255, 255, 0.95);
  box-shadow: 0 2px 10px rgba(60, 72, 120, 0.06), inset 0 1px 0 #fff;
  font-size: 12.5px; font-weight: 600; color: var(--ink2);
}
.chip.blue { color: #0a6cf5; background: rgba(10, 132, 255, 0.10); border-color: rgba(10, 132, 255, 0.18); }
.chip.green { color: #1f9d46; background: rgba(48, 209, 88, 0.12); border-color: rgba(48, 209, 88, 0.22); }
.chip.orange { color: #c77700; background: rgba(255, 159, 10, 0.13); border-color: rgba(255, 159, 10, 0.25); }

/* KPI cards */
.kpi-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; margin-bottom: 18px; }
.kpi {
  padding: 22px 22px 20px; position: relative; overflow: hidden;
  animation: rise 0.7s var(--ease) both; animation-delay: calc(var(--i, 0) * 80ms);
  cursor: default;
}
.kpi:hover { transform: translateY(-5px); box-shadow: var(--shadow-hover), inset 0 1px 0 rgba(255,255,255,.95); }
.kpi::after {
  content: ""; position: absolute; right: -40px; top: -40px; width: 130px; height: 130px;
  border-radius: 50%; background: radial-gradient(circle, rgba(var(--rgb), 0.18), transparent 70%);
}
.kpi .ico {
  width: 42px; height: 42px; border-radius: 13px; display: grid; place-items: center; color: #fff;
  background: linear-gradient(145deg, var(--c1), var(--c2));
  box-shadow: 0 10px 22px rgba(var(--rgb), 0.36), inset 0 1.5px 0 rgba(255, 255, 255, 0.5);
}
.kpi .label { font-size: 13.5px; color: var(--ink3); font-weight: 600; margin-top: 16px; }
.kpi .value { font-size: 34px; font-weight: 740; letter-spacing: -0.04em; line-height: 1.1; margin-top: 4px; }
.kpi .sub { font-size: 13px; color: var(--ink3); margin-top: 6px; }
.kpi.blue   { --c1: #4fa3ff; --c2: #0a6cf5; --rgb: 10,132,255; }
.kpi.purple { --c1: #cf7bff; --c2: #7d5cf0; --rgb: 125,92,240; }
.kpi.teal   { --c1: #6fe0ff; --c2: #1aa8d6; --rgb: 26,168,214; }
.kpi.green  { --c1: #5ee07f; --c2: #1fb24f; --rgb: 31,178,79; }
.kpi.orange { --c1: #ffb84d; --c2: #f08a00; --rgb: 240,138,0; }
@keyframes rise { from { opacity: 0; transform: translateY(22px); } to { opacity: 1; transform: none; } }

/* highlights list */
.hl { display: flex; gap: 12px; padding: 11px 0; border-bottom: 1px solid var(--line); font-size: 14px; line-height: 1.45; color: var(--ink2); }
.hl:last-child { border-bottom: none; }
.hl .bullet { width: 8px; height: 8px; border-radius: 50%; margin-top: 7px; flex: none; background: linear-gradient(135deg, #4fa3ff, #5e5ce6); box-shadow: 0 0 0 4px rgba(10,132,255,.12); }

/* Ask AI: the answer */
.answer { padding: 30px 32px; animation: rise 0.6s var(--ease) both; }
.answer .eyebrow { font-size: 12px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); }
.answer .big {
  font-size: 58px; font-weight: 760; letter-spacing: -0.045em; line-height: 1.05; margin: 8px 0 6px;
  background: linear-gradient(135deg, #0a84ff 0%, #5e5ce6 55%, #bf5af2 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent; word-break: break-word;
}
.answer .big.small { font-size: 40px; }
.answer .text { color: var(--ink2); font-size: 16.5px; line-height: 1.5; }
.answer.warn .eyebrow { color: #c77700; }
.answer.warn .text { color: var(--ink); font-size: 17px; }
.answer .question { font-size: 13.5px; color: var(--ink3); margin-bottom: 14px; display: flex; gap: 8px; align-items: center; }

.insight { padding: 22px 26px; display: flex; gap: 16px; align-items: flex-start; animation: rise 0.6s var(--ease) both; background: linear-gradient(135deg, rgba(10,132,255,.09), rgba(191,90,242,.08)), var(--glass); }
.insight .ico { width: 38px; height: 38px; border-radius: 12px; flex: none; display: grid; place-items: center; color: #fff; background: linear-gradient(145deg, #cf7bff, #7d5cf0); box-shadow: 0 8px 18px rgba(125,92,240,.35), inset 0 1.5px 0 rgba(255,255,255,.5); }
.insight .head { font-size: 12px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #7d5cf0; }
.insight .body { font-size: 16px; line-height: 1.55; color: var(--ink); margin-top: 4px; }
.insight .foot { font-size: 12.5px; color: var(--ink3); margin-top: 8px; display: flex; gap: 6px; align-items: center; }

.steps { display: flex; gap: 10px; flex-wrap: wrap; margin: 4px 0 14px; }
.step { flex: 1; min-width: 160px; padding: 12px 14px; border-radius: 16px; background: rgba(255,255,255,.7); border: 1px solid rgba(255,255,255,.95); }
.step .n { font-size: 11px; font-weight: 700; color: var(--accent); letter-spacing: .08em; }
.step .t { font-size: 13.5px; font-weight: 600; margin-top: 2px; }
.step .d { font-size: 12.5px; color: var(--ink3); margin-top: 2px; }
.codeblock {
  font-family: 'SF Mono', ui-monospace, Menlo, Consolas, monospace; font-size: 12.5px; line-height: 1.55;
  background: rgba(255, 255, 255, 0.7); border: 1px solid rgba(255, 255, 255, 0.95); border-radius: 16px;
  padding: 14px 16px; white-space: pre-wrap; word-break: break-word; color: #3a3a3c;
}

/* Insights page cards */
.insight-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.ins { padding: 22px 24px; animation: rise 0.65s var(--ease) both; animation-delay: calc(var(--i, 0) * 70ms); }
.ins:hover { transform: translateY(-4px); box-shadow: var(--shadow-hover), inset 0 1px 0 rgba(255,255,255,.95); }
.ins .tag { display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; padding: 4px 10px; border-radius: 999px; }
.ins .tag.Opportunity { color: #1f9d46; background: rgba(48,209,88,.14); }
.ins .tag.Watch { color: #c77700; background: rgba(255,159,10,.15); }
.ins .tag.Fact { color: #0a6cf5; background: rgba(10,132,255,.11); }
.ins .t { font-size: 17px; font-weight: 680; letter-spacing: -.02em; margin: 12px 0 6px; }
.ins .d { font-size: 14.5px; line-height: 1.55; color: var(--ink2); }

/* coming soon + landing */
.soon { padding: 44px 40px; text-align: center; }
.soon .ico { width: 64px; height: 64px; margin: 0 auto 18px; border-radius: 20px; display: grid; place-items: center; color: #fff; background: linear-gradient(145deg, #4fa3ff, #5e5ce6); box-shadow: 0 16px 34px rgba(10,132,255,.32), inset 0 2px 0 rgba(255,255,255,.5); }
.soon .t { font-size: 26px; font-weight: 740; letter-spacing: -.03em; }
.soon .d { color: var(--ink2); margin: 10px auto 0; max-width: 520px; line-height: 1.55; }
.how { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 16px; margin-top: 26px; }
.how .glass { padding: 20px 22px; animation: rise .7s var(--ease) both; animation-delay: calc(var(--i,0) * 90ms); }
.how .n { font-size: 12px; font-weight: 700; color: var(--accent); letter-spacing: .1em; }
.how .t { font-size: 16px; font-weight: 680; margin-top: 6px; }
.how .d { font-size: 13.5px; color: var(--ink3); margin-top: 4px; line-height: 1.5; }

/* ---------- buttons: glass pills ---------- */
.stButton > button, .stDownloadButton > button,
[data-testid^="stBaseButton-secondary"] {
  border-radius: 14px !important; border: 1px solid rgba(255, 255, 255, 0.95) !important;
  background: rgba(255, 255, 255, 0.72) !important; color: var(--ink) !important;
  font-weight: 560 !important; padding: 0.55rem 1.15rem !important;
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 4px 16px rgba(60, 72, 120, 0.09), inset 0 1px 0 #fff !important;
  transition: transform 0.22s var(--ease), box-shadow 0.22s var(--ease), background 0.22s var(--ease) !important;
}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid^="stBaseButton-secondary"]:hover {
  transform: translateY(-2px); background: rgba(255, 255, 255, 0.95) !important;
  box-shadow: 0 12px 28px rgba(60, 72, 120, 0.16), inset 0 1px 0 #fff !important;
  color: var(--accent) !important;
}
.stButton > button:active, [data-testid^="stBaseButton-secondary"]:active { transform: scale(0.97); }
.stButton > button[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(180deg, #4fa8ff 0%, #0a7aff 55%, #0a6cf5 100%) !important;
  color: #fff !important; border: 1px solid rgba(255, 255, 255, 0.4) !important;
  box-shadow: 0 10px 26px rgba(10, 132, 255, 0.38), inset 0 1.5px 0 rgba(255, 255, 255, 0.55) !important;
  letter-spacing: 0.01em;
}
.stButton > button[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: linear-gradient(180deg, #62b3ff 0%, #1a86ff 55%, #0a72ff 100%) !important;
  color: #fff !important; box-shadow: 0 16px 34px rgba(10, 132, 255, 0.48), inset 0 1.5px 0 rgba(255, 255, 255, 0.6) !important;
}
button p { color: inherit !important; }

/* ---------- inputs ---------- */
[data-testid="stTextInputRootElement"], [data-baseweb="select"] > div, [data-baseweb="input"] {
  border-radius: 16px !important; border: 1px solid rgba(255, 255, 255, 0.95) !important;
  background: rgba(255, 255, 255, 0.78) !important;
  box-shadow: 0 4px 16px rgba(60, 72, 120, 0.08), inset 0 1px 0 #fff;
  transition: box-shadow 0.25s var(--ease), border-color 0.25s var(--ease);
}
[data-testid="stTextInputRootElement"]:focus-within, [data-baseweb="select"] > div:focus-within {
  box-shadow: 0 0 0 4px rgba(10, 132, 255, 0.20), 0 8px 24px rgba(10, 132, 255, 0.12) !important;
  border-color: rgba(10, 132, 255, 0.55) !important;
}
[data-baseweb="base-input"] { background: transparent !important; }
[data-testid="stTextInput"] input {
  font-size: 1.04rem !important; padding: 0.95rem 1.1rem !important; color: var(--ink) !important;
  background: transparent !important;
}
[data-testid="stTextInput"] input::placeholder { color: var(--ink3) !important; }
/* a tall, premium search field with a matching button */
.st-key-glass-form [data-testid="stTextInputRootElement"] { min-height: 56px; }
.st-key-glass-form [data-testid="stTextInput"] input { height: 54px; padding: 0 1.2rem !important; font-size: 1.08rem !important; }
.st-key-glass-form [data-testid="stFormSubmitButton"] button { min-height: 56px; font-size: 1.02rem; border-radius: 16px !important; }
[class*="st-key-glass-"] .stButton > button { height: 62px; min-height: 62px; padding: 6px 16px !important; display: flex; align-items: center; justify-content: center; line-height: 1.3; font-size: 14.5px; }

/* space between the stacked cards */
.answer, .insight, .glass.soon { margin-bottom: 18px; }
[class*="st-key-glass-"] { margin-bottom: 4px; }
[data-testid="stWidgetLabel"] p { font-weight: 600; color: var(--ink2); font-size: 13.5px; }

/* file upload */
[data-testid="stFileUploaderDropzone"] {
  border: 1.6px dashed rgba(10, 132, 255, 0.38) !important; border-radius: 24px !important;
  background: rgba(255, 255, 255, 0.55) !important; padding: 2.4rem 1.6rem !important;
  backdrop-filter: blur(16px); transition: all 0.3s var(--ease);
}
[data-testid="stFileUploaderDropzone"]:hover {
  border-color: var(--accent) !important; background: rgba(255, 255, 255, 0.85) !important;
  transform: scale(1.006); box-shadow: 0 16px 40px rgba(10, 132, 255, 0.14);
}
[data-testid="stFileUploaderDropzone"] small, [data-testid="stFileUploaderDropzoneInstructions"] span { color: var(--ink3) !important; }
[data-testid="stFileUploader"] section { background: transparent !important; }

/* form without its default box */
[data-testid="stForm"] { border: none !important; padding: 0 !important; background: transparent !important; }

/* ---------- expanders ---------- */
[data-testid="stExpander"] {
  border-radius: 22px !important; border: 1px solid var(--stroke) !important;
  background: var(--glass) !important; backdrop-filter: blur(20px) saturate(170%);
  box-shadow: var(--shadow); overflow: hidden;
}
[data-testid="stExpander"] details { border: none !important; background: transparent !important; }
[data-testid="stExpander"] summary { padding: 15px 20px !important; font-weight: 620; transition: background .2s; }
[data-testid="stExpander"] summary:hover { background: rgba(255,255,255,.5) !important; }
[data-testid="stExpanderDetails"] { padding: 4px 20px 18px !important; }

/* ---------- tabs ---------- */
[data-baseweb="tab-list"] {
  gap: 4px !important; padding: 5px !important; border-radius: 16px; width: fit-content;
  background: rgba(255,255,255,.55); border: 1px solid rgba(255,255,255,.9); box-shadow: 0 4px 14px rgba(60,72,120,.07);
}
button[role="tab"] { border-radius: 12px !important; padding: 8px 18px !important; font-weight: 600 !important; color: var(--ink2) !important; transition: all .25s var(--ease); }
button[role="tab"][aria-selected="true"] { background: #fff !important; color: var(--accent) !important; box-shadow: 0 4px 14px rgba(60,72,120,.12); }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none !important; }

/* ---------- alerts ---------- */
[data-testid="stAlert"] {
  border-radius: 18px !important; border: 1px solid rgba(255,255,255,.9) !important;
  backdrop-filter: blur(16px); box-shadow: var(--shadow);
}

/* ---------- tables ---------- */
[data-testid="stDataFrame"] {
  border-radius: 20px; overflow: hidden; border: 1px solid var(--stroke);
  box-shadow: var(--shadow); background: rgba(255,255,255,.7);
}

/* ---------- headings on the older pages (Data, Clean) ---------- */
[data-testid="stMainBlockContainer"] h2, [data-testid="stMainBlockContainer"] h3 {
  letter-spacing: -0.025em; font-weight: 700; margin-top: 1.6rem;
}
[data-testid="stMainBlockContainer"] h3 { font-size: 1.35rem; }

/* main-area radio (used as a segmented control) */
[data-testid="stMain"] [role="radiogroup"] { gap: 6px; }
[data-testid="stMain"] [role="radiogroup"] label {
  background: rgba(255,255,255,.65); border: 1px solid rgba(255,255,255,.95); border-radius: 12px;
  padding: 7px 16px; margin: 0; transition: all .22s var(--ease); cursor: pointer;
  box-shadow: 0 2px 8px rgba(60,72,120,.06);
}
[data-testid="stMain"] [role="radiogroup"] label > div:not(:has([data-testid="stMarkdownContainer"])),
[data-testid="stMain"] [role="radiogroup"] label > div > div:first-child:not([data-testid="stMarkdownContainer"]):not(:has([data-testid="stMarkdownContainer"])) { display: none; }
[data-testid="stMain"] [role="radiogroup"] label { padding: 7px 14px !important; }
[data-testid="stMain"] [role="radiogroup"] label > div:last-child { margin: 0 !important; padding: 0 !important; }
[data-testid="stMain"] [role="radiogroup"] label p { margin: 0; }
[data-testid="stMain"] [role="radiogroup"] label:has(input:checked) { background: #fff; border-color: rgba(10,132,255,.4); box-shadow: 0 6px 18px rgba(10,132,255,.20); }
[data-testid="stMain"] [role="radiogroup"] label:has(input:checked) p { color: var(--accent); font-weight: 650; }
[data-testid="stMain"] [role="radiogroup"] label:hover { transform: translateY(-1px); }

/* slim scrollbars */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: rgba(60,72,120,.18); border-radius: 10px; border: 2px solid transparent; background-clip: content-box; }
::-webkit-scrollbar-thumb:hover { background: rgba(60,72,120,.32); background-clip: content-box; border: 2px solid transparent; }

/* ---------- dashboard builder ---------- */
[class*="st-key-glass-tile-"] { position: relative; animation: rise 0.5s var(--ease) both; }
[class*="st-key-glass-tile-"] .card-title { padding-right: 44px; }
[class*="st-key-glass-tile-"] [data-testid="stPopover"] { position: absolute; top: 12px; right: 12px; width: auto; z-index: 3; }
[class*="st-key-glass-tile-"] [data-testid="stPopover"] button {
  height: 32px; min-height: 32px; width: 38px; padding: 0 !important; border-radius: 11px !important;
  opacity: 0.5; font-size: 18px; line-height: 1;
}
[class*="st-key-glass-tile-"]:hover [data-testid="stPopover"] button { opacity: 1; }
[class*="st-key-glass-tile-"] [data-testid="stPopover"] button svg,
[class*="st-key-glass-tile-"] [data-testid="stPopover"] button [data-testid="stIconMaterial"] { display: none; }
[class*="st-key-glass-tile-"] [data-testid="stPopover"] button p { font-size: 20px; margin: 0; line-height: 1; letter-spacing: 1px; }
.st-key-glass-filters .stButton > button { height: 44px; min-height: 44px; padding: 0 16px !important; }
[data-testid="stPills"] button, [data-testid="stPills"] [role="button"] { border-radius: 999px !important; font-weight: 560; transition: all .2s var(--ease); }
[data-testid="stPills"] button:hover { transform: translateY(-1px); }
[data-testid="stPopoverBody"] {
  border-radius: 18px !important; background: rgba(255,255,255,.94) !important;
  backdrop-filter: blur(24px); border: 1px solid #fff !important; box-shadow: var(--shadow-hover) !important;
  padding: 10px !important;
}
.tile-kpi { padding: 2px 0 2px; }
.tile-kpi .tt { font-size: 13.5px; font-weight: 650; color: var(--ink3); padding-right: 30px; min-height: 38px; line-height: 1.35; }
.tile-kpi .tv {
  font-size: 34px; font-weight: 750; letter-spacing: -0.04em; line-height: 1.15; margin: 8px 0 4px;
  background: linear-gradient(135deg, var(--c1), var(--c2)); -webkit-background-clip: text; background-clip: text; color: transparent;
}
.tile-kpi .ts { font-size: 12.5px; color: var(--ink3); }
.tile-kpi.blue   { --c1: #4fa3ff; --c2: #0a6cf5; }
.tile-kpi.purple { --c1: #cf7bff; --c2: #7d5cf0; }
.tile-kpi.teal   { --c1: #4fd0f5; --c2: #1190bd; }
.tile-kpi.green  { --c1: #4fd77a; --c2: #17a045; }
.tile-kpi.orange { --c1: #ffb84d; --c2: #e07b00; }
.tile-msg { padding: 22px 18px; border-radius: 16px; background: rgba(255,255,255,.6); color: var(--ink2); font-size: 14px; line-height: 1.5; text-align: center; }
.tile-msg.error { background: rgba(255,159,10,.13); color: #8a5300; }
.filter-count { font-size: 12.5px; color: var(--ink3); margin: 10px 0 12px; }
.empty-state { padding: 38px 30px; text-align: center; }
.empty-state .t { font-size: 20px; font-weight: 700; letter-spacing: -.02em; }
.empty-state .d { color: var(--ink2); margin-top: 6px; }
.st-key-glass-toolbar .stButton > button, .st-key-glass-editor .stButton > button { height: 48px; min-height: 48px; padding: 0 18px !important; }
.st-key-glass-toolbar, .st-key-glass-editor, .st-key-glass-filters, .st-key-glass-report, .st-key-glass-report-done { margin-bottom: 14px; }
.st-key-glass-report .stButton { margin-top: 12px; }
.understood { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 2px 0 16px; font-size: 13px; color: var(--ink3); }
.understood .lead { font-weight: 650; margin-right: 2px; }

/* ---------- answers: values and notices ---------- */
.valchips { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 0 0 16px; }
.valchips .lead { font-size: 13px; font-weight: 650; color: var(--ink3); margin-right: 2px; }
.valchips .chip b { color: var(--ink3); font-weight: 600; margin-left: 2px; }
.notice {
  display: flex; gap: 10px; align-items: flex-start; padding: 12px 16px; margin: 0 0 12px; border-radius: 16px;
  background: rgba(255, 159, 10, 0.12); border: 1px solid rgba(255, 159, 10, 0.25); color: #8a5300; font-size: 14px; line-height: 1.45;
}
.notice svg { flex: none; margin-top: 2px; }

/* ---------- builder v2: title, fixed KPI row, sidebar filters ---------- */
.eyebrow-line { font-size: 12px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); margin: 2px 0 8px; }
.st-key-title-box [data-testid="stTextInputRootElement"] { min-height: 66px; border-radius: 20px !important; background: rgba(255,255,255,.6) !important; }
.st-key-title-box [data-testid="stTextInput"] input { font-size: 30px !important; font-weight: 760 !important; letter-spacing: -0.03em; height: 64px; padding: 0 1.3rem !important; }
.title-hint { font-size: 13px; color: var(--ink3); margin: 8px 6px 18px; }

[class*="st-key-glass-kpi-"] { position: relative; height: 124px; padding: 16px 16px !important; overflow: hidden; margin-bottom: 6px; animation: rise 0.5s var(--ease) both; }
[class*="st-key-glass-kpi-"] [data-testid="stPopover"] { position: absolute; top: 8px; right: 8px; width: auto; z-index: 3; }
[class*="st-key-glass-kpi-"] [data-testid="stPopover"] button {
  height: 28px; min-height: 28px; width: 34px; padding: 0 !important; border-radius: 10px !important; opacity: 0.4; font-size: 18px; line-height: 1;
}
[class*="st-key-glass-kpi-"]:hover [data-testid="stPopover"] button { opacity: 1; }
[class*="st-key-glass-kpi-"] [data-testid="stPopover"] button svg,
[class*="st-key-glass-kpi-"] [data-testid="stPopover"] button [data-testid="stIconMaterial"] { display: none; }
[class*="st-key-glass-kpi-"] [data-testid="stPopover"] button p { font-size: 20px; margin: 0; line-height: 1; letter-spacing: 1px; }
.kfix { display: flex; align-items: center; gap: 12px; height: 90px; }
.kfix .kic {
  width: 44px; height: 44px; border-radius: 14px; flex: none; display: grid; place-items: center; color: #fff;
  background: linear-gradient(145deg, var(--c1), var(--c2));
  box-shadow: 0 9px 20px rgba(var(--rgb), 0.30), inset 0 1.5px 0 rgba(255,255,255,.5);
}
.kfix .kbody { flex: 1; min-width: 0; container-type: inline-size; }
.kfix .kt {
  font-size: 12.5px; font-weight: 650; color: var(--ink3); line-height: 1.25; padding-right: 22px;
  height: 31px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word;
}
[class*="st-key-glass-kpi-"] { container-type: inline-size; }
@container (max-width: 190px) { .kfix .kic { display: none; } }
.kfix .kv { font-weight: 750; letter-spacing: -0.035em; line-height: 1.15; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--ink); }
.kfix .ks { font-size: 12px; color: var(--ink3); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kfix.blue   { --c1: #4fa3ff; --c2: #0a6cf5; --rgb: 10,132,255; }
.kfix.purple { --c1: #cf7bff; --c2: #7d5cf0; --rgb: 125,92,240; }
.kfix.teal   { --c1: #5fd8f7; --c2: #1190bd; --rgb: 26,168,214; }
.kfix.green  { --c1: #5ee07f; --c2: #17a045; --rgb: 31,178,79; }
.kfix.orange { --c1: #ffb84d; --c2: #e07b00; --rgb: 240,138,0; }
.card-title, .card-sub { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile-msg { min-height: 250px; display: flex; align-items: center; justify-content: center; }

.flt-title { font-size: 11.5px; font-weight: 700; color: var(--ink3); letter-spacing: 0.07em; text-transform: uppercase; margin: 12px 6px 4px; }
[data-testid="stSidebar"] [data-testid="stExpander"] { border-radius: 16px !important; box-shadow: 0 3px 12px rgba(60,72,120,.07); margin-bottom: 8px; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary { padding: 10px 14px !important; font-size: 14px; }
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] { padding: 0 12px 12px !important; }
[data-testid="stSidebar"] .stButton > button { height: 36px; min-height: 36px; padding: 0 10px !important; font-size: 13px; border-radius: 12px !important; }
[data-testid="stSidebar"] [data-testid="stCheckbox"] label p { font-size: 13.5px; font-weight: 500; }
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] [data-testid="stCaptionContainer"] { margin: -2px 0 -6px; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { margin-bottom: 4px; }
[data-testid="stSidebar"] [data-testid="stSlider"] { padding: 0 6px; }
.filter-count { font-size: 12.5px; color: var(--ink3); margin: 10px 6px 10px; }

@media (max-width: 1100px) {
  .kpi-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .insight-grid, .how { grid-template-columns: 1fr; }
}
"""


def theme_css(page):
    """The stylesheet. The page name makes the entrance animation replay."""

    name = re.sub(r"[^A-Za-z0-9]", "_", str(page))

    css = (
        CSS.replace("__FONT__", FONT)
        .replace("__PAGE__", name)
        .replace("__NAV_ICONS__", _nav_icon_css())
    )

    return f"<style>{css}</style>"


# ------------------------------------------------------------
# HTML building blocks
# ------------------------------------------------------------

def flat(html):
    """One line, so Streamlit's markdown never reads indentation as code."""

    return " ".join(line.strip() for line in html.strip().splitlines())


def esc(text):
    """Make any text safe to put in HTML, in the page text AND inside attributes like title="..."."""
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&#x27;")
    )


def brand_html():
    return flat(f"""
    <div class="brand">
      <div class="brand-logo">{icon_svg("sparkle", 22, 2)}</div>
      <div><div class="brand-name">Datalyst</div><div class="brand-tag">AI Data Analyst</div></div>
    </div>
    """)


def dataset_card_html(name, rows, columns):
    return flat(f"""
    <div class="glass dataset-card">
      <div class="name" title="{esc(name)}"><span class="dot"></span>{esc(name)}</div>
      <div class="meta">{rows:,} rows · {columns} columns</div>
    </div>
    """)


def hero_html(title, subtitle="", eyebrow="", chips=()):
    chips_html = "".join(
        f'<span class="chip {c.get("tone", "")}">{esc(c["text"])}</span>'
        for c in chips
    )

    return flat(f"""
    <div class="hero">
      {f'<div class="eyebrow">{esc(eyebrow)}</div>' if eyebrow else ''}
      <div class="title">{esc(title)}</div>
      {f'<div class="subtitle">{esc(subtitle)}</div>' if subtitle else ''}
      {f'<div class="chips">{chips_html}</div>' if chips_html else ''}
    </div>
    """)


def kpi_row_html(kpis):
    cards = []

    for index, kpi in enumerate(kpis):
        cards.append(f"""
        <div class="glass kpi {kpi['accent']}" style="--i:{index}" title="{esc(kpi['full'])}">
          <div class="ico">{icon_svg(kpi['icon'], 21)}</div>
          <div class="label">{esc(kpi['label'])}</div>
          <div class="value">{esc(kpi['value'])}</div>
          <div class="sub">{esc(kpi['sub'])}</div>
        </div>
        """)

    return flat(f'<div class="kpi-row">{"".join(cards)}</div>')


def highlights_html(lines):
    rows = "".join(
        f'<div class="hl"><span class="bullet"></span><span>{esc(line)}</span></div>'
        for line in lines
    )

    return flat(rows)


def card_title(title, subtitle=""):
    return flat(
        f'<div class="card-title">{esc(title)}</div>'
        + (f'<div class="card-sub">{esc(subtitle)}</div>' if subtitle else "")
    )


def kpi_tile_html(title, value, full, sub, accent="blue"):
    return flat(f"""
    <div class="tile-kpi {accent}">
      <div class="tt">{esc(title)}</div>
      <div class="tv" title="{esc(full)}">{esc(value)}</div>
      <div class="ts">{esc(sub)}</div>
    </div>
    """)


def tile_message_html(text, error=False):
    return flat(f'<div class="tile-msg {"error" if error else ""}">{esc(text)}</div>')


def empty_state_html(title, text):
    return flat(f"""
    <div class="glass empty-state"><div class="t">{esc(title)}</div><div class="d">{esc(text)}</div></div>
    """)


def kpi_fixed_html(title, value, full, sub, accent="blue", icon="chart"):
    """A KPI card of fixed size: the number shrinks to fit, never wraps."""

    size = 30 if len(value) <= 6 else 26 if len(value) <= 7 else 23 if len(value) <= 8 else 20

    return flat(f"""
    <div class="kfix {accent}">
      <div class="kic">{icon_svg(icon, 21)}</div>
      <div class="kbody">
        <div class="kt" title="{esc(title)}">{esc(title)}</div>
        <div class="kv" title="{esc(full)}" style="font-size:min({size}px,15cqw)">{esc(value)}</div>
        <div class="ks" title="{esc(sub)}">{esc(sub)}</div>
      </div>
    </div>
    """)


def how_it_works_html():
    steps = [
        ("1", "The AI understands", "Your question becomes a small plan. The AI never calculates."),
        ("2", "Code checks the plan", "Columns, values and filters are verified against your real data."),
        ("3", "Python calculates", "The exact number is computed, then explained in plain words."),
    ]

    cards = "".join(
        f'<div class="glass" style="--i:{i}"><div class="n">STEP {n}</div>'
        f'<div class="t">{t}</div><div class="d">{d}</div></div>'
        for i, (n, t, d) in enumerate(steps)
    )

    return flat(f'<div class="how">{cards}</div>')


def soon_html(title, text, icon):
    return flat(f"""
    <div class="glass soon">
      <div class="ico">{icon_svg(icon, 30)}</div>
      <div class="t">{esc(title)}</div>
      <div class="d">{esc(text)}</div>
    </div>
    """)


def insights_grid_html(items):
    cards = []

    for index, item in enumerate(items):
        cards.append(f"""
        <div class="glass ins" style="--i:{index}">
          <span class="tag {item['tag']}">{item['tag']}</span>
          <div class="t">{esc(item['title'])}</div>
          <div class="d">{esc(item['text'])}</div>
        </div>
        """)

    return flat(f'<div class="insight-grid">{"".join(cards)}</div>')


# ---------- the answer on the Ask AI page ----------

EYEBROWS = {
    "total": "Total", "average": "Average", "maximum": "Maximum",
    "minimum": "Minimum", "count": "Count", "unique": "Distinct values",
    "duplicate": "Duplicate rows", "missing": "Missing values",
    "share": "Share", "top": "Top", "bottom": "Lowest", "trend": "Trend",
    "breakdown": "Breakdown", "month_pick": "Month",
}


def _format_scalar(value, plan):
    number = float(value)

    if plan["intent"] == "share" or plan.get("unit") == "%":
        return f"{number:.1f}%"

    if plan.get("unit") == "x":
        return f"{number:,.2f}x"

    if is_whole(number):
        return f"{int(number):,}"

    return f"{number:,.2f}"


def answer_parts(answer):
    """(eyebrow, big text or None, sentence) for the answer card."""

    plan = answer["plan"]
    result = answer["result"]
    intent = plan["intent"]

    eyebrow = EYEBROWS.get(intent, "Answer")

    if intent == "advanced":
        eyebrow = str(plan["advanced"]["kind"]).capitalize()

    if isinstance(result, (int, float)) and not isinstance(result, bool):
        return eyebrow, _format_scalar(result, plan), answer["response"]

    if hasattr(result, "item"):
        return eyebrow, _format_scalar(result.item(), plan), answer["response"]

    if isinstance(result, tuple) and len(result) == 2:
        name = str(result[0])
        group = str(plan.get("group_column") or "").replace("_", " ")
        return f"{eyebrow} {group}".strip(), name, answer["response"]

    return eyebrow, None, answer["response"]


def answer_card_html(question, answer):
    eyebrow, big, text = answer_parts(answer)

    big_html = ""

    if big is not None:
        size = " small" if len(big) > 13 else ""
        big_html = f'<div class="big{size}">{esc(big)}</div>'

    return flat(f"""
    <div class="glass answer">
      <div class="question">{icon_svg("chat", 16)} {esc(question)}</div>
      <div class="eyebrow">{esc(eyebrow)}</div>
      {big_html}
      <div class="text">{esc(text)}</div>
    </div>
    """)


def ai_status_html(state, missing=()):
    """A small light in the sidebar: is the AI that reads questions running?"""

    if state == "ready":
        tone, title, hint = "green", "AI ready", ""
    elif state == "missing":
        tone, title = "amber", "AI model missing"
        hint = "Run in Terminal: " + " ; ".join(f"ollama pull {m}" for m in missing)
    else:
        tone, title = "red", "AI is off"
        hint = "Open the Ollama app. Statistics, growth and ratio questions still work."

    hint_html = f'<span class="hint">{esc(hint)}</span>' if hint else ""

    return flat(f'''
    <div class="ai-status {tone}"><span class="dot"></span><div>{esc(title)}{hint_html}</div></div>
    ''')


def clean_stats_html(original, now):
    """Four glass tiles: your original file compared with now."""

    tiles = [
        ("Rows", "rows", "database", "blue", False),
        ("Columns", "columns", "layers", "purple", False),
        ("Blank cells", "blank_cells", "alert", "orange", True),
        ("Duplicate rows", "duplicate_rows", "shield", "green", True),
    ]
    cards = []

    for index, (label, key, icon, accent, lower_is_better) in enumerate(tiles):
        before, after = int(original[key]), int(now[key])
        change = after - before

        if change == 0:
            tone, text = "same", "no change"
        else:
            tone = ("good" if change < 0 else "worse") if lower_is_better else "same"
            text = f"{change:+,}".replace("-", "\u2212")

        cards.append(f"""
        <div class="glass kpi {accent}" style="--i:{index}">
          <div class="ico">{icon_svg(icon, 21)}</div>
          <div class="label">{esc(label)}</div>
          <div class="value">{after:,}</div>
          <div class="sub">was {before:,}</div>
          <div class="delta {tone}">{esc(text)}</div>
        </div>
        """)

    return flat(f'<div class="kpi-row">{"".join(cards)}</div>')


def changes_html(items):
    """What was changed: one soft row per change, with a green tick."""

    if not items:
        return flat('<div class="changes"><div class="change none">Nothing needed changing.</div></div>')

    rows = "".join(
        f'<div class="change"><span class="tick">{icon_svg("check", 14, 3)}</span><span>{esc(item)}</span></div>'
        for item in items
    )

    return flat(f'<div class="changes">{rows}</div>')


def issue_detail_html(severity, detail, fixable=True):
    """The severity tag and the explanation under an issue's title."""

    tag = severity if fixable else "advice"
    label = {"high": "High", "medium": "Medium", "info": "Info", "advice": "Advice"}.get(tag, "Info")

    return flat(f'''<div class="issue-detail"><span class="sev {tag}">{label}</span>{esc(detail)}</div>''')


def issue_title_html(title):
    return flat(f'<div class="issue-title">{esc(title)}</div>')


def problem_card_html(question, title, message, steps=()):
    """A calm card for a problem that is not the person's fault (a file, the AI)."""

    asked = (
        f'<div class="question">{icon_svg("chat", 16)} {esc(question)}</div>' if question else ""
    )
    steps_html = (
        "<ol>" + "".join(f"<li>{esc(s)}</li>" for s in steps) + "</ol>" if steps else ""
    )

    return flat(f'''
    <div class="glass answer warn problem">
      {asked}
      <div class="eyebrow">{icon_svg("alert", 14)} {esc(title)}</div>
      <div class="text" style="margin-top:8px">{esc(message)}</div>
      {steps_html}
    </div>
    ''')


def refusal_card_html(question, message):
    return flat(f"""
    <div class="glass answer warn">
      <div class="question">{icon_svg("chat", 16)} {esc(question)}</div>
      <div class="eyebrow">{icon_svg("alert", 14)} I will not guess</div>
      <div class="text" style="margin-top:8px">{esc(message)}</div>
    </div>
    """)


def insight_card_html(text, verified_by_ai):
    foot = (
        "Written by AI. Every number was checked against the calculation."
        if verified_by_ai else
        "Every number comes straight from the calculation."
    )

    return flat(f"""
    <div class="glass insight">
      <div class="ico">{icon_svg("sparkle", 19)}</div>
      <div>
        <div class="head">Insight</div>
        <div class="body">{esc(text)}</div>
        <div class="foot">{icon_svg("check", 14, 2.5)} {foot}</div>
      </div>
    </div>
    """)


def steps_html(repairs):
    note = f"{len(repairs)} small correction(s) applied" if repairs else "No corrections needed"

    return flat(f"""
    <div class="steps">
      <div class="step"><div class="n">1 · UNDERSTOOD</div><div class="t">The AI read your question</div><div class="d">It made a plan. It did not calculate.</div></div>
      <div class="step"><div class="n">2 · CHECKED</div><div class="t">Code verified the plan</div><div class="d">{esc(note)}</div></div>
      <div class="step"><div class="n">3 · CALCULATED</div><div class="t">Python did the maths</div><div class="d">Exact numbers from your data.</div></div>
    </div>
    """)


def values_chips_html(values, total=None, limit=40):
    """The different values of a column as chips: [(name, rows)]."""

    shown = values[:limit]
    items = "".join(
        f'<span class="chip">{esc(name)} <b>{rows:,}</b></span>' for name, rows in shown
    )

    more = ""

    if (total or len(values)) > len(shown):
        more = f'<span class="chip">and {(total or len(values)) - len(shown):,} more</span>'

    return flat(
        f'<div class="valchips"><span class="lead">Values (rows):</span> {items}{more}</div>'
    )


def notice_html(text):
    return flat(f'<div class="notice">{icon_svg("alert", 16)}<span>{esc(text)}</span></div>')


def understood_html(chips):
    items = "".join(
        f'<span class="chip {c.get("tone", "")}">{esc(c["text"])}</span>' for c in chips
    )

    return flat(f'<div class="understood"><span class="lead">I understood:</span> {items}</div>')


def code_block_html(text):
    return flat(f'<div class="codeblock">{esc(text)}</div>')


# ------------------------------------------------------------
# Charts
# ------------------------------------------------------------

def _style(chart, height):
    return (
        chart.properties(
            height=height, background="transparent",
            padding={"left": 4, "right": 18, "top": 8, "bottom": 4},
        )
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor="#6e6e73", titleColor="#6e6e73", labelFont=FONT,
            titleFont=FONT, labelFontSize=12, gridColor="rgba(60,72,120,0.10)",
            domainColor="transparent", tickColor="transparent",
        )
        .configure_legend(
            labelColor="#515154", labelFont=FONT, labelFontSize=12.5,
            titleColor="#86868b", titleFont=FONT, symbolType="circle",
            padding=6,
        )
    )


def _frame(values, name="label", value="value"):
    return pd.DataFrame({name: list(values.keys()), value: list(values.values())})


def bar_chart(values, height=300, percent=False):
    """Horizontal rounded bars. Biggest on top."""

    data = _frame(values)
    data["rank"] = range(len(data))
    fmt = ".1f" if percent else ",.2f"

    numbers = [float(v) for v in values.values()] or [1.0]
    high = max(max(numbers), 0.0)
    low = min(min(numbers), 0.0)
    span = max(high - low, 1e-9)
    domain = [low - span * 0.18 if low < 0 else 0, high + span * 0.18 if high > 0 else 0]

    bars = alt.Chart(data).mark_bar(
        cornerRadiusEnd=9, height={"band": 0.62}
    ).encode(
        y=alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=240)),
        x=alt.X(
            "value:Q", title=None,
            scale=alt.Scale(domain=domain),
            axis=alt.Axis(grid=True, format="~s", tickCount=5),
        ),
        color=alt.condition(
            alt.datum.value < 0,
            alt.value("#ff9f0a"),
            alt.Color("value:Q", legend=None, scale=alt.Scale(range=["#bcd8ff", "#0a84ff"])),
        ),
        tooltip=[alt.Tooltip("label:N", title=""), alt.Tooltip("value:Q", format=fmt, title="")],
    )

    labels = alt.Chart(data).mark_text(
        align=alt.expr("datum.value < 0 ? 'right' : 'left'"),
        dx=alt.expr("datum.value < 0 ? -7 : 7"),
        color="#3a3a3c", fontSize=12.5, font=FONT, fontWeight=600,
    ).encode(
        y=alt.Y("label:N", sort=None),
        x="value:Q",
    )

    if percent:
        labels = labels.transform_calculate(
            t="format(datum.value, '.1f') + '%'"
        ).encode(text="t:N")
    else:
        labels = labels.encode(text=alt.Text("value:Q", format=".3~s"))

    return _style(alt.layer(bars, labels), height)


def column_chart(values, height=300, percent=False):
    """Vertical rounded columns (for a few groups)."""

    data = _frame(values)

    chart = alt.Chart(data).mark_bar(
        cornerRadiusTopLeft=9, cornerRadiusTopRight=9, size=34
    ).encode(
        x=alt.X("label:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, labelLimit=110)),
        y=alt.Y("value:Q", title=None, axis=alt.Axis(format="~s")),
        color=alt.condition(alt.datum.value < 0, alt.value("#ff9f0a"), alt.value("#0a84ff")),
        tooltip=[alt.Tooltip("label:N", title=""), alt.Tooltip("value:Q", format=".1f" if percent else ",.2f", title="")],
    )

    return _style(chart, height)


def line_chart(values, height=300, export=False):
    """A smooth line with a soft gradient underneath (export: a plain soft fill)."""

    data = _frame(values, "month", "value")

    gradient = alt.Gradient(
        gradient="linear",
        stops=[
            alt.GradientStop(color="rgba(10,132,255,0.40)", offset=0),
            alt.GradientStop(color="rgba(10,132,255,0.02)", offset=1),
        ],
        x1=1, x2=1, y1=1, y2=0,
    )

    base = alt.Chart(data).encode(
        x=alt.X("month:N", title=None, axis=alt.Axis(labelAngle=0, labelOverlap="parity", labelFontSize=11)),
        y=alt.Y("value:Q", title=None, axis=alt.Axis(format="~s")),
    )

    if export:
        area = base.mark_area(interpolate="monotone", color="#0a84ff", opacity=0.16)
    else:
        area = base.mark_area(interpolate="monotone", color=gradient)
    line = base.mark_line(interpolate="monotone", color="#0a84ff", strokeWidth=3)
    points = base.mark_point(
        filled=True, size=70, color="#0a84ff", opacity=0.0,
    ).encode(
        tooltip=[alt.Tooltip("month:N", title="Month"), alt.Tooltip("value:Q", format=",.2f", title="Value")],
    )

    # the last point: from the SAME data table (one table per chart)
    last_month = str(data["month"].iloc[-1])

    last = base.transform_filter(
        alt.datum.month == last_month
    ).mark_point(
        filled=True, size=130, color="#0a84ff", stroke="white", strokeWidth=3,
        opacity=1,
    )

    return _style(alt.layer(area, line, points, last), height)


def donut_chart(values, height=300):
    data = _frame(values)

    arc = alt.Chart(data).mark_arc(
        innerRadius=72, outerRadius=118, cornerRadius=8, padAngle=0.025
    ).encode(
        theta=alt.Theta("value:Q"),
        color=alt.Color(
            "label:N", sort=None, title=None,
            scale=alt.Scale(range=PALETTE),
            legend=alt.Legend(orient="right", offset=18),
        ),
        order=alt.Order("value:Q", sort="descending"),
        tooltip=[alt.Tooltip("label:N", title=""), alt.Tooltip("value:Q", format=",.0f", title="")],
    )

    center = alt.Chart(data).transform_aggregate(
        total="sum(value)"
    ).mark_text(
        fontSize=26, fontWeight=700, color="#1d1d1f", font=FONT
    ).encode(text=alt.Text("total:Q", format=",.0f"))

    return _style(alt.layer(arc, center), height)
