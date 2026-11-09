"""LinkedIn: lista pública de empleos (la que ve cualquiera sin iniciar sesión).

Ojo: los términos de LinkedIn no permiten la lectura automática. Por eso viene APAGADO por defecto,
lee pocas páginas, con pausas largas, y no usa ninguna cuenta. Si LinkedIn responde con un bloqueo
(429/999), el programa se detiene y lo avisa. Alternativa más segura: alertas de LinkedIn por Gmail.
GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=&location=&start=
"""
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .http import explain, page_headers

BASE = "https://www.linkedin.com"


class _Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards, self.cur, self.field, self.depth = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "li":
            self.cur, self.depth = {"title": "", "company": "", "location": "", "url": "", "date": ""}, 1
            return
        if self.cur is None:
            return
        if tag == "a" and "base-card__full-link" in cls and a.get("href"):
            self.cur["url"] = a["href"].split("?")[0]
        if "base-search-card__title" in cls:
            self.field = "title"
        elif "base-search-card__subtitle" in cls:
            self.field = "company"
        elif "job-search-card__location" in cls:
            self.field = "location"
        if tag == "time" and a.get("datetime"):
            self.cur["date"] = a["datetime"]

    def handle_endtag(self, tag):
        if self.cur is None:
            return
        if tag == "li":
            self.cards.append(self.cur)
            self.cur = None
        elif tag in ("h3", "h4", "span", "a", "div"):
            self.field = None

    def handle_data(self, data):
        if self.cur is not None and self.field:
            self.cur[self.field] += data


def parse_page(html):
    p = _Cards()
    p.feed(html)
    jobs = []
    for c in p.cards:
        title = " ".join(c["title"].split())
        if not title or not c["url"]:
            continue
        jobs.append({
            "title": title, "company": " ".join(c["company"].split()) or "Empresa no indicada",
            "location": " ".join(c["location"].split()), "description": "",
            "posted": c["date"] or None, "source": "LinkedIn", "url": c["url"],
        })
    return jobs


def _get(query, location, start, timeout=20):
    q = urllib.parse.urlencode({"keywords": query, "location": location, "start": start})
    req = urllib.request.Request(f"{BASE}/jobs-guest/jobs/api/seeMoreJobPostings/search?{q}", headers=page_headers(BASE))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch(conf, pause=3.0):
    """conf = {"enabled", "queries", "location", "max_pages"}. Devuelve (ofertas, informe)."""
    location = conf.get("location") or "Buenos Aires, Argentina"
    jobs, report = [], []
    blocked = False
    for q in conf.get("queries", []):
        if blocked:
            continue
        found, note = 0, ""
        for page in range(int(conf.get("max_pages", 1))):
            try:
                got = parse_page(_get(q, location, page * 10))
            except Exception as e:
                note = f"No se pudo leer: {explain(e)}"
                if re.search(r"429|999|403", str(e)):
                    blocked = True
                break
            jobs += got
            found += len(got)
            if len(got) < 10:
                break
            time.sleep(pause)
        report.append({"busqueda": q, "encontradas": found, "nota": note})
        time.sleep(pause)
    return jobs, report
