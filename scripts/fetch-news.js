#!/usr/bin/env node
// Fetch Action retailer news from Google News RSS and save to docs/news.json
// Runs server-side (no CORS), triggered by GitHub Actions every 30 minutes.

import { writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(__dirname, '../docs/news.json');

// ── Queries (per land, lokale taal) ──────────────────────────────
const QUERIES = [
  // Nederland
  ['Action winkelketen Nederland',               'nl', 'NL'],
  ['Action distributiecentrum logistiek',        'nl', 'NL'],
  ['Action winkel opening Nederland',            'nl', 'NL'],
  ['Action omzet resultaten financieel',         'nl', 'NL'],
  ['Action medewerkers staking cao personeel',   'nl', 'NL'],
  // België
  ['Action winkel opening België',               'nl', 'BE'],
  ['Action magasin ouverture Belgique',          'fr', 'BE'],
  // Frankrijk
  ['Action magasin ouverture France',            'fr', 'FR'],
  ['Action entrepôt distribution grève France',  'fr', 'FR'],
  ['Action chiffre affaires résultats France',   'fr', 'FR'],
  // Duitsland
  ['Action Filiale Eröffnung Deutschland',       'de', 'DE'],
  ['Action Mitarbeiter Logistik Deutschland',    'de', 'DE'],
  // Zwitserland
  ['Action Filiale Schweiz Eröffnung',           'de', 'CH'],
  // Oostenrijk
  ['Action Filiale Österreich Eröffnung',        'de', 'AT'],
  // Spanje
  ['Action tienda apertura España',              'es', 'ES'],
  // Portugal
  ['Action loja abertura Portugal',              'pt', 'PT'],
  // Italië
  ['Action negozio apertura Italia',             'it', 'IT'],
  // Roemenië
  ['Action magazin deschidere Romania',          'ro', 'RO'],
  // Polen
  ['Action sklep otwarcie Polska',               'pl', 'PL'],
  // Tsjechië
  ['Action obchod otevření Česko',               'cs', 'CZ'],
  // Slowakije
  ['Action obchod otvorenie Slovensko',          'sk', 'SK'],
  // Slovenië
  ['Action trgovina odprtje Slovenija',          'sl', 'SI'],
  // Engels (internationaal)
  ['Action retailer Europe expansion revenue',   'en', 'GB'],
];

// ── Relevantiefilter ─────────────────────────────────────────────
const RETAIL_TERMS = [
  'winkel','filiaal','winkels','filialen','winkelketen',
  'store','stores','shop','retailer','discounter','non-food',
  'magasin','enseigne','boutique',
  'filiale','filialen','laden','geschäft',
  'tienda','tiendas',
  'loja','lojas',
  'magazin',
  'sklep','sklepy',
  'negozio','negozi',
  'obchod','obchody',
  'trgovina',
  'distributiecentrum','entrepôt','warehouse','magazijn','lager','depozit','magazyn','sklad',
  'medewerker','personeel','staking','grève','streik','huelga','grevă','strajk','sciopero',
  'omzet','revenue','fatturato','chiffre','umsatz',
  'opening','ouverture','eröffnung','apertura','abertura','deschidere','otwarcie','odprtje',
  'logistiek','logistique','logistik','logística','logistica',
  'supply chain','cao','fnv',
];

function isRelevant(title, description) {
  const text = title + ' ' + (description || '');
  if (!/\bAction\b/.test(text)) return false;
  const lc = text.toLowerCase();
  return RETAIL_TERMS.some(t => lc.includes(t));
}

// ── Categorisering ───────────────────────────────────────────────
const CATS = {
  'Supply Chain & Distributie': [
    'supply chain','distributie','warehouse','logistiek','fulfillment','leverancier',' dc ',
    'transport','magazijn','inkoop','entrepôt','almacén','armazém','lager','depozit',
    'magazyn','sklad','logistique','logistik','logística',
  ],
  'Expansie & Openingen': [
    'opening','filiaal','winkel',' store','expansie','expansion','ouverture','eröffnung',
    'tienda','loja','magasin','negozio','obchod','sklep','otwarcie','deschidere',
    'apertura','abertura','odprtje','otevření','otvorenie',
  ],
  'Financieel': [
    'omzet','groei','resultaat','winst','financieel','revenue','profit','kwartaal',
    'overname','jaarverslag','fatturato','chiffre','umsatz','cifra','resultados',
  ],
  'Technologie & Innovatie': [
    'technologie','digitaal','robot','automation','innovatie','software','rfid','scan',' ai ',
  ],
  'Duurzaamheid': [
    'duurzaam','co2','milieu','sustainability','esg','klimaat','recycl','groen','emissie',
    'durabilité','nachhaltigkeit','sostenibili',
  ],
  'Personeel & Arbeid': [
    'personeel','medewerker','cao','fnv','arbeids','vacature','staking','loon',
    'grève','syndicat','salariés','streik','gewerkschaft','huelga','sindicato',
    'grevă','sindical','strajk','związek','sciopero','sindacato','štrajk',
  ],
};

function categorize(title, description) {
  const text = (title + ' ' + (description || '')).toLowerCase();
  for (const [cat, kws] of Object.entries(CATS)) {
    if (kws.some(kw => text.includes(kw))) return cat;
  }
  return 'Algemeen Nieuws';
}

// ── RSS-parser (regex, geen externe deps) ────────────────────────
function parseRSS(xml, lang, country) {
  const items = [];
  const itemRx = /<item>([\s\S]*?)<\/item>/g;
  let m;
  while ((m = itemRx.exec(xml)) !== null) {
    const block = m[1];
    const tag = (name) => {
      const rx = new RegExp(
        `<${name}[^>]*>(?:<!\\[CDATA\\[([\\s\\S]*?)\\]\\]>|([\\s\\S]*?))<\\/${name}>`, 'i'
      );
      const t = rx.exec(block);
      return t ? (t[1] ?? t[2] ?? '').trim() : '';
    };
    const srcUrlM = /<source\s+url="([^"]*)"/.exec(block);
    const srcNameM = /<source[^>]*>([\s\S]*?)<\/source>/.exec(block);
    const title       = tag('title');
    const rawDesc     = tag('description');
    const description = rawDesc.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim().slice(0, 280);
    const url         = tag('link') || (srcUrlM ? srcUrlM[1] : '');
    const publishedAt = tag('pubDate');
    const sourceName  = (srcNameM ? srcNameM[1].trim() : '') || `Google News (${lang.toUpperCase()})`;
    if (title.length > 3) items.push({ title, description, url, publishedAt, source: { name: sourceName }, lang, country });
  }
  return items;
}

