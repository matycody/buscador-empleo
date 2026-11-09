"""Bumeran y ZonaJobs (Argentina): usan la misma API JSON que consume su propio sitio.

POST https://www.bumeran.com.ar/api/avisos/searchV2?pageSize=20&page=N&sort=RECIENTES
cuerpo {"filtros": [], "query": "<puesto>"}  (requiere el encabezado x-site-id: BMAR)
"""
import html as htmllib
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

from ..scoring import norm
from .http import api_headers, explain

SITES = {
    "bumeran": {"base": "https://www.bumeran.com.ar", "site_id": "BMAR", "name": "Bumeran"},
    "zonajobs": {"base": "https://www.zonajobs.com.ar", "site_id": "ZJAR", "name": "ZonaJobs"},
    # mismo sistema en otros países (cada país tiene su marca); verificados con búsquedas reales
    "bumeran_mx": {"base": "https://www.bumeran.com.mx", "site_id": "BMMX", "name": "Bumeran México"},
    "bumeran_pe": {"base": "https://www.bumeran.com.pe", "site_id": "BMPE", "name": "Bumeran Perú"},
    "laborum": {"base": "https://www.laborum.cl", "site_id": "BMCL", "name": "Laborum (Chile)"},
    "multitrabajos": {"base": "https://www.multitrabajos.com", "site_id": "BMEC", "name": "Multitrabajos (Ecuador)"},
    "konzerta": {"base": "https://www.konzerta.com", "site_id": "BMPA", "name": "Konzerta (Panamá)"},
}
BASE = SITES["bumeran"]["base"]  # compatibilidad


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-")


def _text(s):
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def _iso(dmy_hms):
    try:
        d = datetime.strptime(dmy_hms, "%d-%m-%Y %H:%M:%S")
        return d.replace(tzinfo=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def to_job(a, site="bumeran"):
    info = SITES[site]
    company = "" if a.get("confidencial") else (a.get("empresa") or "")
    slug = "-".join(x for x in (_slug(a.get("titulo")), _slug(company)) if x)
    modo = a.get("modalidadTrabajo") or ""
    tipo = a.get("tipoTrabajo") or ""
    head = " | ".join(x for x in (modo, tipo) if x)
    return {
        "title": a.get("titulo", "").strip(), "company": company or "Confidencial",
        "location": a.get("localizacion") or "",
        "description": (head + ". " if head else "") + _text(a.get("detalle"))[:1500],
        "posted": _iso(a.get("fechaHoraPublicacion")), "source": info["name"],
        "url": f"{info['base']}/empleos/{slug}-{a['id']}.html",
    }


def _search(query, page, timeout=20, site="bumeran"):
    info = SITES[site]
    url = f"{info['base']}/api/avisos/searchV2?pageSize=20&page={page}&sort=RECIENTES"
    body = json.dumps({"filtros": [], "query": query}).encode("utf-8")
    headers = {**api_headers(info["base"]), "x-site-id": info["site_id"]}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(conf, pause=1.0, site="bumeran"):
    """conf = {"enabled", "queries", "max_pages", "zonas"}. Devuelve (ofertas, informe)."""
    zonas = [norm(z) for z in conf.get("zonas", []) if z.strip()]
    jobs, report = [], []
    for q in conf.get("queries", []):
        found, note = 0, ""
        for page in range(int(conf.get("max_pages", 2))):
            try:
                data = _search(q, page, site=site)
            except Exception as e:
                note = f"No se pudo leer: {explain(e)}"
                break
            items = data.get("content", [])
            for a in items:
                if zonas and not any(z in norm(a.get("localizacion")) for z in zonas):
                    continue
                jobs.append(to_job(a, site))
                found += 1
            if len(items) < 20:
                break
            time.sleep(pause)
        time.sleep(pause)
        report.append({"busqueda": q, "encontradas": found, "nota": note})
    return jobs, report
