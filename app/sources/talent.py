"""Talent.com Argentina (agregador). Lee la primera página de resultados de cada búsqueda (~11 ofertas).

GET https://ar.talent.com/jobs?k=<puesto>&l=<lugar>
Las clases CSS del sitio llevan un sufijo que cambia, por eso se buscan por prefijo (JobCard_title, etc.).
"""
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from .http import explain, page_headers

BASE = "https://ar.talent.com"
_AGO = re.compile(r"hace\s+(\d+)\s+(minuto|hora|día|dia|semana|mes)", re.I)
_UNIT = {"minuto": 1 / 1440, "hora": 1 / 24, "día": 1, "dia": 1, "semana": 7, "mes": 30}


def ago_to_iso(text, now=None):
    m = _AGO.search(text or "")
    if not m:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=int(m.group(1)) * _UNIT[m.group(2).lower()])).strftime("%Y-%m-%dT%H:%M:%S")


class _Cards(HTMLParser):
    FIELDS = {"JobCard_title": "title", "JobCard_company": "company", "JobCard_location": "location",
              "JobCard_snippet": "snippet", "JobCard_timeText": "time"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards, self.cur, self.depth, self.field = [], None, 0, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "article" and "JobCard_card" in cls:
            self.cur, self.depth = {"url": "", "title": "", "company": "", "location": "", "snippet": "", "time": ""}, 1
            return
        if self.cur is None:
            return
        if tag == "article":
            self.depth += 1
        if tag == "a" and not self.cur["url"] and (a.get("href") or "").startswith("/view?id="):
            self.cur["url"] = BASE + a["href"]
        for prefix, name in self.FIELDS.items():
            if prefix in cls:
                self.field = name

    def handle_endtag(self, tag):
        if self.cur is None:
            return
        if tag == "article":
            self.depth -= 1
            if self.depth == 0:
                self.cards.append(self.cur)
                self.cur = None
        elif tag in ("h2", "span", "p", "div", "time"):
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
        snippet = " ".join(c["snippet"].replace("Mostrar más", "").split())
        jobs.append({
            "title": title, "company": " ".join(c["company"].split()) or "Empresa no indicada",
            "location": " ".join(c["location"].split()), "description": snippet,
            "posted": ago_to_iso(c["time"]), "source": "Talent.com", "url": c["url"],
        })
    return jobs


def _get(query, location, timeout=20):
    q = urllib.parse.urlencode({"k": query, "l": location})
    req = urllib.request.Request(f"{BASE}/jobs?{q}", headers=page_headers(BASE))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch(conf, pause=1.5):
    """conf = {"enabled", "queries", "location"}. Devuelve (ofertas, informe)."""
    location = conf.get("location") or "Buenos Aires"
    jobs, report = [], []
    for q in conf.get("queries", []):
        note = ""
        try:
            got = parse_page(_get(q, location))
        except Exception as e:
            got, note = [], f"No se pudo leer: {explain(e)}"
        jobs += got
        report.append({"busqueda": q, "encontradas": len(got), "nota": note})
        time.sleep(pause)
    return jobs, report
