#!/usr/bin/env python3
"""
Action News Aggregator
======================
Maakt bij het openen automatisch verbinding met het internet en zoekt wereldwijd
naar nieuws over Action (Nederlandse retailer), inclusief supply chain en
distributiecentra.

Gebruik:
    python action_news_aggregator.py
    python action_news_aggregator.py --export rapport.html --open
    python action_news_aggregator.py --export data.json
    python action_news_aggregator.py --days 7 --max 50
    python action_news_aggregator.py --newsapi-key YOUR_KEY --days 14
    python action_news_aggregator.py --demo   # toon zoekstrategie zonder internet
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Google News RSS-queries  (taal × onderwerp)
# Geen API-key nodig – werkt worldwide
# ──────────────────────────────────────────────────────────────────────────────
GOOGLE_NEWS_QUERIES = [
    # Nederlands
    ("Action retail nieuw", "nl", "NL"),
    ("Action winkel opening distributie", "nl", "NL"),
    ("Action distributiecentrum supply chain", "nl", "NL"),
    ("Action leveranciers logistiek", "nl", "NL"),
    ("Action omzet resultaten groei", "nl", "NL"),
    ("Action medewerkers personeel cao", "nl", "NL"),
    ("Action duurzaamheid milieu", "nl", "NL"),
    # Engels – internationaal
    ("Action retailer Netherlands news", "en", "US"),
    ("Action stores supply chain distribution", "en", "US"),
    ("Action retail Europe expansion", "en", "GB"),
    ("Action warehouse fulfillment logistics", "en", "US"),
    ("Action Netherlands revenue profit", "en", "US"),
    # Duits
    ("Action Discounter Filialen Deutschland", "de", "DE"),
    ("Action Einzelhandel Logistik Lager", "de", "DE"),
    # Frans
    ("Action magasin France ouverture", "fr", "FR"),
    ("Action enseigne supply chain logistique", "fr", "FR"),
    # Pools
    ("Action sklep Polska otwarcie", "pl", "PL"),
    # Spaans
    ("Action tienda España apertura", "es", "ES"),
]

# ──────────────────────────────────────────────────────────────────────────────
# Gespecialiseerde vak-RSS-feeds (retail, logistiek, supply chain)
# ──────────────────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    # Nederlandse retail / logistiek media
    ("Retaildetail NL",     "https://www.retaildetail.nl/rss.xml"),
    ("Distrifood",          "https://www.distrifood.nl/rss"),
    ("Logistiek.nl",        "https://www.logistiek.nl/rss"),
    ("Supply Chain Mag NL", "https://www.supplychain.nl/feed/"),
    ("NU.nl Economie",      "https://www.nu.nl/rss/economie"),
    ("RTL Nieuws Eco",      "https://www.rtlnieuws.nl/rss/economie.xml"),
    ("FD.nl",               "https://fd.nl/rss"),
    # Internationaal retail
    ("Retail Gazette",      "https://www.retailgazette.co.uk/feed/"),
    ("Retail Dive",         "https://www.retaildive.com/feeds/news/"),
    ("Lebensmittelzeitung", "https://www.lebensmittelzeitung.net/rss.xml"),
    ("LSA Conso (FR)",      "https://www.lsa-conso.fr/rss"),
    # Supply chain internationaal
    ("Supply Chain 247",    "https://www.supplychaindigital.com/rss.xml"),
    ("Logistics Manager",   "https://www.logisticsmanager.com/feed/"),
    ("Transport+Logistik",  "https://www.trans.info/en/feed"),
]

# Woorden die in titel/beschrijving moeten staan → artikel is relevant voor Action
ACTION_KEYWORDS = [
    "action", "action retail", "action store", "action stores",
    "action nederland", "action distributie", "action warehouse",
    "action supply chain", "action filiaal", "action winkel",
    "action opening", "action dc ", "action logistiek",
    "action discounter", "action enseigne", "action tienda",
    "action sklep",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    "Accept-Language": "nl,en;q=0.9,de;q=0.8,fr;q=0.7",
}

# Terminal kleuren
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"


# ──────────────────────────────────────────────────────────────────────────────
# Netwerk
# ──────────────────────────────────────────────────────────────────────────────
def fetch_url(url: str, timeout: int = 12) -> str | None:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            enc = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(enc, errors="replace")
    except Exception:
        return None


def check_connectivity() -> bool:
    """Snelle verbindingstest via Google DNS."""
    import socket
    try:
        socket.setdefaulttimeout(5)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except OSError:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Google News RSS  (gratis, geen API-key)
# ──────────────────────────────────────────────────────────────────────────────
def fetch_google_news(query: str, lang: str = "nl", country: str = "NL") -> list[dict]:
    q = urllib.parse.quote(query)
    url = (
        f"https://news.google.com/rss/search"
        f"?q={q}&hl={lang}&gl={country}&ceid={country}:{lang}"
    )
    xml = fetch_url(url)
    return parse_rss_xml("Google News", xml) if xml else []


# ──────────────────────────────────────────────────────────────────────────────
# NewsAPI.org  (optioneel – gratis tier: 100 req/dag)
# ──────────────────────────────────────────────────────────────────────────────
NEWSAPI_QUERIES = [
    '"Action" retail Netherlands',
    '"Action" supply chain distribution center',
    '"Action" distributiecentrum logistiek',
    '"Action" stores expansion Europe',
    '"Action" revenue profit growth',
    '"Action" sustainability duurzaamheid',
    '"Action" warehouse fulfillment',
    '"Action" opening new store',
]


def fetch_newsapi(query: str, api_key: str, days: int = 30) -> list[dict]:
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    params = urllib.parse.urlencode({
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "pageSize": 20,
        "apiKey": api_key,
    })
    data = fetch_url(f"https://newsapi.org/v2/everything?{params}")
    if not data:
        return []
    try:
        arts = json.loads(data).get("articles", [])
    except json.JSONDecodeError:
        return []
    return [
        {
            "title":       a.get("title", ""),
            "description": a.get("description", "")[:300],
            "url":         a.get("url", ""),
            "publishedAt": a.get("publishedAt", ""),
            "source":      {"name": a.get("source", {}).get("name", "NewsAPI")},
        }
        for a in arts
        if a.get("title")
    ]


# ──────────────────────────────────────────────────────────────────────────────
# RSS parser  (geen externe library)
# ──────────────────────────────────────────────────────────────────────────────
def _tag(xml: str, tag: str) -> str:
    m = re.search(
        rf"<{tag}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>",
        xml, re.DOTALL | re.IGNORECASE,
    )
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


def _attr(xml: str, tag: str, attr: str) -> str:
    m = re.search(rf'<{tag}[^>]*{attr}="([^"]+)"', xml, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def parse_rss_xml(feed_name: str, xml: str) -> list[dict]:
    articles = []
    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    if not items:
        items = re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL)

    for item in items[:30]:
        title = _tag(item, "title")
        if not title:
            continue

        # Probeer link op meerdere manieren
        link = _tag(item, "link")
        if not link:
            link = _attr(item, "link", "href")
        if not link:
            m = re.search(r"<link[^>]*/?>([^<]+)", item)
            link = m.group(1).strip() if m else ""

        # Google News geeft soms <a href=...> in description
        if not link:
            m = re.search(r'href="(https?://[^"]+)"', item)
            link = m.group(1) if m else ""

        desc = _tag(item, "description") or _tag(item, "summary")
        desc = desc[:300]
        pub  = _tag(item, "pubDate") or _tag(item, "updated")

        combined = (title + " " + desc).lower()
        if any(kw in combined for kw in ACTION_KEYWORDS):
            articles.append({
                "title":       title,
                "description": desc,
                "url":         link,
                "publishedAt": pub,
                "source":      {"name": feed_name},
            })
    return articles


def fetch_rss_feed(feed_name: str, url: str) -> list[dict]:
    xml = fetch_url(url)
    return parse_rss_xml(feed_name, xml) if xml else []


# ──────────────────────────────────────────────────────────────────────────────
# Categorisatie
# ──────────────────────────────────────────────────────────────────────────────
CATEGORIES = {
    "Supply Chain & Distributie": [
        "supply chain", "distributie", "warehouse", "logistiek", "fulfillment",
        "leverancier", "dc ", "transport", "opslag", "magazijn",
        "inkoop", "procurement", "distribution center", "lager", "stockage",
    ],
    "Expansie & Openingen": [
        "opening", "filiaal", "winkel", "store", "expansie", "expansion",
        "nieuw", "new", "ouverture", "otwarcie", "apertura",
        "eröffnung", "vestiging", "country",
    ],
    "Financieel": [
        "omzet", "groei", "resultaat", "winst", "financieel", "revenue",
        "profit", "groei", "jaarverslag", "kwartaal", "investering",
        "overname", "acquisition", "waardering", "private equity",
    ],
    "Duurzaamheid": [
        "duurzaam", "co2", "milieu", "sustainability", "esg", "klimaat",
        "recycl", "groen", "green", "emissie", "carbon", "circulair",
    ],
    "Personeel & Arbeid": [
        "personeel", "medewerker", "cao", "fnv", "arbeids", "vacature",
        "staking", "loon", "employee", "worker", "hr ", "recruitment",
    ],
    "Technologie & Innovatie": [
        "technologie", "digitaal", "robot", "automation", "ai ", "app",
        "innovatie", "software", "scan", "rfid", "edi", "erp",
    ],
}


def categorize(article: dict) -> str:
    text = (article.get("title", "") + " " + article.get("description", "")).lower()
    for cat, keywords in CATEGORIES.items():
        if any(kw in text for kw in keywords):
            return cat
    return "Algemeen Nieuws"


def format_date(raw: str) -> str:
    if not raw:
        return "datum onbekend"
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S GMT",
    ):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%d %b %Y %H:%M")
        except ValueError:
            continue
    return raw[:16]


def deduplicate(articles: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in articles:
        key = a.get("title", "").lower()[:70]
        if key and key not in seen:
            seen.add(key)
            out.append(a)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Terminal output
# ──────────────────────────────────────────────────────────────────────────────
def print_banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║   🛒  ACTION NEWS AGGREGATOR                                 ║
║   Wereldwijd nieuws – Action (Nederlandse retailer)          ║
║   Supply Chain · Distributie · Expansie · Financieel         ║
╚══════════════════════════════════════════════════════════════╝{RESET}""")


