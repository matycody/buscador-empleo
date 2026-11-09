"""Copia de seguridad automática de la carpeta de datos a un almacenamiento compatible con S3 (Cloudflare R2, Backblaze B2, etc.).

Sirve para hostings sin disco persistente: el servidor guarda una copia cada pocos minutos, hace una última al recibir la
señal de apagado y, si arranca con la carpeta vacía, restaura todo desde la copia.

Se activa con estas variables (si falta alguna, queda apagado):
  BL_BACKUP_ENDPOINT   ej: https://<cuenta>.r2.cloudflarestorage.com
  BL_BACKUP_BUCKET     nombre del bucket (privado)
  BL_BACKUP_KEY_ID / BL_BACKUP_SECRET   claves de acceso
Opcionales: BL_BACKUP_REGION (por defecto "auto", que sirve para R2; con Backblaze B2 hay que poner la región del endpoint, ej. us-west-004), BL_BACKUP_PREFIX (por defecto "buscador"), BL_BACKUP_MINUTOS (por defecto 2).

Si hay BL_SECRET_KEY, cada archivo se cifra antes de subirlo (el bucket nunca ve datos en claro). Sin esa variable se sube tal cual.
No se copian la caché de búsquedas ni las estadísticas de portales (se vuelven a armar solas).
"""
import base64
import datetime
import hashlib
import hmac
import os
import re
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree

from . import ctx, health

ENC = ".enc"
_lock = threading.Lock()
_estado = {"ultima": 0, "ok": None, "archivos": 0, "error": "", "restaurado": 0}
_vistos = {}  # ruta relativa -> (mtime, tamaño) de lo que ya está subido
_conjunto = set()  # archivos que había en la última pasada (para avisar solo cuando algo se agrega o se borra)


# ---------- configuración ----------
def _cfg():
    e = os.environ
    campos = ("BL_BACKUP_ENDPOINT", "BL_BACKUP_BUCKET", "BL_BACKUP_KEY_ID", "BL_BACKUP_SECRET")
    if not all(e.get(c) for c in campos):
        return None
    return {
        "endpoint": e["BL_BACKUP_ENDPOINT"].rstrip("/"), "bucket": e["BL_BACKUP_BUCKET"],
        "key_id": e["BL_BACKUP_KEY_ID"], "secret": e["BL_BACKUP_SECRET"],
        "region": e.get("BL_BACKUP_REGION", "auto"), "prefix": e.get("BL_BACKUP_PREFIX", "buscador").strip("/"),
    }


def enabled():
    return _cfg() is not None


def minutos():
    try:
        return max(1.0, float(os.environ.get("BL_BACKUP_MINUTOS", 2)))
    except ValueError:
        return 2.0


