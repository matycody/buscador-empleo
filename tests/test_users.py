import os
import unittest

from tests import base
from app import config, ctx, users


class Cuentas(base.TempData):
    def test_registro_login_y_verificacion(self):
        u = users.register("Ana@Mail.com", "claveSegura1", "Ana", verificar=True, legal="2026-11")
        self.assertEqual(u["email"], "ana@mail.com")
        with self.assertRaises(users.AuthError):  # sin verificar no entra
            users.authenticate("ana@mail.com", "claveSegura1")
        token = users.make_token(u["id"], "verify", 48)
        users.verify_email(token)
        self.assertTrue(users.authenticate("ana@mail.com", "claveSegura1"))

    def test_token_de_un_solo_uso_y_tipo(self):
        u = users.register("b@mail.com", "claveSegura1")
        t = users.make_token(u["id"], "reset", 1)
        with self.assertRaises(users.AuthError):
            users.verify_email(t)  # tipo equivocado... y además lo consume
        t2 = users.make_token(u["id"], "reset", 1)
        users.reset_with_token(t2, "otraClave123")
        with self.assertRaises(users.AuthError):
            users.reset_with_token(t2, "otraClave456")  # ya usado
        self.assertTrue(users.authenticate("b@mail.com", "otraClave123"))

    def test_token_vencido(self):
        u = users.register("c@mail.com", "claveSegura1")
        t = users.make_token(u["id"], "reset", -1)
        with self.assertRaises(users.AuthError):
            users.reset_with_token(t, "otraClave123")

    def test_validaciones(self):
        with self.assertRaises(users.AuthError):
            users.register("no-es-mail", "claveSegura1")
        with self.assertRaises(users.AuthError):
            users.register("d@mail.com", "corta")
        users.register("d@mail.com", "claveSegura1")
        with self.assertRaises(users.AuthError):
            users.register("D@mail.com", "claveSegura1")  # repetido

    def test_firma_de_baja(self):
        sig = users.sign("baja", "abc123")
        self.assertTrue(users.check_sign("baja", "abc123", sig))
        self.assertFalse(users.check_sign("baja", "abc123", sig[:-1] + ("0" if sig[-1] != "0" else "1")))
        self.assertFalse(users.check_sign("baja", "otro", sig))
        self.assertFalse(users.check_sign("reset", "abc123", sig))

    def test_stats_sin_datos_personales(self):
        users.register("e@mail.com", "claveSegura1")
        st = users.stats()
        self.assertEqual(st["cuentas"], 1)
        self.assertNotIn("e@mail.com", str(st))


try:
    import cryptography  # noqa: F401
    HAY_CRYPTO = True
except ImportError:
    HAY_CRYPTO = False


@unittest.skipUnless(HAY_CRYPTO, "falta instalar cryptography (pip install -r requirements.txt)")
class Secretos(base.TempData):
    def test_cifrado_ida_y_vuelta(self):
        os.environ["BL_SECRET_KEY"] = "clave-maestra-de-prueba"
        d = os.path.join(self.tmp, "users", "u1")
        os.makedirs(d)
        with ctx.using(d):
            config.set_secret("gmail", "mi-clave-app")
            with open(os.path.join(d, "secrets.json"), encoding="utf-8") as fh:
                crudo = fh.read()
            self.assertNotIn("mi-clave-app", crudo)
            self.assertEqual(config.get_secret("gmail"), "mi-clave-app")

    def test_no_se_lee_con_otra_cuenta_ni_otra_clave(self):
        os.environ["BL_SECRET_KEY"] = "clave-1"
        a, b = (os.path.join(self.tmp, "users", x) for x in ("a", "b"))
        for d in (a, b):
            os.makedirs(d)
        with ctx.using(a):
            config.set_secret("gmail", "secreto")
        os.rename(os.path.join(a, "secrets.json"), os.path.join(b, "secrets.json"))
        with ctx.using(b):
            self.assertEqual(config.get_secret("gmail"), "")
        os.rename(os.path.join(b, "secrets.json"), os.path.join(a, "secrets.json"))
        os.environ["BL_SECRET_KEY"] = "clave-2"
        with ctx.using(a):
            self.assertEqual(config.get_secret("gmail"), "")


class SecretosSinClave(base.TempData):
    def test_modo_publico_sin_clave_no_guarda(self):
        os.environ["BL_PUBLIC"] = "1"
        d = os.path.join(self.tmp, "users", "u")
        os.makedirs(d)
        with ctx.using(d), self.assertRaises(config.SecretError):
            config.set_secret("gmail", "x")


if __name__ == "__main__":
    unittest.main()
