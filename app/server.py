"""Servidor local sin dependencias externas (solo librería estándar)."""
import json
import mimetypes
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config, ctx, cvparse, db, mailer, presets, scoring, search, users
from .sources import demo

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


LEGAL_VERSION = "2026-11"                        # subila cuando cambien los términos o la privacidad
LEGAL_FECHA = "9 de noviembre de 2026"
PUBLIC = os.environ.get("BL_PUBLIC") == "1"      # servidor abierto a internet (detrás de HTTPS)
_REGISTROS = {}                                   # ip -> momentos de registros recientes


def _registro_permitido(ip):
    """Máximo 5 cuentas nuevas por hora desde la misma IP (evita cuentas masivas)."""
    ahora = time.time()
    recientes = [t for t in _REGISTROS.get(ip, []) if ahora - t < 3600]
    if len(recientes) >= 5:
        _REGISTROS[ip] = recientes
        return False
    _REGISTROS[ip] = recientes + [ahora]
    return True


_LIMITES = {}


def _limite(clave, maximo, segundos):
    """True si todavía se puede (máximo `maximo` veces por `segundos` para esa clave)."""
    ahora = time.time()
    recientes = [t for t in _LIMITES.get(clave, []) if ahora - t < segundos]
    ok = len(recientes) < maximo
    _LIMITES[clave] = recientes + ([ahora] if ok else [])
    return ok


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        if PUBLIC:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        super().end_headers()

    def _token(self):
        m = re.search(r"(?:^|;\s*)sid=([\w\-]+)", self.headers.get("Cookie", ""))
        return m.group(1) if m else None

    def _begin(self, public=()):
        """Identifica al usuario de este pedido y apunta los datos a su carpeta. False si falta iniciar sesión."""
        self.user = users.user_for(self._token())
        ctx.set_dir(users.user_dir(self.user["id"]) if self.user else None)
        path = urlparse(self.path).path
        if path.startswith("/api/") and path not in public and not self.user:
            self._json({"error": "Iniciá sesión", "login": True}, 401)
            return False
        return True

    def _base_url(self):
        base = os.environ.get("BL_BASE_URL", "").rstrip("/")
        return base or f"{'https' if PUBLIC else 'http'}://{self.headers.get('Host', 'localhost')}"

    def _enviar_verificacion(self, user):
        token = users.make_token(user["id"], "verify", 48)
        return mailer.send_verify(user["email"], user.get("nombre", ""), f"{self._base_url()}/verify?token={token}")

    def _ip(self):
        """IP real del cliente (detrás de un proxy HTTPS se lee X-Forwarded-For, solo en modo público)."""
        if PUBLIC:
            fwd = self.headers.get("X-Forwarded-For", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return self.client_address[0]

    def _session_cookie(self, token, days=users.SESSION_DAYS):
        age = days * 86400 if token else 0
        return f"sid={token or ''}; HttpOnly; SameSite=Lax; Path=/; Max-Age={age}" + ("; Secure" if PUBLIC else "")

    def _json(self, data, code=200, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        if not self._begin(public=("/api/me", "/verify")):
            return
        if u.path == "/verify":
            try:
                users.verify_email(parse_qs(u.query).get("token", [""])[0])
                destino = "/#verificado"
            except users.AuthError:
                destino = "/#verificado-error"
            self.send_response(302)
            self.send_header("Location", destino)
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if u.path == "/api/me":
            return self._json({"user": self.user, "primera": not users.has_users(), "mail": mailer.enabled()})
        if u.path == "/api/cv":
            prof = re.sub(r"\W", "", parse_qs(u.query).get("profile", [""])[0])
            folder = os.path.join(ctx.data_dir(), "cvs")
            name = next((f for f in (os.listdir(folder) if os.path.isdir(folder) else []) if os.path.splitext(f)[0] == prof), None)
            if not prof or not name:
                return self._json({"error": "No hay CV cargado"}, 404)
            with open(os.path.join(folder, name), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path == "/api/jobs":
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            return self._json(db.list_jobs(
                q=q.get("q", ""), cv=q.get("cv", ""), status=q.get("status", ""),
                min_score=int(q.get("min_score") or 0), location=q.get("location", "")))
        if u.path == "/api/export":
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            status = q.get("status", "aplicada")
            if status not in ("aplicada", "interesa", "descartada", "nueva"):
                status = "aplicada"
            body = db.export_csv(status).encode("utf-8-sig")  # con BOM para que Excel respete los acentos
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="ofertas-{status}.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/api/explain":
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            job = db.get_job(int(q.get("id") or 0))
            if not job:
                return self._json({"items": [], "total": 0}, 404)
            return self._json(scoring.explain(job, config.load()))
        if u.path == "/api/config":
            return self._json(config.load())
        if u.path == "/api/search/progress":
            return self._json(search.progress())
        if u.path == "/api/presets":
            return self._json(presets.listing())
        if u.path == "/api/status":
            st = search.load_state()
            return self._json({"last_search": st.get("last_search"), "last_added": st.get("last_added", 0)})
        if u.path == "/api/jooble/status":
            return self._json({"key_set": bool(config.get_secret("jooble_key", "JOOBLE_API_KEY"))})
        if u.path == "/api/gmail/status":
            return self._json({"password_set": bool(config.get_secret("gmail_password", "GMAIL_APP_PASSWORD"))})
        # archivos estáticos
        rel = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        full = os.path.normpath(os.path.join(STATIC, rel))
        if not full.startswith(STATIC) or not os.path.isfile(full):
            self.send_error(404)
            return
        with open(full, "rb") as f:
            data = f.read()
        if os.path.basename(full) in ("terminos.html", "privacidad.html"):
            from html import escape
            datos = {"{{OPERADOR}}": os.environ.get("BL_OPERADOR", "el responsable de este servicio"),
                     "{{CONTACTO}}": os.environ.get("BL_CONTACTO", "el correo de contacto del servicio"),
                     "{{VERSION}}": LEGAL_VERSION, "{{FECHA}}": LEGAL_FECHA}
            texto = data.decode("utf-8")
            for k, v in datos.items():
                texto = texto.replace(k, escape(v))
            data = texto.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        u = urlparse(self.path)
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self._json({"error": "Pedido no permitido"}, 403)
        body = self._body()
        if not self._begin(public=("/api/register", "/api/login", "/api/logout", "/api/forgot", "/api/resend", "/api/reset")):
            return
        if u.path == "/api/register":
            if body.get("acepto") is not True:
                return self._json({"error": "Para crear la cuenta tenés que aceptar los términos y la política de privacidad."}, 400)
            ip = self._ip()
            if not PUBLIC and ip not in ("127.0.0.1", "::1"):
                return self._json({"error": "Las cuentas nuevas se crean desde la computadora donde corre el programa."}, 403)
            if PUBLIC and not _registro_permitido(ip):
                return self._json({"error": "Demasiados registros desde tu conexión. Probá más tarde."}, 429)
        if u.path in ("/api/register", "/api/login"):
            try:
                if u.path == "/api/register":
                    verificar = mailer.enabled()
                    user = users.register(body.get("email"), body.get("password"), body.get("nombre"), verificar=verificar, legal=LEGAL_VERSION)
                    if verificar:
                        enviado = self._enviar_verificacion(user)
                        return self._json({"verificar": True, "email": user["email"], "enviado": enviado})
                else:
                    user = users.authenticate(body.get("email"), body.get("password"))
            except users.AuthError as e:
                return self._json({"error": str(e)}, 400)
            token = users.new_session(user["id"])
            return self._json({"user": user}, headers={"Set-Cookie": self._session_cookie(token)})
        if u.path in ("/api/forgot", "/api/resend"):
            email = str(body.get("email", "")).strip().lower()
            if not _limite(("mail", self._ip()), 10, 3600) or not _limite(("mail", email), 3, 3600):
                return self._json({"error": "Pediste varios correos seguidos. Probá en un rato."}, 429)
            if not mailer.enabled():
                return self._json({"error": "Este servidor no envía correos. Pedile al administrador que cambie tu contraseña."}, 400)
            found = users.find_by_email(email)
            if found and u.path == "/api/forgot":
                token = users.make_token(found["id"], "reset", 1)
                mailer.send_reset(found["email"], f"{self._base_url()}/#reset={token}")
            elif found and found.get("verified") is False:
                self._enviar_verificacion(found)
            return self._json({"ok": True})  # misma respuesta exista o no la cuenta
        if u.path == "/api/reset":
            try:
                users.reset_with_token(body.get("token"), body.get("password"))
            except users.AuthError as e:
                return self._json({"error": str(e)}, 400)
            return self._json({"ok": True})
        if u.path == "/api/logout":
            users.end_session(self._token())
            return self._json({"ok": True}, headers={"Set-Cookie": self._session_cookie("")})
        if u.path in ("/api/account/password", "/api/account/delete"):
            try:
                if u.path.endswith("password"):
                    users.change_password(self.user["id"], body.get("old"), body.get("new"), self._token())
                    return self._json({"ok": True})
                users.delete_account(self.user["id"], body.get("password"))
                return self._json({"ok": True}, headers={"Set-Cookie": self._session_cookie("")})
            except users.AuthError as e:
                return self._json({"error": str(e)}, 400)
        if u.path == "/api/demo":
            return self._json(db.upsert_jobs(demo.fetch()))
        if u.path == "/api/search":
            res = search.run_search()
            return self._json(res if res is not None else {"agregadas": 0, "aviso": "Ya hay una búsqueda en curso. Esperá a que termine."})
        if u.path in ("/api/jooble/key", "/api/gmail/password"):
            nombre, campo, salida = ("jooble_key", "key", "key_set") if u.path.endswith("key") else ("gmail_password", "password", "password_set")
            try:
                config.set_secret(nombre, "".join(str(body.get(campo, "")).split()))
            except config.SecretError as e:
                return self._json({"error": str(e)}, 400)
            return self._json({salida: bool(config.get_secret(nombre))})
        if u.path == "/api/recalc":
            return self._json(db.recalc())
        if u.path == "/api/clear":
            return self._json(db.clear())
        if u.path == "/api/setup":
            base = config.load()
            had = base.get("setup_done")
            base.pop("setup_done", None)
            cfg = presets.apply(base, body.get("rubros") or [], body.get("extra") or [])
            if not cfg.get("setup_done"):
                if had:
                    cfg["setup_done"] = True  # solo cambió los datos personales
                else:
                    return self._json({"error": "Elegí al menos un rubro o escribí un puesto"}, 400)
            cfg = presets.apply_empresas(cfg, body.get("rubros") or [])
            cfg = presets.apply_perfil(cfg, body.get("perfil"))
            config.save(cfg)
            return self._json(db.recalc())
        if u.path == "/api/cv":
            import base64
            prof = re.sub(r"\W", "", str(body.get("profile", "")))
            ext = os.path.splitext(str(body.get("filename", "")))[1].lower()
            if not prof or ext not in (".pdf", ".doc", ".docx", ".odt", ".txt"):
                return self._json({"error": "Subí un CV en PDF, Word o texto"}, 400)
            try:
                raw = base64.b64decode(body.get("data", ""), validate=False)
            except Exception:
                return self._json({"error": "Archivo ilegible"}, 400)
            if not raw or len(raw) > 5 * 1024 * 1024:
                return self._json({"error": "El CV debe pesar hasta 5 MB"}, 400)
            folder = os.path.join(ctx.data_dir(), "cvs")
            os.makedirs(folder, exist_ok=True)
            for old in os.listdir(folder):  # un solo CV por perfil
                if os.path.splitext(old)[0] == prof:
                    os.remove(os.path.join(folder, old))
            with open(os.path.join(folder, prof + ext), "wb") as f:
                f.write(raw)
            cfg = config.load()
            info = {"ok": True, "leido": False, "agregadas": [], "reforzadas": [], "rubros": []}
            if prof in cfg.get("profiles", {}):
                cfg["profiles"][prof]["cv_file"] = str(body.get("filename"))[:120]
                res = cvparse.analyze(cvparse.extract_text(os.path.join(folder, prof + ext)), cfg["profiles"][prof].get("keywords", {}))
                if res:
                    cfg["profiles"][prof]["keywords"], info["agregadas"], info["reforzadas"], info["rubros"] = res
                    info["leido"] = True
                config.save(cfg)
                if info["leido"]:
                    db.recalc()
            return self._json(info)
        if u.path == "/api/config":
            config.save(body)
            return self._json(db.recalc())
        if u.path == "/api/jobs":  # carga manual de una oferta
            if not body.get("title"):
                return self._json({"error": "Falta el título"}, 400)
            body.setdefault("source", "manual")
            return self._json(db.upsert_jobs([body]))
        m = re.fullmatch(r"/api/jobs/(\d+)", u.path)
        if m:
            return self._json(db.update_job(int(m.group(1)), body.get("status"), body.get("notes"), body.get("outcome"), body.get("followup")))
        self.send_error(404)


def run(host="127.0.0.1", port=8000):
    if PUBLIC and not os.environ.get("BL_SECRET_KEY"):
        print("AVISO: falta BL_SECRET_KEY. Sin ella no se pueden guardar contraseñas de Gmail ni claves de API en modo público.")
    if os.environ.get("BL_SECRET_KEY"):
        try:
            import cryptography  # noqa: F401
        except ImportError:
            raise SystemExit("Hay BL_SECRET_KEY pero falta la biblioteca: ejecutá  pip install -r requirements.txt")
    for folder in users.all_dirs():
        try:
            with ctx.using(folder):
                config.load()
                config.encrypt_existing()
                db.conn().close()
                if db.clean_descriptions():
                    db.recalc()
        except Exception as e:  # la limpieza nunca debe impedir que arranque
            print("No se pudo preparar una cuenta:", e)
    stop = threading.Event()
    threading.Thread(target=search.scheduler_loop, args=(stop,), daemon=True).start()
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"Buscador de empleo listo en http://{host}:{port}  (Ctrl+C para cortar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nChau!")