# ---------- firma AWS Signature V4 ----------
def _hm(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def firmar(method, path, query, headers, payload_hash, key_id, secret, region, service="s3"):
    """Devuelve el valor del encabezado Authorization. `headers` ya incluye host y x-amz-date."""
    amz = headers["x-amz-date"]
    fecha = amz[:8]
    quote = lambda s: urllib.parse.quote(s, safe="-_.~")
    canon_q = "&".join(f"{quote(k)}={quote(v)}" for k, v in sorted(query.items()))
    hs = sorted((k.lower(), " ".join(str(v).split())) for k, v in headers.items())
    canon_h = "".join(f"{k}:{v}\n" for k, v in hs)
    firmados = ";".join(k for k, _ in hs)
    canon = "\n".join([method, urllib.parse.quote(path, safe="/-_.~"), canon_q, canon_h, firmados, payload_hash])
    alcance = f"{fecha}/{region}/{service}/aws4_request"
    a_firmar = "\n".join(["AWS4-HMAC-SHA256", amz, alcance, hashlib.sha256(canon.encode()).hexdigest()])
    k = _hm(_hm(_hm(_hm(("AWS4" + secret).encode(), fecha), region), service), "aws4_request")
    firma = hmac.new(k, a_firmar.encode(), hashlib.sha256).hexdigest()
    return f"AWS4-HMAC-SHA256 Credential={key_id}/{alcance}, SignedHeaders={firmados}, Signature={firma}"


def _pedir(c, method, key="", query=None, body=b"", timeout=60):
    query = query or {}
    path = f"/{c['bucket']}" + (f"/{key}" if key else "")
    url = c["endpoint"] + urllib.parse.quote(path, safe="/-_.~")
    if query:
        url += "?" + "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}" for k, v in sorted(query.items()))
    host = urllib.parse.urlparse(c["endpoint"]).netloc
    ph = hashlib.sha256(body).hexdigest()
    h = {"host": host, "x-amz-date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "x-amz-content-sha256": ph}
    h["Authorization"] = firmar(method, path, query, {k: v for k, v in h.items()}, ph, c["key_id"], c["secret"], c["region"])
    req = urllib.request.Request(url, data=body if method in ("PUT", "POST") else None, method=method,
                                 headers={k: v for k, v in h.items() if k != "host"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------- cifrado ----------
def _fernet():
    master = os.environ.get("BL_SECRET_KEY", "")
    if not master:
        return None
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hmac.new(master.encode(), b"bl-backup", hashlib.sha256).digest()))


# ---------- qué se copia ----------
def _archivos():
    """{ruta relativa (con /): ruta absoluta} de todo lo que hay que respaldar."""
    raiz = ctx.ROOT_DATA
    out = {}
    for base, dirs, files in os.walk(raiz):
        dirs[:] = [d for d in dirs if not (base == raiz and d == "cache")]
        for f in files:
            if f.endswith((".tmp", "-journal", "-wal", "-shm")) or (base == raiz and f == "health.json"):
                continue  # health.json se reescribe con cada copia: se rearma solo y no vale la pena subirlo
            ab = os.path.join(base, f)
            out[os.path.relpath(ab, raiz).replace(os.sep, "/")] = ab
    return out


def _leer(ab):
    """Contenido listo para subir. Las bases SQLite se copian con la API de SQLite (consistente aunque estén en uso)."""
    if ab.endswith(".db"):
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            src = sqlite3.connect(ab)
            dst = sqlite3.connect(tmp)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            with open(tmp, "rb") as f:
                return f.read()
        finally:
            os.unlink(tmp)
    with open(ab, "rb") as f:
        return f.read()


def _listar(c):
    """Claves que hay en el bucket bajo el prefijo (con paginación)."""
    claves, token = [], None
    while True:
        q = {"list-type": "2", "prefix": c["prefix"] + "/"}
        if token:
            q["continuation-token"] = token
        raiz = ElementTree.fromstring(_pedir(c, "GET", query=q))
        ns = re.match(r"\{.*\}", raiz.tag)
        ns = ns.group(0) if ns else ""
        claves += [k.text for k in raiz.iter(ns + "Key")]
        trunc = raiz.find(ns + "IsTruncated")
        if trunc is not None and trunc.text == "true":
            token = raiz.find(ns + "NextContinuationToken").text
        else:
            return claves


# ---------- copiar y restaurar ----------
def sincronizar(forzar=False):
    """Sube lo que cambió y borra de la copia lo que ya no existe. Devuelve cuántos archivos subió."""
    c = _cfg()
    if not c:
        return 0
    with _lock:
        subidos, error = 0, ""
        try:
            f = _fernet()
            locales = _archivos()
            if "users.json" not in locales:
                return 0  # carpeta vacía (recién arrancada): no se toca la copia, podría ser lo único que existe
            for rel, ab in locales.items():
                try:
                    st = os.stat(ab)
                except OSError:
                    continue
                marca = (st.st_mtime, st.st_size)
                if not forzar and _vistos.get(rel) == marca:
                    continue
                datos = _leer(ab)
                _pedir(c, "PUT", f"{c['prefix']}/{rel}{ENC if f else ''}", body=f.encrypt(datos) if f else datos)
                _vistos[rel] = marca
                subidos += 1
            if forzar or set(locales) != _conjunto:
                esperadas = {f"{c['prefix']}/{rel}{ENC if f else ''}" for rel in locales}
                for k in _listar(c):
                    if k not in esperadas:
                        _pedir(c, "DELETE", k)  # cuenta o archivo borrado: no debe resucitar al restaurar
                _conjunto.clear()
                _conjunto.update(locales)
        except Exception as e:  # noqa: BLE001 - un fallo de red no debe tumbar el servidor
            error = f"{type(e).__name__}: {e}"[:300]
        _estado.update(ultima=time.time(), ok=not error, error=error, archivos=len(_archivos()))
        health.record("backup", not error, subidos, error)
        return subidos


def restaurar():
    """Si la carpeta de datos está vacía (sin users.json), baja todo desde la copia. Devuelve cuántos archivos restauró."""
    c = _cfg()
    if not c or os.path.exists(os.path.join(ctx.ROOT_DATA, "users.json")):
        return 0
    n = 0
    try:
        f = _fernet()
        prefijo = c["prefix"] + "/"
        claves = _listar(c)
        if not any(k == prefijo + "users.json" + (ENC if f else "") for k in claves):
            return 0  # no hay copia (primer arranque)
        for k in sorted(claves, key=lambda k: k[len(prefijo):].startswith("users.json")):  # users.json al final
            rel = k[len(prefijo):]
            datos = _pedir(c, "GET", k)
            if rel.endswith(ENC):
                if not f:
                    raise RuntimeError("La copia está cifrada y falta BL_SECRET_KEY")
                datos, rel = f.decrypt(datos), rel[:-len(ENC)]
            destino = os.path.normpath(os.path.join(ctx.ROOT_DATA, rel))
            if not destino.startswith(os.path.normpath(ctx.ROOT_DATA) + os.sep):
                continue  # nunca escribir fuera de la carpeta de datos
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino + ".tmp", "wb") as fh:
                fh.write(datos)
            os.replace(destino + ".tmp", destino)
            _vistos[rel] = (os.stat(destino).st_mtime, os.stat(destino).st_size)
            n += 1
    except Exception as e:  # noqa: BLE001
        _estado.update(ok=False, error=f"Al restaurar: {type(e).__name__}: {e}"[:300])
        print("No se pudo restaurar la copia:", e)
        return 0
    _estado["restaurado"] = n
    return n


def loop(stop):
    """Hilo: copia al arrancar y después cada BL_BACKUP_MINUTOS."""
    sincronizar()
    while not stop.wait(minutos() * 60):
        sincronizar()


def cerrar():
    """Última copia completa antes de apagar (la llama el manejador de SIGTERM)."""
    if enabled():
        n = sincronizar(forzar=True)
        print(f"Copia final: {n} archivos")


def estado():
    return {"activo": enabled(), "cada_min": minutos(), "cifrado": bool(os.environ.get("BL_SECRET_KEY")), **_estado}
