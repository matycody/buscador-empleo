import threading
import unittest

from tests import base
from app import cache, health


class Cache(base.TempData):
    def test_segunda_consulta_sale_de_la_cache(self):
        llamadas = []

        def lector(conf):
            llamadas.append(conf["queries"])
            return [{"title": "A", "url": "u"}], [{"busqueda": conf["queries"][0], "encontradas": 1}]

        conf = {"queries": ["electricista"], "zonas": ["x"]}
        j1, _, r1 = cache.fetch("p", lector, conf)
        j2, rep, r2 = cache.fetch("p", lector, dict(conf))
        self.assertEqual((r1, r2, len(llamadas)), (1, 0, 1))
        self.assertEqual(j1, j2)
        self.assertTrue(rep[0]["cache"])

    def test_distinta_configuracion_no_comparte(self):
        n = []
        lector = lambda c: (n.append(1) or [], [{"busqueda": "q", "encontradas": 0}])
        cache.fetch("p", lector, {"queries": ["q"], "zonas": ["a"]})
        cache.fetch("p", lector, {"queries": ["q"], "zonas": ["b"]})
        self.assertEqual(len(n), 2)

    def test_hilos_simultaneos_hacen_una_sola_consulta(self):
        n = []

        def lento(conf):
            import time
            time.sleep(0.2)
            n.append(1)
            return [{"title": "A", "url": "u"}], [{"busqueda": "q", "encontradas": 1}]

        hs = [threading.Thread(target=cache.fetch, args=("p", lento, {"queries": ["q"]})) for _ in range(4)]
        [h.start() for h in hs]
        [h.join() for h in hs]
        self.assertEqual(len(n), 1)

    def test_un_portal_roto_no_frena(self):
        def roto(conf):
            raise RuntimeError("403")
        jobs, rep, _ = cache.fetch("p", roto, {"queries": ["q"]})
        self.assertEqual(jobs, [])
        self.assertIn("Falló", rep[0]["nota"])
        self.assertEqual(health.snapshot()["p"]["seguidas"], 1)

    def test_salud_cuenta_fallas_seguidas(self):
        for _ in range(3):
            health.record("x", False, 0, "boom")
        health.record("x", True, 5)
        self.assertEqual(health.snapshot()["x"]["seguidas"], 0)
        self.assertEqual(health.snapshot()["x"]["fail"], 3)


if __name__ == "__main__":
    unittest.main()
