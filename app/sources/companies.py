"""Revisa las páginas de empleo de las empresas de interés.

Hay lectores específicos para Mercado Libre (API JSON de su sitio de carreras) y Ualá
(datos embebidos en la página). Para cualquier otra empresa se usa el lector genérico.

Lee el HTML de cada página y se queda con los links cuyo texto parece un puesto
(coincide con las palabras clave de tus CV). Muchas páginas de empleo cargan
con JavaScript y no muestran nada en el HTML: en ese caso se informa, no se inventa.
"""
import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from ..scoring import norm
from .http import explain, page_headers



class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._txt = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._txt = []

    def handle_data(self, data):
        if self._href is not None:
            self._txt.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._txt).split())
            if text:
                self.links.append((text, self._href))
            self._href = None


def _check_one(empresa, keywords, timeout=15):
    req = urllib.request.Request(empresa["url"], headers=page_headers())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        html = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    parser = _Links()
    parser.feed(html)
    jobs, seen = [], set()
    for text, href in parser.links:
        if not 8 <= len(text) <= 120 or href.startswith(("#", "javascript:", "mailto:")):
            continue
        n = norm(text)
        if not any(k in n for k in keywords):
            continue
        url = urljoin(empresa["url"], href)
        if url in seen:
            continue
        seen.add(url)
        jobs.append({"title": text, "company": empresa["name"], "location": "", "description": "",
                     "posted": None, "source": f"Web de {empresa['name']}", "url": url})
    return jobs


def _get(url, timeout=20, limit=3_000_000):
    req = urllib.request.Request(url, headers=page_headers())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit).decode(r.headers.get_content_charset() or "utf-8", "replace")


def _matches(text, keywords):
    n = norm(text)
    return any(k in n for k in keywords)


# ---------- Mercado Libre: API JSON pública de su sitio de carreras ----------
MELI = "https://careers-meli.mercadolibre.com"


def _meli(empresa, keywords, max_pages=30):
    jobs, start = [], 0
    for _ in range(max_pages):
        data = json.loads(_get(f"{MELI}/api/positions?sort_by=timestamp&location=Argentina&start={start}"))
        for p in data.get("positions", []):
            extra = f"{p.get('department', '')} {p.get('name', '')}"
            if not _matches(extra, keywords):
                continue
            posted = None
            if p.get("postedTs"):
                posted = datetime.fromtimestamp(p["postedTs"], tz=timezone.utc).isoformat()
            modo = {"onsite": "Presencial", "hybrid": "Híbrido", "remote": "Remoto"}.get(p.get("workLocationOption"), "")
            jobs.append({
                "title": p["name"], "company": empresa["name"],
                "location": ", ".join(p.get("locations", [])),
                "description": f"Área: {p.get('department', '')}. Modalidad: {modo}.".strip(),
                "posted": posted, "source": "Mercado Libre Careers",
                "url": f"{MELI}/es/positions?id={p['id']}",
            })
        if not data.get("hasMore"):
            break
        start += len(data.get("positions", [])) or 12
    return jobs


# ---------- Ualá: las posiciones vienen dentro del HTML (__NEXT_DATA__) ----------
def _find_positions(o):
    if isinstance(o, list):
        if o and isinstance(o[0], dict) and {"id", "title", "description"} <= o[0].keys():
            return o
        for x in o:
            r = _find_positions(x)
            if r:
                return r
    elif isinstance(o, dict):
        for v in o.values():
            r = _find_positions(v)
            if r:
                return r
    return None


def _uala(empresa, keywords):
    html = _get("https://www.ua.la/sumate")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("la página no devolvió los datos (puede estar pidiendo verificación anti-bots)")
    positions = _find_positions(json.loads(m.group(1))) or []
    jobs = []
    for p in positions:
        desc = re.sub(r"<[^>]+>", " ", p.get("description") or "")
        desc = " ".join(desc.split())[:1500]
        jobs.append({
            "title": p["title"], "company": empresa["name"],
            "location": p.get("country") or "", "description": f"{p.get('department') or ''}. {desc}".strip(". "),
            "posted": None, "source": "Ualá Súmate", "url": f"https://www.ua.la/sumate/{p['id']}",
        })
    return jobs


def _adapter(url):
    host = urlparse(url).netloc.lower()
    if "careers-meli.mercadolibre.com" in host:
        return _meli
    if host.endswith("ua.la") or host.endswith("uala.com.ar"):
        return _uala
    return None


def fetch(cfg):
    keywords = {norm(k) for p in cfg["profiles"].values() for k in p["keywords"]}
    jobs, report = [], []
    for e in cfg.get("empresas", []):
        if not e.get("url"):
            continue
        try:
            adapter = _adapter(e["url"])
            found = adapter(e, keywords) if adapter else _check_one(e, keywords)
            jobs += found
            report.append({"empresa": e["name"], "encontradas": len(found),
                           "nota": "" if found else "No se leyeron puestos (la página probablemente carga con JavaScript o no hay ninguno que coincida). Abrila desde el link."})
        except Exception as ex:
            report.append({"empresa": e["name"], "encontradas": 0, "nota": f"No se pudo abrir: {explain(ex)}"})
    return jobs, report