// ── Fetch één query ───────────────────────────────────────────────
async function fetchQuery(query, lang, country) {
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=${lang}&gl=${country}&ceid=${country}:${lang}`;
  try {
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; ActionNewsBot/1.0; +https://github.com)' },
      signal: AbortSignal.timeout(15000),
    });
    if (!resp.ok) { console.warn(`HTTP ${resp.status} for: ${query}`); return []; }
    return parseRSS(await resp.text(), lang, country);
  } catch (e) {
    console.warn(`Failed [${lang}/${country}] "${query}": ${e.message}`);
    return [];
  }
}

// ── Deduplicatie ─────────────────────────────────────────────────
function dedupe(articles) {
  const seen = new Set();
  return articles.filter(a => {
    const k = a.title.toLowerCase().slice(0, 65);
    if (!k || seen.has(k)) return false;
    seen.add(k); return true;
  });
}

// ── Main ─────────────────────────────────────────────────────────
const results = await Promise.allSettled(
  QUERIES.map(([q, l, c]) => fetchQuery(q, l, c))
);
const merged   = results.flatMap(r => r.status === 'fulfilled' ? r.value : []);
const relevant = merged.filter(a => isRelevant(a.title, a.description));
const unique   = dedupe(relevant);

unique.forEach(a => { a.category = categorize(a.title, a.description); });
unique.sort((a, b) => {
  const da = new Date(a.publishedAt), db = new Date(b.publishedAt);
  if (isNaN(da) && isNaN(db)) return 0;
  if (isNaN(da)) return 1;
  if (isNaN(db)) return -1;
  return db - da;
});

const output = { fetchedAt: new Date().toISOString(), articles: unique };
writeFileSync(OUT, JSON.stringify(output, null, 2));
console.log(`Saved ${unique.length} articles to docs/news.json`);
