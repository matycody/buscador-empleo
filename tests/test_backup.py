import http.server
import json
import os
import re
import sqlite3
import threading
import unittest
import urllib.parse

from tests import base
from app import backup, ctx, users

try:
    import cryptography  # noqa: F401
    HAY_CRYPTO = True
except ImportError:
    HAY_CRYPTO = False


class S3Falso(http.server.BaseHTTPRequestHandler):
    objetos = {}
    pedidos = []
    PAGINA = 2  # páginas chicas para probar la paginación

    def log_message(self, *a):
        pass

    def _clave(self):
        u = urllib.parse.urlparse(self.path)
        partes = urllib.parse.unquote(u.path).lstrip("/").split("/", 1)
        return (partes[1] if len(partes) > 1 else ""), urllib.parse.parse_qs(u.query)

    def _ok(self, cuerpo=b"", code=200):
        self.send_response(code)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _auth(self):
        a = self.headers.get("Authorization", "")
        return bool(re.match(r"AWS4-HMAC-SHA256 Credential=KEYID/\d{8}/auto/s3/aws4_request, SignedHeaders=[\w;-]+, Signature=[0-9a-f]{64}$", a))

    def do_PUT(self):
        if not self._auth():
            return self._ok(code=403)
        n = int(self.headers["Content-Length"])
        k, _ = self._clave()
        S3Falso.objetos[k] = self.rfile.read(n)
        S3Falso.pedidos.append(("PUT", k))
        self._ok()

    def do_DELETE(self):
        k, _ = self._clave()
        S3Falso.objetos.pop(k, None)
        S3Falso.pedidos.append(("DELETE", k))
        self._ok(code=204)

    def do_GET(self):
        if not self._auth():
            return self._ok(code=403)
        k, q = self._clave()
        if k:
            if k not in S3Falso.objetos:
                return self._ok(code=404)
            S3Falso.pedidos.append(("GET", k))
            return self._ok(S3Falso.objetos[k])
        S3Falso.pedidos.append(("LIST", q.get("prefix", [""])[0]))
        prefijo = q.get("prefix", [""])[0]
        claves = sorted(x for x in S3Falso.objetos if x.startswith(prefijo))
        desde = int(q.get("continuation-token", ["0"])[0])
        pag = claves[desde:desde + self.PAGINA]
        mas = desde + self.PAGINA < len(claves)
        xml = '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">' + "".join(f"<Contents><Key>{x}</Key></Contents>" for x in pag)
        xml += f"<IsTruncated>{'true' if mas else 'false'}</IsTruncated>" + (f"<NextContinuationToken>{desde + self.PAGINA}</NextContinuationToken>" if mas else "") + "</ListBucketResult>"
        self._ok(xml.encode())


class Firma(unittest.TestCase):
    def test_vector_oficial_aws_get_vanilla(self):
        # Caso "get-vanilla" de la suite de pruebas de AWS Signature V4
        auth = backup.firmar("GET", "/", {}, {"host": "example.amazonaws.com", "x-amz-date": "20150830T123600Z"},
                             "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                             "AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "us-east-1", service="service")
        self.assertTrue(auth.endswith("Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31"))
        self.assertIn("SignedHeaders=host;x-amz-date", auth)


