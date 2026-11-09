import copy
import unittest

from tests import base
from app import config, scoring


class Scoring(base.TempData):
    def cfg(self):
        c = copy.deepcopy(config.load())
        return c

    def test_oferta_que_no_nombra_nada_queda_baja(self):
        job = {"title": "Vendedor de seguros", "company": "Z", "location": "Córdoba", "description": "Ventas telefónicas", "posted": None}
        score, _, _ = scoring.score_job(job, self.cfg())
        self.assertLessEqual(score, scoring.NO_MATCH_CAP)

    def test_puntaje_en_rango(self):
        c = self.cfg()
        for title in ("Electricista industrial", "Desarrollador Python", "Cocinero", ""):
            s, cv, per = scoring.score_job({"title": title, "description": "tableros PLC python"}, c)
            self.assertTrue(0 <= s <= 100)
            self.assertIn(cv, per)

    def test_dedupe_ignora_mayusculas_y_acentos(self):
        a = {"title": "Electricista", "company": "Fábrica", "location": "Lanús"}
        b = {"title": "ELECTRICISTA", "company": "fabrica", "location": "lanus"}
        self.assertEqual(scoring.dedupe_key(a), scoring.dedupe_key(b))

    def test_senior_pide_mas_experiencia(self):
        junior = scoring.experience_adjust("electricista", "sin experiencia previa")
        senior = scoring.experience_adjust("electricista senior", "5 años de experiencia")
        self.assertGreater(junior, senior)


if __name__ == "__main__":
    unittest.main()


class SinSaturacion(base.TempData):
    """Las ofertas buenas no pueden quedar todas empatadas en 100."""

    def setUp(self):
        super().setUp()
        self.cfg = copy.deepcopy(config.load())
        self.cfg["locations_ok"] = ["quilmes"]

    def puntaje(self, titulo, desc="", **kw):
        j = {"title": titulo, "description": desc, "location": "Quilmes", "posted": None, "company": "X"}
        j.update(kw)
        return scoring.score_job(j, self.cfg)[0]

    def test_mas_coincidencias_dan_mas_puntaje(self):
        a = self.puntaje("Electricista")
        b = self.puntaje("Electricista industrial de mantenimiento")
        c = self.puntaje("Montador tablerista electricista PLC automatismos", "tableros siemens logo baja tension instalaciones industrial")
        self.assertLess(a, b)
        self.assertLess(b, c)

    def test_tres_palabras_genericas_no_son_excelentes(self):
        self.assertLess(self.puntaje("Electricista industrial mantenimiento"), 75)

    def test_el_tope_exige_todo(self):
        mejor = self.puntaje("Montador tablerista electricista PLC automatismos", "tableros siemens logo baja tension instalaciones industrial mantenimiento")
        self.assertLessEqual(mejor, 100)
        self.assertGreater(mejor, 80)

    def test_antiguedad_resta(self):
        from datetime import datetime, timedelta
        hace = lambda d: (datetime.now() - timedelta(days=d)).strftime("%Y-%m-%dT00:00:00")
        t = "Montador tablerista PLC"
        self.assertGreater(self.puntaje(t, posted=hace(1)), self.puntaje(t, posted=hace(30)))

    def test_el_desglose_suma_el_total(self):
        j = {"title": "Electricista industrial", "description": "mantenimiento", "location": "Quilmes", "posted": None, "company": "X"}
        e = scoring.explain(j, self.cfg)
        self.assertEqual(max(0, min(100, sum(i["points"] for i in e["items"]))), e["total"])
