import os
import re
import unittest

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static")


def leer(nombre):
    with open(os.path.join(STATIC, nombre), encoding="utf-8") as f:
        return f.read()


class ModoOscuro(unittest.TestCase):
    def test_todas_las_paginas_cargan_theme_js(self):
        for pagina in ("index.html", "landing.html", "terminos.html", "privacidad.html", "admin.html"):
            self.assertIn('<script src="/theme.js"></script>', leer(pagina), pagina)

    def test_no_hay_scripts_en_linea(self):
        # La CSP solo permite JavaScript propio: un <script> con código dentro quedaría bloqueado
        for pagina in ("index.html", "landing.html", "terminos.html", "privacidad.html", "admin.html"):
            for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.+?)</script>", leer(pagina), re.S):
                self.assertEqual(m.group(1).strip(), "", f"script en línea en {pagina}")

    def test_cada_variable_usada_esta_definida_en_claro_y_oscuro(self):
        css = leer("styles.css")
        claro = css[css.index(":root {"):css.index(':root[data-theme="dark"]')]
        oscuro = css[css.index(':root[data-theme="dark"]'):]
        oscuro = oscuro[:oscuro.index("\n}\n")]
        usadas = set(re.findall(r"var\(--([\w-]+)\)", css))
        definidas = set(re.findall(r"--([\w-]+):", claro))
        self.assertEqual(usadas - definidas - {"h"}, set())  # --h: tono de cada avatar, se define por elemento desde JS
        # lo que cambia de color entre temas tiene que estar en el oscuro (radius y font son iguales en los dos)
        sin_oscuro = {v for v in definidas - {"radius", "font", "elec", "prog"} if f"--{v}:" not in oscuro}
        self.assertEqual(sin_oscuro, set())

    def test_hay_boton_para_cambiar_de_tema(self):
        self.assertIn("data-theme-toggle", leer("index.html"))
        self.assertIn("data-theme-toggle", leer("landing.html"))


if __name__ == "__main__":
    unittest.main()
