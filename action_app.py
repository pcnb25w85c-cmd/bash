#!/usr/bin/env python3
"""
Action Nieuws App – iPhone PWA
===============================
Een lokale webserver die op iPhone als app werkt via Safari "Voeg toe aan beginscherm".

Installeren & starten:
    pip install flask
    python action_app.py

Op iPhone installeren:
    1. Zorg dat je iPhone op hetzelfde WiFi-netwerk zit als deze computer
    2. Open Safari op je iPhone
    3. Ga naar het adres dat in de terminal verschijnt (bijv. http://192.168.1.10:5001)
    4. Tik op het Deel-icoon (het vierkantje met pijl omhoog)
    5. Kies "Voeg toe aan beginscherm"  →  "Voeg toe"
    De app verschijnt nu als icoon op je iPhone-beginscherm!
"""

import json
import socket
import struct
import sys
import threading
import time
import zlib
from datetime import datetime

try:
    from flask import Flask, Response, jsonify, request
except ImportError:
    print("\n⚠  Flask niet gevonden. Installeer met:\n   pip install flask\n")
    sys.exit(1)

from action_news_aggregator import (
    GOOGLE_NEWS_QUERIES,
    RSS_FEEDS,
    categorize,
    deduplicate,
    fetch_google_news,
    fetch_rss_feed,
)

