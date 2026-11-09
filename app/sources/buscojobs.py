"""BuscoJobs Argentina: la página de resultados trae las ofertas en el JSON de __NEXT_DATA__.

GET https://www.buscojobs.com.ar/ofertas/<puesto-con-guiones>_[/<pagina>]  (15 ofertas por página)
"""
import json
import re
import time
import urllib.request

from ..scoring import norm
from .http import explain, page_headers

BASE = "https://www.buscojobs.com.ar"
PER_PAGE = 15
_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-")


def _place(o):
    parts = [(o.get("Ciudad") or {}).get("Nombre"), (o.get("Departamento") or {}).get("Nombre")]
    return ", ".join(p for p in parts if p)


def to_job(o):
    company = "" if o.get("Confidencial") else (o.get("NombreEmpresa") or o.get("Empresa") or "")
    place = _place(o)
    title = (o.get("CargoVacante") or "").strip()
    slug = "-".join(x for x in (_slug(title), "en", _slug(place)) if x)
    flags = [t for k, t in (("EsPasantia", "Pasantía"),
                            ("PermiteTeletrabajo", "Teletrabajo"), ("PermiteTrabajoHibrido", "Híbrido"))
             if o.get(k)]
    desc = " ".join((o.get("Descripcion") or "").split())
    return {
        "title": title, "company": company or "Confidencial", "location": place,
        "description": (" | ".join(flags) + ". " if flags else "") + desc[:1500],
        "posted": o.get("FechaInicio"), "source": "BuscoJobs",
        "url": f"{BASE}/{slug}-ID-{o['IdOferta']}",
    }


def parse_page(html):
    m = _NEXT.search(html)
    if not m:
        return []
    data = json.loads(m.group(1))
    return (data.get("props", {}).get("pageProps", {}).get("resultadosIniciales") or {}).get("ofertas") or []


def _get(query, page, timeout=20):
    url = f"{BASE}/ofertas/{_slug(query)}_" + (f"/{page}" if page > 1 else "")
    req = urllib.request.Request(url, headers=page_headers(BASE))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch(conf, pause=1.0):
    """conf = {"enabled", "queries", "max_pages", "zonas"}. Devuelve (ofertas, informe)."""
    zonas = [norm(z) for z in conf.get("zonas", []) if z.strip()]
    jobs, report = [], []
    for q in conf.get("queries", []):
        found, note = 0, ""
        for page in range(1, int(conf.get("max_pages", 2)) + 1):
            try:
                items = parse_page(_get(q, page))
            except Exception as e:
                note = f"No se pudo leer: {explain(e)}"
                break
            for o in items:
                if zonas and not any(z in norm(_place(o)) for z in zonas):
                    continue
                jobs.append(to_job(o))
                found += 1
            if len(items) < PER_PAGE:
                break
            time.sleep(pause)
        time.sleep(pause)
        report.append({"busqueda": q, "encontradas": found, "nota": note})
    return jobs, report
