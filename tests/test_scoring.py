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
