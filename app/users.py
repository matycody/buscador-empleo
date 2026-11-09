"""Cuentas: registro, ingreso y sesiones. Cada cuenta tiene su propia carpeta de datos."""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
import time

from . import config, ctx

ROOT = ctx.ROOT_DATA
USERS_PATH = os.path.join(ROOT, "users.json")
SESSIONS_PATH = os.path.join(ROOT, "sessions.json")
TOKENS_PATH = os.path.join(ROOT, "tokens.json")
USERS_DIR = os.path.join(ROOT, "users")
SESSION_DAYS = 30
ITERATIONS = 200_000
LEGACY = ("config.json", "jobs.db", "state.json", "secrets.json", "cvs")

_lock = threading.RLock()
_fails = {}  # email -> [intentos fallidos recientes]


class AuthError(Exception):
    pass


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(ROOT, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS).hex()


def _norm_email(email):
    return str(email or "").strip().lower()


def _public(u):
    return {"id": u["id"], "email": u["email"], "nombre": u.get("nombre", ""), "created": u.get("created")}


def user_dir(uid):
    return os.path.join(USERS_DIR, uid)


def all_dirs():
    return [user_dir(u["id"]) for u in _read(USERS_PATH, [])]


def has_users():
    return bool(_read(USERS_PATH, []))


def register(email, password, nombre="", verificar=False, legal=""):
    email = _norm_email(email)
    nombre = str(nombre or "").strip()[:80]
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 120:
        raise AuthError("Escribí un correo válido.")
    if len(password or "") < 8:
        raise AuthError("La contraseña debe tener al menos 8 caracteres.")
    if len(password) > 200:
        raise AuthError("La contraseña es demasiado larga.")
    with _lock:
        users = _read(USERS_PATH, [])
        if any(u["email"] == email for u in users):
            raise AuthError("Ya hay una cuenta con ese correo. Ingresá o usá otro.")
        salt = secrets.token_hex(16)
        user = {"id": secrets.token_hex(6), "email": email, "nombre": nombre, "salt": salt,
                "hash": _hash(password, salt), "created": time.strftime("%Y-%m-%d"),
                "legal": {"version": legal, "fecha": time.strftime("%Y-%m-%d %H:%M")}}
        if verificar:
            user["verified"] = False  # sin la clave, las cuentas viejas cuentan como verificadas
        folder = user_dir(user["id"])
        os.makedirs(folder, exist_ok=True)
        if not users:  # la primera cuenta se queda con los datos que ya había (versión sin cuentas)
            for name in LEGACY:
                src = os.path.join(ROOT, name)
                if os.path.exists(src):
                    shutil.move(src, os.path.join(folder, name))
        with ctx.using(folder):
            cfg = config.load()
            if not cfg.get("perfil"):
                cfg["perfil"] = {"nombre": nombre, "email": email}
                config.save(cfg)
        users.append(user)
        _write(USERS_PATH, users)
    return _public(user)


def authenticate(email, password):
    email = _norm_email(email)
    with _lock:
        now = time.time()
        recent = [t for t in _fails.get(email, []) if now - t < 600]
        _fails[email] = recent
        if len(recent) >= 5:
            raise AuthError("Demasiados intentos. Esperá unos minutos y probá de nuevo.")
        user = next((u for u in _read(USERS_PATH, []) if u["email"] == email), None)
        # se calcula el hash aunque no exista la cuenta, para que no se note la diferencia
        salt = user["salt"] if user else "00" * 16
        ok = hmac.compare_digest(_hash(password or "", salt), user["hash"] if user else "x")
        if not user or not ok:
            _fails[email].append(now)
            raise AuthError("Correo o contraseña incorrectos.")
        _fails.pop(email, None)
        if user.get("verified") is False:
            raise AuthError("Confirmá tu correo: te mandamos un link. Si no te llegó, pedí uno nuevo abajo.")
        return _public(user)


