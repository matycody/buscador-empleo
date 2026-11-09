"""Jooble (agregador de ofertas) usando su API oficial y gratuita.

Se necesita una clave: https://jooble.org/api/about  (se pide con un mail y llega en el momento).
La clave se guarda solo en esta PC (data/secrets.json) y se carga desde Configuración.
POST https://jooble.org/api/<clave>   {"keywords": "...", "location": "...", "page": "1"}
"""
import json
import re
import time
import urllib.request

from .. import config
from .http import explain

_TAGS = re.compile(r"<[^>]+>")


def to_job(j):
    updated = (j.get("updated") or "")[:19] or None
    snippet = " ".join(_TAGS.sub(" ", j.get("snippet") or "").replace("&nbsp;", " ").split())
    return {
        "title": " ".join(_TAGS.sub(" ", j.get("title") or "").split()),
        "company": (j.get("company") or "").strip() or "Empresa no indicada",
        "location": (j.get("location") or "").strip(),
        "description": snippet,
        "posted": updated, "source": "Jooble" + (f" ({j['source']})" if j.get("source") else ""),
        "url": j.get("link") or "",
    }


def _search(key, query, location, page, timeout=20):
    body = json.dumps({"keywords": query, "location": location, "page": str(page)}).encode("utf-8")
    req = urllib.request.Request(
        f"https://jooble.org/api/{key}", data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "BusquedaLaboral/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(conf, pause=1.0):
    """conf = {"enabled", "queries", "max_pages", "location"}. Devuelve (ofertas, informe)."""
    key = config.get_secret("jooble_key", "JOOBLE_API_KEY")
    if not key:
        return [], [{"busqueda": "", "encontradas": 0, "nota": "Falta la clave de la API de Jooble (Configuración → Jooble)."}]
    location = conf.get("location") or "Buenos Aires"
    jobs, report = [], []
    for q in conf.get("queries", []):
        found, note = 0, ""
        for page in range(1, int(conf.get("max_pages", 2)) + 1):
            try:
                items = _search(key, q, location, page).get("jobs", [])
            except Exception as e:
                note = f"No se pudo leer: {explain(e)}"
                break
            for j in items:
                if j.get("link") and j.get("title"):
                    jobs.append(to_job(j))
                    found += 1
            if not items:
                break
            time.sleep(pause)
        time.sleep(pause)
        report.append({"busqueda": q, "encontradas": found, "nota": note})
    return jobs, report
