import unittest

from tests import base  # noqa: F401
from app.sources import amia, portalempleo, remoto

AMIA_HTML = """
<table><tr><td class="ContenidoCopeteListado">
<span class="map-provincias">Tornero CNC - AB123</span>
<b>Para Metalúrgica Sur</b><br>- Zona de trabajo: Lanús.<br>Se requiere secundario técnico.
<a onclick="LoginAlert('77', '9')">Postular</a></td><td width="70"></td></tr>
<tr><td class="ContenidoCopeteListado">
<span class="map-provincias">Electricista - CD456</span>
<b>Para Obras SA</b><br>- Zona de trabajo: Quilmes.<br>Tareas de mantenimiento.
<a onclick="LoginAlert('78', '9')">Postular</a></td><td width="70"></td></tr></table>
"""

PE_HTML = """
<p>Mostrando <strong>2</strong> de <strong>37</strong></p>
<article class="pe-oferta-card-item">
 <a href="/ofertas-laborales/details/abc-1">ver</a>
 <h3 class="pe-oferta-puesto">ELECTRICISTA INDUSTRIAL</h3>
 <span class="pe-oferta-empresa">Fábrica Norte</span>
 <span class="pe-oferta-loc-texto">LA MATANZA</span>
 <p class="pe-oferta-desc">Mantenimiento de tableros.</p>
 <time datetime="2026-11-01">1 nov</time>
 <span class="pe-oferta-badge x">Jornada completa</span>
</article>
<article class="pe-oferta-card-item"><h3 class="pe-oferta-puesto">Sin link</h3></article>
"""


class Amia(unittest.TestCase):
    def test_parsea_dos_filas(self):
        jobs = amia.parse_page(AMIA_HTML)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["title"], "Tornero CNC")  # sin el código final
        self.assertEqual(jobs[0]["company"], "Metalúrgica Sur")
        self.assertEqual(jobs[0]["location"], "Lanús")
        self.assertIn("pBNodoId=77", jobs[0]["url"])
        self.assertEqual(jobs[1]["location"], "Quilmes")

    def test_html_vacio(self):
        self.assertEqual(amia.parse_page("<html></html>"), [])


class PortalEmpleo(unittest.TestCase):
    def test_parsea_y_descarta_sin_link(self):
        jobs = portalempleo.parse_page(PE_HTML)
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["company"], "Fábrica Norte")
        self.assertEqual(j["location"], "La Matanza")
        self.assertTrue(j["posted"].startswith("2026-11-01"))
        self.assertTrue(j["url"].endswith("/details/abc-1"))
        self.assertIn("Jornada completa", j["description"])

    def test_total(self):
        self.assertEqual(portalempleo.total_of(PE_HTML), 37)
        self.assertEqual(portalempleo.total_of(""), 0)


class Remoto(unittest.TestCase):
    def test_remotive(self):
        data = {"jobs": [{"title": "Dev", "company_name": "X", "url": "https://x/1", "description": "<p>Hola <b>mundo</b></p>",
                          "candidate_required_location": "LATAM", "publication_date": "2026-11-02T10:00:00"},
                         {"title": "", "url": "https://x/2"}]}
        jobs = remoto.parse_remotive(data)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["description"], "Hola mundo")
        self.assertEqual(jobs[0]["location"], "Remoto · LATAM")

    def test_arbeitnow(self):
        jobs = remoto.parse_arbeitnow({"data": [{"title": "QA", "url": "https://a/1", "remote": True, "location": "Berlin", "created_at": 1762000000}]})
        self.assertEqual(jobs[0]["location"], "Remoto · Berlin")
        self.assertRegex(jobs[0]["posted"], r"^\d{4}-\d\d-\d\dT")

    def test_jobicy(self):
        jobs = remoto.parse_jobicy({"jobs": [{"jobTitle": "Ops &amp; Data", "companyName": "Y", "url": "https://j/1", "jobGeo": ["Chile", "Peru"], "pubDate": "2026-11-03 09:00:00"}]})
        self.assertEqual(jobs[0]["title"], "Ops & Data")
        self.assertEqual(jobs[0]["location"], "Remoto · Chile, Peru")
        self.assertEqual(jobs[0]["posted"], "2026-11-03T09:00:00")


if __name__ == "__main__":
    unittest.main()