CAT_ORDER = [
    "Supply Chain & Distributie",
    "Expansie & Openingen",
    "Financieel",
    "Technologie & Innovatie",
    "Duurzaamheid",
    "Personeel & Arbeid",
    "Algemeen Nieuws",
]
CAT_ICONS = {
    "Supply Chain & Distributie": "🏭",
    "Expansie & Openingen":       "🏪",
    "Financieel":                 "💰",
    "Technologie & Innovatie":    "💻",
    "Duurzaamheid":               "🌱",
    "Personeel & Arbeid":         "👷",
    "Algemeen Nieuws":            "📰",
}


def print_articles(articles: list[dict], header: str = "Resultaten"):
    cat_map: dict[str, list[dict]] = {}
    for a in articles:
        cat_map.setdefault(categorize(a), []).append(a)

    print(f"\n{BOLD}{YELLOW}{'═'*62}{RESET}")
    print(f"{BOLD}{YELLOW}  {header}  ({len(articles)} artikelen){RESET}")
    print(f"{BOLD}{YELLOW}{'═'*62}{RESET}")

    for cat in CAT_ORDER:
        arts = cat_map.get(cat, [])
        if not arts:
            continue
        icon = CAT_ICONS.get(cat, "📌")
        print(f"\n{BOLD}{GREEN}  {icon} {cat}  ({len(arts)}){RESET}")
        print(f"{DIM}  {'─'*58}{RESET}")
        for i, a in enumerate(arts, 1):
            title  = a.get("title", "Geen titel")
            source = a.get("source", {}).get("name", "Onbekend")
            date   = format_date(a.get("publishedAt", ""))
            url    = a.get("url", "")
            desc   = a.get("description", "")[:130]
            print(f"\n  {BOLD}{i}. {title}{RESET}")
            print(f"     {CYAN}📰 {source}  |  📅 {date}{RESET}")
            if desc:
                print(f"     {DIM}{desc}…{RESET}")
            if url:
                print(f"     {DIM}🔗 {url}{RESET}")