def _sid(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(uid):
    token = secrets.token_urlsafe(32)
    with _lock:
        sess = {k: v for k, v in _read(SESSIONS_PATH, {}).items() if v["exp"] > time.time()}
        sess[_sid(token)] = {"uid": uid, "exp": time.time() + SESSION_DAYS * 86400}
        _write(SESSIONS_PATH, sess)
    return token


def user_for(token):
    if not token:
        return None
    s = _read(SESSIONS_PATH, {}).get(_sid(token))
    if not s or s["exp"] < time.time():
        return None
    u = next((u for u in _read(USERS_PATH, []) if u["id"] == s["uid"]), None)
    return _public(u) if u else None


def end_session(token):
    with _lock:
        sess = _read(SESSIONS_PATH, {})
        if sess.pop(_sid(token or ""), None) is not None:
            _write(SESSIONS_PATH, sess)


def _drop_sessions(uid, keep=None):
    sess = _read(SESSIONS_PATH, {})
    sess = {k: v for k, v in sess.items() if v["uid"] != uid or k == keep}
    _write(SESSIONS_PATH, sess)


def change_password(uid, old, new, token=None):
    if len(new or "") < 8:
        raise AuthError("La contraseña nueva debe tener al menos 8 caracteres.")
    with _lock:
        users = _read(USERS_PATH, [])
        u = next((x for x in users if x["id"] == uid), None)
        if not u or not hmac.compare_digest(_hash(old or "", u["salt"]), u["hash"]):
            raise AuthError("La contraseña actual no es correcta.")
        u["salt"] = secrets.token_hex(16)
        u["hash"] = _hash(new, u["salt"])
        _write(USERS_PATH, users)
        _drop_sessions(uid, keep=_sid(token) if token else None)  # cierra las demás sesiones


def reset_password(email, new):
    """Para olvidos: `python run.py --reset-password correo nueva` (hace falta acceso a la PC)."""
    if len(new or "") < 8:
        raise AuthError("La contraseña nueva debe tener al menos 8 caracteres.")
    with _lock:
        users = _read(USERS_PATH, [])
        u = next((x for x in users if x["email"] == _norm_email(email)), None)
        if not u:
            raise AuthError("No hay una cuenta con ese correo.")
        u["salt"] = secrets.token_hex(16)
        u["hash"] = _hash(new, u["salt"])
        _write(USERS_PATH, users)
        _drop_sessions(u["id"])


def delete_account(uid, password):
    with _lock:
        users = _read(USERS_PATH, [])
        u = next((x for x in users if x["id"] == uid), None)
        if not u or not hmac.compare_digest(_hash(password or "", u["salt"]), u["hash"]):
            raise AuthError("La contraseña no es correcta.")
        _write(USERS_PATH, [x for x in users if x["id"] != uid])
        _drop_sessions(uid)
        shutil.rmtree(user_dir(uid), ignore_errors=True)


# ---------- links por correo: confirmar correo y recuperar contraseña ----------
def make_token(uid, kind, hours):
    """Crea un link de un solo uso. Se guarda solo el hash, igual que las sesiones."""
    token = secrets.token_urlsafe(32)
    with _lock:
        now = time.time()
        toks = {k: v for k, v in _read(TOKENS_PATH, {}).items() if v["exp"] > now}
        toks = {k: v for k, v in toks.items() if not (v["uid"] == uid and v["kind"] == kind)}  # el nuevo reemplaza al anterior
        toks[_sid(token)] = {"uid": uid, "kind": kind, "exp": now + hours * 3600}
        _write(TOKENS_PATH, toks)
    return token


def _use_token(token, kind):
    with _lock:
        toks = _read(TOKENS_PATH, {})
        t = toks.pop(_sid(token or ""), None)
        if not t or t["kind"] != kind or t["exp"] < time.time():
            raise AuthError("El link venció o ya se usó. Pedí uno nuevo.")
        _write(TOKENS_PATH, toks)
        return t["uid"]


def find_by_email(email):
    u = next((x for x in _read(USERS_PATH, []) if x["email"] == _norm_email(email)), None)
    return dict(u) if u else None


def verify_email(token):
    uid = _use_token(token, "verify")
    with _lock:
        users = _read(USERS_PATH, [])
        for u in users:
            if u["id"] == uid:
                u["verified"] = True
        _write(USERS_PATH, users)


def reset_with_token(token, new):
    if len(new or "") < 8:
        raise AuthError("La contraseña nueva debe tener al menos 8 caracteres.")
    uid = _use_token(token, "reset")
    with _lock:
        users = _read(USERS_PATH, [])
        u = next((x for x in users if x["id"] == uid), None)
        if not u:
            raise AuthError("La cuenta ya no existe.")
        u["salt"] = secrets.token_hex(16)
        u["hash"] = _hash(new, u["salt"])
        if u.get("verified") is False:
            u["verified"] = True  # llegó al link por su correo: queda confirmado
        _write(USERS_PATH, users)
        _drop_sessions(uid)