app = Flask(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# In-memory cache
# ──────────────────────────────────────────────────────────────────────────────
_cache: dict = {
    "articles": [],
    "last_updated": None,
    "fetching": False,
}
_lock = threading.Lock()


# ──────────────────────────────────────────────────────────────────────────────
# PNG icon generator (pure Python stdlib – geen Pillow nodig)
# ──────────────────────────────────────────────────────────────────────────────
def _make_png(size: int, r: int, g: int, b: int) -> bytes:
    def chunk(t: bytes, d: bytes) -> bytes:
        crc = zlib.crc32(t + d) & 0xFFFFFFFF
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    # Elke rij: filter-byte 0 + RGB-pixels
    row = b"\x00" + bytes([r, g, b]) * size
    raw = row * size
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


# Genereer iconen eenmalig in geheugen (Action-rood #e30613)
_ICON_192 = _make_png(192, 227, 6, 19)
_ICON_512 = _make_png(512, 227, 6, 19)

# ──────────────────────────────────────────────────────────────────────────────
# PWA manifest
# ──────────────────────────────────────────────────────────────────────────────
_MANIFEST = json.dumps({
    "name": "Action Nieuws",
    "short_name": "Action",
    "description": "Wereldwijd nieuws over Action – supply chain, expansie en meer",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#e30613",
    "theme_color": "#e30613",
    "orientation": "portrait-primary",
    "lang": "nl",
    "categories": ["news"],
    "icons": [
        {"src": "/icon.png?s=192", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/icon.png?s=512", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
})

# ──────────────────────────────────────────────────────────────────────────────
# Service Worker (cache-first shell, network-first API)
# ──────────────────────────────────────────────────────────────────────────────
_SW = r"""
const CACHE = 'action-news-v2';
const SHELL = ['/', '/manifest.json', '/icon.png'];

self.addEventListener('install', e =>
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()))
);

self.addEventListener('activate', e =>
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  )
);

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(e.request).catch(() =>
        new Response(JSON.stringify({articles:[], fetching:false, error:'offline'}),
          {headers:{'Content-Type':'application/json'}})
      )
    );
  } else {
    e.respondWith(caches.match(e.request).then(c => c || fetch(e.request)));
  }
});
"""

# ──────────────────────────────────────────────────────────────────────────────
# Nieuws ophalen
# ──────────────────────────────────────────────────────────────────────────────
def _fetch_all():
    with _lock:
        if _cache["fetching"]:
            return
        _cache["fetching"] = True

    try:
        arts: list[dict] = []

        # Google News RSS (18 queries in 6 talen)
        for query, lang, country in GOOGLE_NEWS_QUERIES:
            found = fetch_google_news(query, lang, country)
            arts.extend(found)
            time.sleep(0.35)

        # Vakblad RSS-feeds
        for name, url in RSS_FEEDS:
            found = fetch_rss_feed(name, url)
            arts.extend(found)
            time.sleep(0.15)

        unique = deduplicate(arts)
        for a in unique:
            a["category"] = categorize(a)

        with _lock:
            _cache["articles"] = unique
            _cache["last_updated"] = datetime.now().isoformat()
    finally:
        with _lock:
            _cache["fetching"] = False


def _background_loop():
    _fetch_all()
    while True:
        time.sleep(30 * 60)  # elke 30 minuten vernieuwen
        _fetch_all()


# ──────────────────────────────────────────────────────────────────────────────
# HTML – de volledige iPhone app UI
# ──────────────────────────────────────────────────────────────────────────────
_HTML = """<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">

  <!-- PWA / iPhone -->
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="Action Nieuws">
  <meta name="theme-color" content="#e30613">
  <link rel="manifest" href="/manifest.json">
  <link rel="apple-touch-icon" href="/icon.png">

  <title>Action Nieuws</title>
  <style>
    :root {
      --red:    #e30613;
      --dkred:  #b8000f;
      --bg:     #f2f2f7;
      --card:   #ffffff;
      --txt:    #000000;
      --sec:    #636366;
      --sep:    rgba(60,60,67,.12);
      --top:    env(safe-area-inset-top,    20px);
      --bot:    env(safe-area-inset-bottom,  0px);
      --left:   env(safe-area-inset-left,    0px);
      --right:  env(safe-area-inset-right,   0px);
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    html, body {
      height: 100%; overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', Helvetica, sans-serif;
      background: var(--bg); color: var(--txt);
      -webkit-tap-highlight-color: transparent;
      -webkit-text-size-adjust: 100%;
    }

    /* ── Layout shell ────────────────────────────────── */
    #app { display: flex; flex-direction: column; height: 100%; }

    /* ── Header ──────────────────────────────────────── */
    .hdr {
      background: var(--red);
      color: #fff;
      padding: calc(var(--top) + 10px) calc(16px + var(--right)) 10px calc(16px + var(--left));
      display: flex; align-items: center; gap: 12px;
      flex-shrink: 0;
      box-shadow: 0 1px 0 rgba(0,0,0,.18);
      position: relative; z-index: 10;
    }
    .hdr-logo {
      width: 38px; height: 38px;
      background: #fff; border-radius: 9px;
      display: flex; align-items: center; justify-content: center;
      font-size: 22px; font-weight: 900; color: var(--red);
      flex-shrink: 0; letter-spacing: -1px;
      box-shadow: 0 1px 4px rgba(0,0,0,.25);
    }
    .hdr-info { flex: 1; min-width: 0; }
    .hdr-info h1 { font-size: 17px; font-weight: 700; letter-spacing: -.3px; }
    .hdr-sub {
      font-size: 11px; opacity: .85; margin-top: 1px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .hdr-btn {
      width: 36px; height: 36px; border: none; cursor: pointer;
      background: rgba(255,255,255,.18); border-radius: 50%;
      color: #fff; font-size: 20px; line-height: 1;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; -webkit-appearance: none; transition: background .15s;
    }
    .hdr-btn:active { background: rgba(255,255,255,.35); }
    .hdr-btn.spin { animation: spin .9s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Tabs ────────────────────────────────────────── */
    .tabs-wrap {
      background: var(--card);
      border-bottom: 1px solid var(--sep);
      flex-shrink: 0;
    }
    .tabs {
      display: flex; overflow-x: auto; -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      padding: 0 calc(8px + var(--left)) 0 calc(8px + var(--right));
    }
    .tabs::-webkit-scrollbar { display: none; }
    .tab {
      flex-shrink: 0; border: none; background: none; cursor: pointer;
      padding: 11px 13px; font-size: 13.5px; font-weight: 500;
      color: var(--sec); position: relative; white-space: nowrap;
      -webkit-appearance: none; transition: color .15s;
    }
    .tab.on { color: var(--red); font-weight: 600; }
    .tab.on::after {
      content: ''; position: absolute; bottom: 0; left: 13px; right: 13px;
      height: 2.5px; background: var(--red); border-radius: 2px 2px 0 0;
    }

    /* ── Feed ────────────────────────────────────────── */
    .feed {
      flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch;
      padding: 10px calc(14px + var(--right)) calc(var(--bot) + 20px) calc(14px + var(--left));
    }

    /* ── PTR indicator ───────────────────────────────── */
    .ptr {
      text-align: center; font-size: 12px; color: var(--sec);
      height: 0; overflow: hidden; transition: height .2s ease;
      display: flex; align-items: center; justify-content: center; gap: 6px;
    }
    .ptr.show { height: 44px; }

    /* ── Count label ─────────────────────────────────── */
    .count {
      text-align: center; font-size: 12px; color: var(--sec);
      padding: 4px 0 10px; letter-spacing: .2px;
    }

    /* ── Article card ────────────────────────────────── */
    .card {
      display: block; text-decoration: none; color: inherit;
      background: var(--card); border-radius: 13px;
      padding: 13px 15px; margin-bottom: 9px;
      box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 0 0 .5px rgba(0,0,0,.04);
      animation: up .28s ease both;
      -webkit-tap-highlight-color: transparent;
      transition: opacity .12s;
    }
    .card:active { opacity: .55; }
    @keyframes up {
      from { opacity: 0; transform: translateY(10px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .card-meta {
      display: flex; align-items: center; flex-wrap: wrap;
      gap: 4px; font-size: 11.5px; color: var(--sec); margin-bottom: 5px;
    }
    .card-src { font-weight: 700; color: var(--red); }
    .card-sep { opacity: .35; font-size: 10px; }
    .card-cat {
      background: #f0f0f5; border-radius: 5px;
      padding: 1px 6px; font-size: 10.5px; font-weight: 500; color: #3c3c43;
    }
    .card-title {
      font-size: 15.5px; font-weight: 600; line-height: 1.35;
      margin-bottom: 5px; color: #000; letter-spacing: -.15px;
    }
    .card-desc {
      font-size: 13px; line-height: 1.45; color: var(--sec);
      display: -webkit-box; -webkit-line-clamp: 2;
      -webkit-box-orient: vertical; overflow: hidden;
    }

    /* ── Skeleton ────────────────────────────────────── */
    .skel-card {
      background: var(--card); border-radius: 13px;
      padding: 13px 15px; margin-bottom: 9px;
    }
    .skel {
      background: linear-gradient(90deg, #e5e5ea 25%, #ebebf0 50%, #e5e5ea 75%);
      background-size: 300% 100%; border-radius: 5px;
      animation: shim 1.4s infinite;
    }
    @keyframes shim { from { background-position: 300% 0; } to { background-position: -300% 0; } }
    .skel-sm  { height: 11px; width: 55%; margin-bottom: 9px; }
    .skel-lg  { height: 16px; width: 92%; margin-bottom: 5px; }
    .skel-lg2 { height: 16px; width: 72%; margin-bottom: 9px; }
    .skel-xs  { height: 11px; width: 100%; margin-bottom: 4px; }
    .skel-xs2 { height: 11px; width: 78%; }

    /* ── Empty state ─────────────────────────────────── */
    .empty {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; padding: 64px 32px; text-align: center;
    }
    .empty-ico { font-size: 52px; margin-bottom: 18px; }
    .empty h3  { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
    .empty p   { font-size: 14px; color: var(--sec); line-height: 1.55; }
  </style>
</head>
<body>
<div id="app">

  <!-- ── Header ── -->
  <header class="hdr">
    <div class="hdr-logo">A</div>
    <div class="hdr-info">
      <h1>Action Nieuws</h1>
      <div class="hdr-sub" id="sub">Nieuws ophalen&hellip;</div>
    </div>
    <button class="hdr-btn" id="rbtn" onclick="doRefresh()" aria-label="Vernieuwen">&#8635;</button>
  </header>

  <!-- ── Categorie-tabs ── -->
  <div class="tabs-wrap">
    <div class="tabs" id="tabs">
      <button class="tab on" data-cat="">Alles</button>
      <button class="tab" data-cat="Supply Chain &amp; Distributie">🏭 Supply Chain</button>
      <button class="tab" data-cat="Expansie &amp; Openingen">🏪 Expansie</button>
      <button class="tab" data-cat="Financieel">💰 Financieel</button>
      <button class="tab" data-cat="Technologie &amp; Innovatie">💻 Technologie</button>
      <button class="tab" data-cat="Duurzaamheid">🌱 Duurzaamheid</button>
      <button class="tab" data-cat="Personeel &amp; Arbeid">👷 Personeel</button>
      <button class="tab" data-cat="Algemeen Nieuws">📰 Overig</button>
    </div>
  </div>

  <!-- ── Nieuwsfeed ── -->
  <div class="feed" id="feed">
    <div class="ptr" id="ptr">&#8595; Loslaten om te vernieuwen</div>
  </div>

</div>

<script>
// ── State ───────────────────────────────────────────────────────
let all = [], cat = '', busy = false;

// ── Helpers ─────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const esc = s => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };

function ago(raw) {
  if (!raw) return '';
  // ISO 8601 or RFC 2822
  let d = new Date(raw);
  if (isNaN(d)) {
    // Try "13 Mar 2026 21:00" style
    d = new Date(raw.replace(/(\d{2}) (\w{3}) (\d{4})/, '$2 $1 $3'));
  }
  if (isNaN(d)) return raw.slice(0,10);
  const s = (Date.now() - d) / 1000;
  if (s <    60) return 'zojuist';
  if (s <  3600) return Math.floor(s/60) + ' min geleden';
  if (s < 86400) return Math.floor(s/3600) + ' uur geleden';
  if (s < 86400*7) return Math.floor(s/86400) + ' dagen geleden';
  return d.toLocaleDateString('nl-NL', {day:'numeric', month:'short'});
}

const CAT_SHORT = {
  'Supply Chain & Distributie': 'Supply Chain',
  'Expansie & Openingen': 'Expansie',
  'Financieel': 'Financieel',
  'Technologie & Innovatie': 'Technologie',
  'Duurzaamheid': 'Duurzaamheid',
  'Personeel & Arbeid': 'Personeel',
  'Algemeen Nieuws': 'Overig',
};

// ── Render ──────────────────────────────────────────────────────
function skeletons() {
  const f = $('feed'), ptr = $('ptr');
  f.innerHTML = '';
  f.appendChild(ptr);
  for (let i = 0; i < 7; i++) f.insertAdjacentHTML('beforeend', `
    <div class="skel-card">
      <div class="skel skel-sm"></div>
      <div class="skel skel-lg"></div>
      <div class="skel skel-lg2"></div>
      <div class="skel skel-xs"></div>
      <div class="skel skel-xs2"></div>
    </div>`);
}

function render(articles) {
  const f = $('feed'), ptr = $('ptr');
  f.innerHTML = '';
  f.appendChild(ptr);

  if (!articles.length) {
    f.insertAdjacentHTML('beforeend', `
      <div class="empty">
        <div class="empty-ico">🔍</div>
        <h3>Geen artikelen</h3>
        <p>Geen nieuws gevonden in deze categorie.<br>Tik ↻ om te vernieuwen.</p>
      </div>`);
    return;
  }

  f.insertAdjacentHTML('beforeend',
    `<div class="count">${articles.length} artikel${articles.length !== 1 ? 'en' : ''}</div>`);

  f.insertAdjacentHTML('beforeend', articles.map((a, i) => {
    const src  = esc(a.source?.name || 'Onbekend');
    const cat  = esc(CAT_SHORT[a.category] || '');
    const t    = ago(a.publishedAt);
    const url  = a.url || '#';
    const ttl  = esc(a.title || 'Geen titel');
    const desc = esc(a.description || '');
    const delay = Math.min(i * 0.035, 0.45).toFixed(3);

    return `<a class="card" href="${url}" target="_blank" rel="noopener noreferrer"
               style="animation-delay:${delay}s">
      <div class="card-meta">
        <span class="card-src">${src}</span>
        ${t   ? `<span class="card-sep">·</span><span>${t}</span>` : ''}
        ${cat ? `<span class="card-sep">·</span><span class="card-cat">${cat}</span>` : ''}
      </div>
      <div class="card-title">${ttl}</div>
      ${desc ? `<div class="card-desc">${desc}</div>` : ''}
    </a>`;
  }).join(''));
}

function show() {
  render(cat ? all.filter(a => a.category === cat) : all);
}

// ── API ─────────────────────────────────────────────────────────
async function load(skel = false) {
  if (busy) return;
  busy = true;
  if (skel) skeletons();
  $('rbtn').classList.add('spin');
  $('sub').textContent = 'Ophalen\u2026';

  try {
    const r = await fetch('/api/news');
    const d = await r.json();
    all = d.articles || [];
    const upd = d.last_updated
      ? new Date(d.last_updated).toLocaleTimeString('nl-NL',{hour:'2-digit',minute:'2-digit'})
      : '';
    $('sub').textContent = all.length + ' artikelen' + (upd ? ' \u00b7 ' + upd : '');
    show();
  } catch {
    $('sub').textContent = '\u26a0 Verbindingsfout';
  } finally {
    busy = false;
    $('rbtn').classList.remove('spin');
  }
}

async function doRefresh() {
  if (busy) return;
  busy = true;
  $('rbtn').classList.add('spin');
  $('sub').textContent = 'Vernieuwen\u2026';

  try {
    await fetch('/api/refresh', { method: 'POST' });
    // Poll totdat ophalen klaar is
    for (let i = 0; i < 90; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const r = await fetch('/api/news');
      const d = await r.json();
      if (!d.fetching) {
        all = d.articles || [];
        const upd = d.last_updated
          ? new Date(d.last_updated).toLocaleTimeString('nl-NL',{hour:'2-digit',minute:'2-digit'})
          : '';
        $('sub').textContent = all.length + ' artikelen \u00b7 ' + upd;
        show();
        break;
      }
    }
  } catch {
    $('sub').textContent = '\u26a0 Fout bij vernieuwen';
  } finally {
    busy = false;
    $('rbtn').classList.remove('spin');
  }
}

// ── Tabs ─────────────────────────────────────────────────────────
$('tabs').addEventListener('click', e => {
  const tab = e.target.closest('.tab');
  if (!tab) return;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
  tab.classList.add('on');
  // Decode HTML entities from data-cat
  const tmp = document.createElement('textarea');
  tmp.innerHTML = tab.dataset.cat;
  cat = tmp.value;
  show();
  tab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
});

// ── Pull-to-refresh ───────────────────────────────────────────────
let _y0 = 0;
const feed = $('feed'), ptr = $('ptr');
feed.addEventListener('touchstart', e => { _y0 = e.touches[0].clientY; }, { passive: true });
feed.addEventListener('touchmove', e => {
  if (feed.scrollTop === 0 && e.touches[0].clientY - _y0 > 70) ptr.classList.add('show');
}, { passive: true });
feed.addEventListener('touchend', () => {
  if (ptr.classList.contains('show')) { ptr.classList.remove('show'); doRefresh(); }
});

// ── Auto-refresh elke 5 minuten ───────────────────────────────────
setInterval(load, 5 * 60 * 1000);

// ── Service Worker ────────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
}

// ── Start ─────────────────────────────────────────────────────────
load(true);
</script>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Flask routes
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return Response(_HTML, content_type="text/html; charset=utf-8")


@app.route("/manifest.json")
def manifest():
    return Response(_MANIFEST, content_type="application/manifest+json")


@app.route("/sw.js")
def sw():
    resp = Response(_SW, content_type="application/javascript; charset=utf-8")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/icon.png")
def icon():
    s = request.args.get("s", "192")
    data = _ICON_512 if s == "512" else _ICON_192
    return Response(data, content_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.route("/api/news")
def api_news():
    with _lock:
        return jsonify({
            "articles":     _cache["articles"],
            "last_updated": _cache["last_updated"],
            "total":        len(_cache["articles"]),
            "fetching":     _cache["fetching"],
        })


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    if not _cache["fetching"]:
        threading.Thread(target=_fetch_all, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/status")
def api_status():
    with _lock:
        return jsonify({
            "fetching":     _cache["fetching"],
            "last_updated": _cache["last_updated"],
            "total":        len(_cache["articles"]),
        })


# ──────────────────────────────────────────────────────────────────────────────
# Startup
# ──────────────────────────────────────────────────────────────────────────────
def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    PORT = 5001

    # Achtergrond-thread: nieuws ophalen op start + elke 30 min
    threading.Thread(target=_background_loop, daemon=True).start()

    ip = _local_ip()
    print(f"""
\033[1m\033[91m╔══════════════════════════════════════════════════════════════╗
║   🛒  ACTION NIEUWS APP – iPhone PWA                         ║
╚══════════════════════════════════════════════════════════════╝\033[0m

\033[92m✅ Server gestart\033[0m

   Lokaal:   \033[96mhttp://localhost:{PORT}\033[0m
   iPhone:   \033[96mhttp://{ip}:{PORT}\033[0m

\033[1m📱 Op iPhone installeren:\033[0m
   1. Zorg dat iPhone en computer op hetzelfde WiFi zitten
   2. Open \033[1mSafari\033[0m op je iPhone
   3. Ga naar \033[96mhttp://{ip}:{PORT}\033[0m
   4. Tik op het \033[1mDeel-icoon\033[0m (vierkantje met pijl omhoog ↑)
   5. Kies \033[1m"Voeg toe aan beginscherm"\033[0m  →  \033[1m"Voeg toe"\033[0m

   De app verschijnt nu als icoon op je beginscherm! 🎉

\033[2m🔄 Nieuws wordt op de achtergrond opgehaald...
   Stop met Ctrl+C\033[0m
""")

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