def print_demo():
    """Toon zoekstrategie zonder internetverbinding."""
    print_banner()
    print(f"\n{BOLD}Demo-modus – overzicht van zoekstrategie{RESET}\n")

    print(f"{BOLD}{CYAN}📡 Google News RSS-queries ({len(GOOGLE_NEWS_QUERIES)} zoekacties):{RESET}")
    for q, lang, country in GOOGLE_NEWS_QUERIES:
        print(f"   [{lang.upper()}/{country}] {q}")

    print(f"\n{BOLD}{CYAN}📡 Gespecialiseerde RSS-feeds ({len(RSS_FEEDS)} bronnen):{RESET}")
    for name, url in RSS_FEEDS:
        print(f"   {name:<28}  {url}")

    print(f"\n{BOLD}{CYAN}📡 NewsAPI.org queries (optioneel, --newsapi-key vereist):{RESET}")
    for q in NEWSAPI_QUERIES:
        print(f"   {q}")

    print(f"\n{BOLD}Categorieën:{RESET}")
    for cat, kws in CATEGORIES.items():
        print(f"  {CAT_ICONS.get(cat,'📌')} {cat}")

    print(f"\n{DIM}Gebruik: python action_news_aggregator.py{RESET}\n")


# ──────────────────────────────────────────────────────────────────────────────
# HTML export
# ──────────────────────────────────────────────────────────────────────────────
def export_html(articles: list[dict], path: str):
    now = datetime.now().strftime("%d %B %Y %H:%M")
    cat_map: dict[str, list[dict]] = {}
    for a in articles:
        cat_map.setdefault(categorize(a), []).append(a)

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    cards_html = ""
    for cat in CAT_ORDER:
        arts = cat_map.get(cat, [])
        if not arts:
            continue
        icon = CAT_ICONS.get(cat, "📌")
        cards_html += (
            f'<h2 class="cat-header">{icon} {esc(cat)}'
            f' <span class="badge">{len(arts)}</span></h2>\n<div class="grid">\n'
        )
        for a in arts:
            title = esc(a.get("title", "Geen titel"))
            source = esc(a.get("source", {}).get("name", "Onbekend"))
            date   = format_date(a.get("publishedAt", ""))
            url    = a.get("url", "#")
            desc   = esc(a.get("description", "")[:250])
            cards_html += f"""  <div class="card">
    <a href="{url}" target="_blank" rel="noopener" class="card-title">{title}</a>
    <p class="card-meta">📰 {source} &nbsp;|&nbsp; 📅 {date}</p>
    <p class="card-desc">{desc}</p>
  </div>\n"""
        cards_html += "</div>\n"

    summary_pills = "".join(
        f'<span class="pill">{CAT_ICONS.get(c,"📌")} {c}: {len(a)}</span>'
        for c, a in ((c, cat_map.get(c, [])) for c in CAT_ORDER) if a
    )

    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Action Nieuws Aggregator – {now}</title>
  <style>
    :root{{--red:#e30613;--bg:#f4f5f7;--card:#fff;--txt:#222;--muted:#666}}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--txt)}}
    header{{background:var(--red);color:#fff;padding:2rem;text-align:center}}
    header h1{{font-size:2rem;letter-spacing:1px}}
    header p{{margin-top:.5rem;opacity:.85}}
    .summary{{display:flex;gap:.75rem;flex-wrap:wrap;justify-content:center;padding:1.25rem 2rem}}
    .pill{{background:var(--red);color:#fff;border-radius:999px;padding:.3rem .9rem;font-size:.82rem;font-weight:600}}
    main{{max-width:1200px;margin:0 auto;padding:1rem 2rem 3rem}}
    .cat-header{{margin:2rem 0 1rem;font-size:1.2rem;border-left:4px solid var(--red);padding-left:.75rem;display:flex;align-items:center;gap:.5rem}}
    .badge{{background:var(--red);color:#fff;border-radius:999px;font-size:.72rem;padding:.15rem .55rem}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1rem}}
    .card{{background:var(--card);border-radius:8px;padding:1.25rem;box-shadow:0 1px 4px rgba(0,0,0,.1);transition:box-shadow .2s}}
    .card:hover{{box-shadow:0 3px 14px rgba(0,0,0,.18)}}
    .card-title{{font-weight:700;font-size:.94rem;color:#1a0aab;text-decoration:none;display:block;margin-bottom:.5rem}}
    .card-title:hover{{text-decoration:underline}}
    .card-meta{{font-size:.78rem;color:var(--muted);margin-bottom:.55rem}}
    .card-desc{{font-size:.84rem;color:#444;line-height:1.5}}
    footer{{text-align:center;padding:2rem;color:var(--muted);font-size:.8rem;border-top:1px solid #ddd}}
  </style>
</head>
<body>
<header>
  <h1>🛒 Action Nieuws Aggregator</h1>
  <p>Wereldwijd nieuws over Action (Nederlandse retailer)</p>
  <p>Supply Chain &bull; Distributiecentra &bull; Expansie &bull; Financieel</p>
  <p style="margin-top:.75rem;font-size:.85rem">
    Gegenereerd op {now} &nbsp;|&nbsp; {len(articles)} artikelen gevonden
  </p>
</header>
<div class="summary">{summary_pills}</div>
<main>{cards_html}</main>
<footer>Action News Aggregator &bull; {now}</footer>
</body>
</html>"""
    Path(path).write_text(html, encoding="utf-8")
    print(f"\n{GREEN}✅ HTML-rapport opgeslagen: {Path(path).resolve()}{RESET}")


def export_json(articles: list[dict], path: str):
    data = {
        "generated": datetime.now().isoformat(),
        "total": len(articles),
        "articles": articles,
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{GREEN}✅ JSON opgeslagen: {Path(path).resolve()}{RESET}")


# ──────────────────────────────────────────────────────────────────────────────
# Hoofdprogramma
# ──────────────────────────────────────────────────────────────────────────────
def run(args) -> list[dict]:
    print_banner()

    # ── Connectiviteitscheck ──
    print(f"\n{CYAN}🌐 Internetverbinding controleren…{RESET}", end=" ", flush=True)
    if not check_connectivity():
        print(f"{RED}GEEN VERBINDING{RESET}")
        print(f"{RED}⚠  Geen internetverbinding. Gebruik --demo voor een overzicht.{RESET}")
        sys.exit(1)
    print(f"{GREEN}OK{RESET}")

    all_articles: list[dict] = []

    # ── Stap 1: Google News RSS ──
    total_q = len(GOOGLE_NEWS_QUERIES)
    print(f"\n{CYAN}[1/3] Google News RSS ({total_q} zoekopdrachten)…{RESET}")
    gn_count = 0
    for i, (query, lang, country) in enumerate(GOOGLE_NEWS_QUERIES, 1):
        arts = fetch_google_news(query, lang, country)
        all_articles.extend(arts)
        gn_count += len(arts)
        bar = "█" * i + "░" * (total_q - i)
        print(f"\r     [{bar}] {i}/{total_q}  (+{len(arts)})", end="", flush=True)
        time.sleep(0.4)
    print(f"\r     {GREEN}✓ {gn_count} artikelen via Google News{RESET}          ")

    # ── Stap 2: Vakblad RSS-feeds ──
    total_f = len(RSS_FEEDS)
    print(f"{CYAN}[2/3] Vakblad RSS-feeds ({total_f} bronnen)…{RESET}")
    rss_count = 0
    for i, (name, url) in enumerate(RSS_FEEDS, 1):
        arts = fetch_rss_feed(name, url)
        all_articles.extend(arts)
        rss_count += len(arts)
        bar = "█" * i + "░" * (total_f - i)
        print(f"\r     [{bar}] {i}/{total_f}  {name:<25} (+{len(arts)})", end="", flush=True)
        time.sleep(0.2)
    print(f"\r     {GREEN}✓ {rss_count} artikelen via vakbladen{RESET}                          ")

    # ── Stap 3: NewsAPI (optioneel) ──
    if args.newsapi_key:
        total_nq = len(NEWSAPI_QUERIES)
        print(f"{CYAN}[3/3] NewsAPI.org ({total_nq} queries)…{RESET}")
        na_count = 0
        for i, q in enumerate(NEWSAPI_QUERIES, 1):
            arts = fetch_newsapi(q, args.newsapi_key, days=args.days)
            all_articles.extend(arts)
            na_count += len(arts)
            bar = "█" * i + "░" * (total_nq - i)
            print(f"\r     [{bar}] {i}/{total_nq}", end="", flush=True)
            time.sleep(0.35)
        print(f"\r     {GREEN}✓ {na_count} artikelen via NewsAPI{RESET}          ")
    else:
        print(
            f"{DIM}[3/3] NewsAPI overgeslagen "
            f"(voeg --newsapi-key KEY toe voor extra resultaten){RESET}"
        )

    # ── Dedupliceer & begrens ──
    unique = deduplicate(all_articles)
    if args.max:
        unique = unique[: args.max]

    # ── Terminal output ──
    date_str = datetime.now().strftime("%d %B %Y")
    print_articles(unique, f"Action Nieuws – {date_str}")

    # ── Exports ──
    if args.export:
        ext = Path(args.export).suffix.lower()
        if ext == ".json":
            export_json(unique, args.export)
        else:
            export_html(unique, args.export)
            if args.open:
                webbrowser.open(f"file://{Path(args.export).resolve()}")
    elif args.open:
        tmp = f"/tmp/action_news_{int(time.time())}.html"
        export_html(unique, tmp)
        webbrowser.open(f"file://{tmp}")
        print(f"{CYAN}🌐 Browser geopend: {tmp}{RESET}")

    total = len(unique)
    print(f"\n{BOLD}{'═'*62}{RESET}")
    print(f"{BOLD}Totaal: {total} unieke artikelen gevonden over Action.{RESET}")
    print(f"{DIM}Tip: gebruik --export rapport.html --open voor een visueel rapport.{RESET}\n")
    return unique


def main():
    parser = argparse.ArgumentParser(
        description="Action News Aggregator – wereldwijd nieuws over Action retail NL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Voorbeelden:
  python action_news_aggregator.py
  python action_news_aggregator.py --export rapport.html --open
  python action_news_aggregator.py --export data.json
  python action_news_aggregator.py --days 7 --max 50
  python action_news_aggregator.py --newsapi-key jouw_sleutel
  python action_news_aggregator.py --demo
""",
    )
    parser.add_argument("--export",       metavar="FILE",
                        help="Sla resultaten op als .html of .json")
    parser.add_argument("--open",         action="store_true",
                        help="Open HTML automatisch in browser")
    parser.add_argument("--days",         type=int, default=30,
                        help="Zoek nieuws van afgelopen N dagen (standaard: 30)")
    parser.add_argument("--max",          type=int, default=300,
                        help="Max artikelen in output (standaard: 300)")
    parser.add_argument("--newsapi-key",  metavar="KEY", default="",
                        help="NewsAPI.org sleutel voor extra bronnen (gratis op newsapi.org)")
    parser.add_argument("--demo",         action="store_true",
                        help="Toon zoekstrategie zonder internetverbinding")
    args = parser.parse_args()

    if args.demo:
        print_demo()
        return

    run(args)


if __name__ == "__main__":
    main()
