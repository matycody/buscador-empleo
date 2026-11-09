"""Portal Empleo (Ministerio de Capital Humano, portalempleo.gob.ar): ofertas de todo el país, gratis y públicas.

GET https://portalempleo.gob.ar/ofertas-laborales?Q=<puesto>&page-number=<n>   (10 ofertas por página, HTML)
Como es nacional, se guardan solo las ofertas cuyo lugar contiene alguna de tus zonas.
"""
import re
import time
import urllib.parse
import urllib.request
from html import unescape

from ..scoring import norm
from .http import explain, page_headers

BASE = "https://portalempleo.gob.ar"
_CARD = re.compile(r"<article class=\"pe-oferta-card-item\">(.*?)</article>", re.S)


def _field(block, cls):
    m = re.search(r'class="[^"]*\b' + re.escape(cls) + r'\b[^"]*"[^>]*>(.*?)</', block, re.S)
    return unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""


def parse_page(html):
    jobs = []
    for block in _CARD.findall(html):
        href = re.search(r'href="(/ofertas-laborales/details/[^"]+)"', block)
        title = _field(block, "pe-oferta-puesto")
        if not href or not title:
            continue
        date = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', block)
        badges = [unescape(b).strip() for b in re.findall(r'pe-oferta-badge[^"]*"[^>]*>([^<]+)<', block)]
        desc = _field(block, "pe-oferta-desc")
        jobs.append({
            "title": title.capitalize(),
            "company": _field(block, "pe-oferta-empresa"),
            "location": _field(block, "pe-oferta-loc-texto").title(),
            "description": " · ".join(x for x in [desc] + badges if x),
            "posted": date.group(1) + "T00:00:00" if date else None,
            "source": "Portal Empleo",
            "url": BASE + href.group(1),
        })
    return jobs


def total_of(html):
    m = re.search(r"Mostrando <strong>\d+</strong> de <strong>(\d+)</strong>", html)
    return int(m.group(1)) if m else 0


def _get(query, page, timeout=20):
    qs = urllib.parse.urlencode({"Q": query, "page-number": page})
    req = urllib.request.Request(f"{BASE}/ofertas-laborales?{qs}", headers=page_headers(BASE + "/"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")


def fetch(conf, pause=1.0):
    """conf = {"enabled", "queries", "max_pages", "zonas"}. Devuelve (ofertas, informe)."""
    zonas = [norm(z) for z in conf.get("zonas", []) if z and norm(z) != "remoto"]
    jobs, report, seen = [], [], set()
    for q in conf.get("queries", []):
        found, note = 0, ""
        for page in range(1, int(conf.get("max_pages", 2)) + 1):
            try:
                html = _get(q, page)
            except Exception as e:
                note = f"No se pudo leer: {explain(e)}"
                break
            got = parse_page(html)
            for j in got:
                if j["url"] in seen or (zonas and not any(z in norm(j["location"]) for z in zonas)):
                    continue
                seen.add(j["url"])
                jobs.append(j)
                found += 1
            if len(got) < 10:
                break
            time.sleep(pause)
        time.sleep(pause)
        report.append({"busqueda": q, "encontradas": found, "nota": note})
    return jobs, report
