"""Computrabajo Argentina: lee las páginas de resultados (HTML ya armado, 20 ofertas por página).

URL de búsqueda:  https://ar.computrabajo.com/trabajo-de-<puesto>-en-<region>?p=<pagina>
"""
import html as htmllib
from html.parser import HTMLParser
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from ..scoring import norm
from .http import explain, page_headers

BASE = "https://ar.computrabajo.com"


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-")


def _clean(fragment):
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).split())


def _relative_date(text):
    t = norm(text)
    now = datetime.now(timezone.utc)
    if "ayer" in t:
        return (now - timedelta(days=1)).isoformat()
    if "hoy" in t:
        return now.isoformat()
    m = re.search(r"(\d+)\s*(minuto|hora|dia|semana|mes)", t)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {"minuto": timedelta(minutes=n), "hora": timedelta(hours=n), "dia": timedelta(days=n),
             "semana": timedelta(weeks=n), "mes": timedelta(days=30 * n)}[unit]
    return (now - delta).isoformat()


def parse_page(page_html, base=BASE):
    jobs = []
    for block in page_html.split('<article class="box_offer')[1:]:
        block = block.split("</article>")[0]
        m = re.search(r'<a[^>]*class="js-o-link[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        href, title = m.group(1).split("#")[0], _clean(m.group(2))
        comp = re.search(r"offer-grid-article-company-url[^>]*>(.*?)</a>", block, re.S)
        if comp:
            company = _clean(comp.group(1))
        else:
            p = re.search(r'<p class="dFlex[^"]*"[^>]*>(.*?)</p>', block, re.S)
            company = _clean(p.group(1)) if p else ""
        loc = re.search(r'<p class="fs16 fc_base mt5">\s*<span class="mr10">(.*?)</span>', block, re.S)
        sal = re.search(r'i_salary"></span>(.*?)</span>', block, re.S)
        date = re.search(r'<p class="fs13 fc_aux mt15">(.*?)</p>', block, re.S)
        jobs.append({
            "title": title, "company": company,
            "location": _clean(loc.group(1)) if loc else "",
            "description": f"Sueldo publicado: {_clean(sal.group(1))}." if sal else "",
            "posted": _relative_date(_clean(date.group(1))) if date else None,
            "source": "Computrabajo", "url": base + href if href.startswith("/") else href,
        })
    return jobs


class _Detail(HTMLParser):
    """Extrae el texto del bloque <div div-link="oferta">, sin los botones del final."""

    def __init__(self):
        super().__init__()
        self.depth = 0          # profundidad dentro del bloque (0 = fuera)
        self.skip = 0           # profundidad dentro de una zona que se ignora
        self.parts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.depth == 0:
            if tag == "div" and a.get("div-link") == "oferta":
                self.depth = 1
            return
        if tag == "br":
            self.parts.append("\n")
        if tag == "div":
            self.depth += 1
            if self.skip:
                self.skip += 1
            elif "posSticky" in (a.get("class") or ""):
                self.skip = 1
        elif tag in ("p", "li", "h2") and not self.skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.depth == 0:
            return
        if tag == "div":
            self.depth -= 1
            if self.skip:
                self.skip -= 1
        elif tag in ("p", "li", "h2") and not self.skip:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.parts.append(data)


PORTAL_SEP = "§PORTAL§"
_CUT = ("Aptitudes asociadas a esta oferta", "Avísame con ofertas similares", "Denunciar empleo",
        "Gracias por ayudarnos a mejorar", "Hay 0 aptitudes que faltan", "Mostar competencias")


def clean_description(text):
    """Separa el texto del aviso de lo que agrega la página del portal (aptitudes, palabras clave, botones).
    Lo del portal queda al final, después de PORTAL_SEP, para mostrarlo aparte."""
    text = text or ""
    if PORTAL_SEP in text:
        return text
    cuts = [text.find(c) for c in _CUT if text.find(c) != -1]
    if not cuts:
        return text
    main = text[:min(cuts)].strip()
    extra = []
    m = re.search(r"Aptitudes asociadas a esta oferta\s*(?:Nuevo)?\s*\n(.*?)(?:\nVer \d+ aptitudes|\nHay \d+ aptitudes|\nSi las tienes|$)", text, re.S)
    if m:
        skills = [x.strip() for x in m.group(1).split("\n") if x.strip()]
        if skills:
            extra.append("Aptitudes: " + ", ".join(skills))
    k = re.search(r"Palabras clave:\s*(.+?)(?:\nHace \d|\nAvísame|$)", text, re.S)
    if k:
        extra.append("Palabras clave: " + " ".join(k.group(1).split()))
    return main + (f"\n{PORTAL_SEP}\n" + "\n".join(extra) if extra else "")


def parse_detail(page_html):
    """Texto limpio de la descripción y los requisitos de un aviso."""
    d = _Detail()
    d.feed(page_html)
    text = htmllib.unescape("".join(d.parts))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return clean_description(re.sub(r"^Descripción de la oferta\s*", "", text)[:6000])


def fetch_detail(url):
    return parse_detail(_get(url))


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=page_headers("{0.scheme}://{0.netloc}/".format(urllib.parse.urlsplit(url))))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")


def fetch(conf, pause=1.0):
    """conf = {"enabled", "region", "queries", "max_pages"}. Devuelve (ofertas, informe)."""
    jobs, report = [], []
    sub = conf.get("pais_sub") or "ar"
    base = f"https://{sub}.computrabajo.com"
    # las regiones («buenos-aires-gba») son de Argentina; en otros países se busca en todo el país
    region = _slug(conf.get("region") or "buenos-aires-gba") if sub == "ar" else ""
    for q in conf.get("queries", []):
        slug, found = _slug(q), 0
        if not slug:
            continue
        note = ""
        for page in range(1, int(conf.get("max_pages", 2)) + 1):
            url = f"{base}/trabajo-de-{slug}" + (f"-en-{region}" if region else "") + (f"?p={page}" if page > 1 else "")
            try:
                got = parse_page(_get(url), base)
            except Exception as e:
                note = f"No se pudo leer: {explain(e)}"
                break
            jobs += got
            found += len(got)
            if len(got) < 20:
                break
            time.sleep(pause)
        time.sleep(pause)
        report.append({"busqueda": q, "encontradas": found, "nota": note})
    return jobs, report
