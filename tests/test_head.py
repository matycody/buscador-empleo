import http.client
import threading
import unittest
from http.server import ThreadingHTTPServer

from tests import base
from app import server


class Head(base.TempData):
    def test_head_responde_igual_que_get_pero_sin_cuerpo(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            for metodo in ("GET", "HEAD"):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
                c.request(metodo, "/api/me")
                r = c.getresponse()
                cuerpo = r.read()
                self.assertEqual(r.status, 200, metodo)
                if metodo == "HEAD":
                    self.assertEqual(cuerpo, b"")
                    self.assertTrue(int(r.getheader("Content-Length")) > 0)
                c.close()
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
