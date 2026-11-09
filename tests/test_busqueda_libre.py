import unittest
from unittest import mock

from tests import base
from app import ctx, config, search, users


class BusquedaLibre(base.TempData):
    def _cuenta(self):
        u = users.register("a@b.com", "claveSegura1", "A")
        return u

    def test_consulta_libre_busca_solo_ese_puesto_y_no_toca_el_reloj(self):
        u = self._cuenta()
        pedidas = []

        def falso(conf):
            pedidas.append(list(conf["queries"]))
            return [{"title": "Repositor", "company": "X", "url": "http://x/1", "source": "Falso"}], [{"busqueda": conf["queries"][0], "encontradas": 1}]

        with ctx.using(users.user_dir(u["id"])):
            cfg = config.load()
            cfg["busquedas"] = ["electricista"]
            cfg["portales"]["computrabajo"] = {"enabled": True}
            config.save(cfg)
            with mock.patch.object(search.computrabajo, "fetch", falso), mock.patch.object(search, "enrich_computrabajo", lambda c: 0):
                res = search.run_search("repositor")
            self.assertEqual(pedidas, [["repositor"]])
            self.assertEqual(res["agregadas"], 1)
            self.assertFalse(search.load_state().get("last_search"))


if __name__ == "__main__":
    unittest.main()
