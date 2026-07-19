# Current theme

## `server/app/static/app.css`

```css
:root {
  --bg: #0f1115;
  --surface: #181b21;
  --surface-2: #22262d;
  --text: #e8eaed;
  --muted: #9aa0a6;
  --accent: #58a6ff;
  --danger: #f85149;
  --success: #3fb950;
  --warn: #d29922;
  --border: #30363d;
}

* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }
.navbar { display: flex; justify-content: space-between; align-items: center; padding: .75rem 1.25rem; background: var(--surface); border-bottom: 1px solid var(--border); }
.nav-brand { font-weight: 600; }.nav-user { color: var(--muted); font-size: .9rem; }
.container { max-width: 1200px; margin: 0 auto; padding: 1.25rem; }
.course-card,.group-card,.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; }
.group-members { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:.75rem; }
.member-cell { background:var(--surface-2); border:1px solid var(--border); border-radius:8px; padding:.9rem; }
.badge { font-size:.75rem; padding:.2rem .5rem; border-radius:4px; background:var(--surface); border:1px solid var(--border); }
.badge.ai { color:var(--accent); }.badge.final { color:var(--success); }.badge.failed { background:var(--danger); color:#fff; }
```

## `server/app/static/present.css`

```css
:root { --bg:#050505; --surface:#121212; --text:#f0f0f0; --muted:#9aa0a6; --accent:#58a6ff; --success:#3fb950; --border:#30363d; }
* { box-sizing:border-box; }
html,body { margin:0; padding:0; width:100%; height:100%; overflow:hidden; }
.present-body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans SC",sans-serif; display:flex; flex-direction:column; justify-content:center; align-items:center; }
.stage { width:100%; max-width:1600px; padding:4vh 6vw; text-align:center; }
.group-name { font-size:4rem; font-weight:800; margin:0 0 4vh; letter-spacing:.05em; }
.members-row { display:flex; flex-wrap:wrap; justify-content:center; gap:2rem; margin-bottom:4vh; }
.member-pill { background:var(--surface); border:2px solid var(--border); border-radius:999px; padding:1.2rem 2.2rem; display:flex; align-items:center; gap:1rem; font-size:1.8rem; }
.carousel { display:flex; flex-wrap:nowrap; gap:1.5rem; justify-content:center; overflow-x:auto; padding-bottom:1rem; }.carousel img { max-height:28vh; border:2px solid var(--border); border-radius:12px; }
```