class Copia(base.TempData):
    def setUp(self):
        super().setUp()
        S3Falso.objetos, S3Falso.pedidos = {}, []
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), S3Falso)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        os.environ.update(BL_BACKUP_ENDPOINT=f"http://127.0.0.1:{self.srv.server_port}", BL_BACKUP_BUCKET="b",
                          BL_BACKUP_KEY_ID="KEYID", BL_BACKUP_SECRET="SECRET", BL_BACKUP_REGION="auto", BL_BACKUP_PREFIX="t")
        backup._vistos.clear()
        backup._conjunto.clear()

    def tearDown(self):
        self.srv.shutdown()
        super().tearDown()

    def _datos(self):
        self.u = users.register("a@mail.com", "claveSegura1", "Ana")
        d = users.user_dir(self.u["id"])
        os.makedirs(os.path.join(d, "cvs"), exist_ok=True)
        with open(os.path.join(d, "cvs", "prog.pdf"), "wb") as f:
            f.write(b"%PDF-mi-cv")
        c = sqlite3.connect(os.path.join(d, "jobs.db"))
        c.execute("CREATE TABLE jobs (id INTEGER, title TEXT)")
        c.execute("INSERT INTO jobs VALUES (1, 'Electricista')")
        c.commit()
        c.close()
        os.makedirs(os.path.join(self.tmp, "cache"), exist_ok=True)
        with open(os.path.join(self.tmp, "cache", "x.json"), "w") as f:
            f.write("{}")
        return d

    def test_apagado_sin_variables(self):
        for k in ("BL_BACKUP_ENDPOINT",):
            os.environ.pop(k)
        self.assertFalse(backup.enabled())
        self.assertEqual(backup.sincronizar(), 0)

    def test_sube_restaura_y_no_copia_cache(self):
        d = self._datos()
        n = backup.sincronizar()
        self.assertGreaterEqual(n, 3)
        self.assertFalse(any("cache" in k for k in S3Falso.objetos))
        # simula un servidor nuevo, con la carpeta vacía
        import shutil
        shutil.rmtree(self.tmp)
        os.makedirs(self.tmp)
        backup._vistos.clear()
        self.assertGreaterEqual(backup.restaurar(), 3)
        self.assertTrue(users.authenticate("a@mail.com", "claveSegura1"))
        with open(os.path.join(d, "cvs", "prog.pdf"), "rb") as f:
            self.assertEqual(f.read(), b"%PDF-mi-cv")
        c = sqlite3.connect(os.path.join(d, "jobs.db"))
        self.assertEqual(c.execute("SELECT title FROM jobs").fetchone()[0], "Electricista")
        c.close()

    def test_solo_sube_lo_que_cambio(self):
        d = self._datos()
        backup.sincronizar()
        S3Falso.pedidos.clear()
        self.assertEqual(backup.sincronizar(), 0)
        self.assertEqual([p for p in S3Falso.pedidos if p[0] == "PUT"], [])
        with open(os.path.join(d, "cvs", "prog.pdf"), "wb") as f:
            f.write(b"%PDF-nuevo-cv-mas-largo")
        self.assertEqual(backup.sincronizar(), 1)

    def test_borrar_cuenta_borra_la_copia(self):
        d = self._datos()
        backup.sincronizar()
        self.assertTrue(any("cvs/prog.pdf" in k for k in S3Falso.objetos))
        users.delete_account(self.u["id"], "claveSegura1")
        backup.sincronizar()
        self.assertFalse(any("cvs/prog.pdf" in k for k in S3Falso.objetos))

    def test_carpeta_vacia_no_borra_la_copia(self):
        self._datos()
        backup.sincronizar()
        antes = dict(S3Falso.objetos)
        import shutil
        shutil.rmtree(self.tmp)
        os.makedirs(self.tmp)
        backup._conjunto.clear()
        self.assertEqual(backup.sincronizar(), 0)
        self.assertEqual(S3Falso.objetos, antes)

    def test_no_restaura_si_ya_hay_datos(self):
        self._datos()
        backup.sincronizar()
        self.assertEqual(backup.restaurar(), 0)

    def test_fallo_de_red_no_explota(self):
        self._datos()
        self.srv.shutdown()
        self.srv.server_close()
        self.assertEqual(backup.sincronizar(), 0)
        self.assertFalse(backup.estado()["ok"])

    @unittest.skipUnless(HAY_CRYPTO, "falta cryptography")
    def test_cifrada_en_el_bucket(self):
        os.environ["BL_SECRET_KEY"] = "clave-de-prueba"
        d = self._datos()
        backup.sincronizar()
        self.assertTrue(all(k.endswith(".enc") for k in S3Falso.objetos))
        crudo = b"".join(S3Falso.objetos.values())
        self.assertNotIn(b"%PDF-mi-cv", crudo)
        self.assertNotIn(b"a@mail.com", crudo)
        import shutil
        shutil.rmtree(self.tmp)
        os.makedirs(self.tmp)
        self.assertGreaterEqual(backup.restaurar(), 3)
        self.assertTrue(users.authenticate("a@mail.com", "claveSegura1"))
        # con otra clave no se puede leer
        shutil.rmtree(self.tmp)
        os.makedirs(self.tmp)
        os.environ["BL_SECRET_KEY"] = "otra-clave"
        self.assertEqual(backup.restaurar(), 0)
        self.assertFalse(os.path.exists(users.USERS_PATH))


if __name__ == "__main__":
    unittest.main()
