"""Servicio de Empleo AMIA (empleos.amia.org.ar): bolsa de trabajo gratuita, ofertas de CABA, GBA y otras ciudades.

Las ofertas están en https://focuspagina.amia.org.ar/Autoconsulta/Ofertas/Default.asp (últimas ~20, una sola página).
No tiene buscador por texto: se leen todas y después el puntaje decide cuáles te sirven.
Se guardan las de tus zonas y las de CABA / Buenos Aires (quedan a distancia razonable).
"""
import re
import urllib.request
from html import unescape

from ..scoring import norm
from .http import explain, page_headers

BASE = "https://focuspagina.amia.org.ar"
LISTA = BASE + "/Autoconsulta/Ofertas/Default.asp?contentOnly=1&pNodoId=&pAreaPuestoId="
_SIEMPRE = ("caba", "capital federal", "buenos aires", "gba", "amba")


def _text(html):
    html = re.sub(r"<br\s*/?>", "\n", html)
    return unescape(re.sub(r"<[^>]+>", "", html))


def parse_page(html):
    jobs = []
    for block in html.split('class="ContenidoCopeteListado"')[1:]:
        head = re.search(r'class="map-provincias">(.*?)</span>', block, re.S)
        ident = re.search(r"LoginAlert\('(\d+)',\s*'(\d+)'", block)
        if not head or not ident:
            continue
        title = re.sub(r"\s+", " ", _text(head.group(1))).strip()
        title = re.sub(r"\s*-\s*[A-Z]{2}\d+\s*$", "", title)
        body = block.split("</span>", 1)[1].split("<td width=\"70\"")[0]
        company = re.search(r"<b>(.*?)</b>", body, re.S)
        lines = [re.sub(r"\s+", " ", x).strip() for x in _text(re.sub(r"<b>.*?</b>", "", body, count=1, flags=re.S)).split("\n")]
        lines = [x for x in lines if x]
        zona = next((x.split(":", 1)[1].strip(" .") for x in lines if x.lower().lstrip("- ").startswith("zona de trabajo")), "")
        jobs.append({
            "title": title,
            "company": re.sub(r"^Para\s+", "", _text(company.group(1)).strip()) if company else "",
            "location": zona,
            "description": "\n".join(lines),
            "posted": None,
            "source": "AMIA",
            "url": f"{BASE}/Autoconsulta/Ofertas/Default.asp?pBNodoId={ident.group(1)}&pbId={ident.group(2)}",
        })
    return jobs


def fetch(conf, pause=1.0):
    """conf = {"enabled", "zonas"}. Devuelve (ofertas, informe)."""
    zonas = [norm(z) for z in conf.get("zonas", []) if z and norm(z) != "remoto"]
    try:
        req = urllib.request.Request(LISTA, headers=page_headers(BASE + "/"))
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read(2_000_000).decode(r.headers.get_content_charset() or "latin-1", "replace")
    except Exception as e:
        return [], [{"busqueda": "AMIA", "encontradas": 0, "nota": f"No se pudo leer: {explain(e)}"}]
    todas = parse_page(html)
    jobs = [j for j in todas if not zonas or any(z in norm(j["location"] + " " + j["title"]) for z in zonas + list(_SIEMPRE))]
    return jobs, [{"busqueda": "últimas ofertas", "encontradas": len(jobs), "nota": ""}]
