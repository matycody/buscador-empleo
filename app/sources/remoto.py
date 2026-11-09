"""Ofertas remotas internacionales (APIs públicas, gratis y sin clave): Remotive, Arbeitnow y Jobicy.

- Remotive  https://remotive.com/api/remote-jobs?search=<q>   (pide dar crédito; datos con 24 h de demora)
- Arbeitnow https://www.arbeitnow.com/api/job-board-api       (Europa y remoto)
- Jobicy    https://jobicy.com/api/v2/remote-jobs?tag=<q>      (remoto en todo el mundo)
Son ofertas en inglés, sobre todo de tecnología. Se piden pocas veces por búsqueda para no abusar de los servicios.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape

from ..scoring import norm
from .http import explain, page_headers


def _json(url, timeout=20):
    req = urllib.request.Request(url, headers={**page_headers(url), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(5_000_000).decode("utf-8", "replace"))


def _plain(html, limit=3000):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()[:limit]


def parse_remotive(data):
    return [{
        "title": j.get("title", ""), "company": j.get("company_name", ""),
        "location": ("Remoto · " + j["candidate_required_location"]) if j.get("candidate_required_location") else "Remoto",
        "description": _plain(j.get("description")), "posted": (j.get("publication_date") or "")[:19] or None,
        "source": "Remotive", "url": j.get("url", ""),
    } for j in data.get("jobs", []) if j.get("url") and j.get("title")]


def parse_arbeitnow(data):
    jobs = []
    for j in data.get("data", []):
        if not j.get("url") or not j.get("title"):
            continue
        ts = j.get("created_at")
        jobs.append({
            "title": j["title"], "company": j.get("company_name", ""),
            "location": ("Remoto · " if j.get("remote") else "") + (j.get("location") or ""),
            "description": _plain(j.get("description")),
            "posted": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") if isinstance(ts, (int, float)) else None,
            "source": "Arbeitnow", "url": j["url"],
        })
    return jobs


def parse_jobicy(data):
    return [{
        "title": unescape(j.get("jobTitle", "")), "company": unescape(j.get("companyName", "")),
        "location": "Remoto · " + (j["jobGeo"] if isinstance(j.get("jobGeo"), str) else ", ".join(j.get("jobGeo") or [])),
        "description": _plain(j.get("jobDescription") or j.get("jobExcerpt")),
        "posted": (j.get("pubDate") or "")[:19].replace(" ", "T") or None, "source": "Jobicy", "url": j.get("url", ""),
    } for j in data.get("jobs", []) if j.get("url") and j.get("jobTitle")]


def fetch(conf, pause=1.0):
    """conf = {"enabled", "queries"}. Devuelve (ofertas, informe). Se queda con las que mencionan el puesto buscado."""
    queries = [q for q in conf.get("queries", []) if q and len(q) >= 3]
    jobs, report, seen = [], [], set()
    for q in queries:
        enc = urllib.parse.quote(q)
        for name, url, parse in (
            ("Remotive", f"https://remotive.com/api/remote-jobs?search={enc}&limit=30", parse_remotive),
            ("Jobicy", f"https://jobicy.com/api/v2/remote-jobs?count=30&tag={enc}", parse_jobicy),
        ):
            found, note = 0, ""
            try:
                for j in parse(_json(url)):
                    if j["url"] not in seen:
                        seen.add(j["url"]); jobs.append(j); found += 1
            except Exception as e:
                note = f"No se pudo leer {name}: {explain(e)}"
            report.append({"busqueda": f"{q} ({name})", "encontradas": found, "nota": note})
            time.sleep(pause)
    found, note = 0, ""
    try:  # Arbeitnow no filtra por texto: se baja una página y se queda con lo que coincide
        words = [norm(q) for q in queries]
        for j in parse_arbeitnow(_json("https://www.arbeitnow.com/api/job-board-api")):
            if j["url"] not in seen and any(w in norm(j["title"] + " " + j["description"]) for w in words):
                seen.add(j["url"]); jobs.append(j); found += 1
    except Exception as e:
        note = f"No se pudo leer Arbeitnow: {explain(e)}"
    report.append({"busqueda": "Arbeitnow (Europa)", "encontradas": found, "nota": note})
    return jobs, report
