"""Caché compartida entre cuentas: un mismo puesto en un mismo portal se pide una sola vez y lo comparten todos.

Sin esto, cada cuenta saldría a buscar sola y los portales bloquearían la IP del servidor.
La clave incluye el portal, el país, la zona, el puesto y los ajustes del portal, así que dos cuentas solo comparten
resultados cuando buscarían exactamente lo mismo. Vida útil:
  - BL_CACHE_MINUTOS (por defecto 180 en modo público y 10 en uso local)
  - las consultas que fallaron se recuerdan solo 15 minutos, para no insistirle a un portal que nos bloquea.
"""
import hashlib
import json
import os
import threading
import time

from . import ctx, health

ERROR_MIN = 15
_guard = threading.Lock()
_locks = {}


def _dir(sub=""):
    return os.path.join(ctx.ROOT_DATA, "cache", sub)


def ttl_min():
    try:
        return float(os.environ.get("BL_CACHE_MINUTOS", 180 if os.environ.get("BL_PUBLIC") == "1" else 10))
    except ValueError:
        return 10


def _key(*parts):
    return hashlib.sha1(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _lock_for(key):
    with _guard:
        return _locks.setdefault(key, threading.Lock())


def _load(key, ttl_minutes, sub=""):
    try:
        with open(os.path.join(_dir(sub), key + ".json"), encoding="utf-8") as f:
            e = json.load(f)
    except (OSError, ValueError):
        return None
    limite = ERROR_MIN if e.get("error") else ttl_minutes
    return e if time.time() - e.get("t", 0) < limite * 60 else None


def _save(key, entry, sub=""):
    os.makedirs(_dir(sub), exist_ok=True)
    path = os.path.join(_dir(sub), key + ".json")
    tmp = f"{path}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({**entry, "t": time.time()}, f, ensure_ascii=False)
    os.replace(tmp, path)


def fetch(portal, fn, conf, mode="por_consulta"):
    """Pide (o reutiliza) las ofertas de un portal. Devuelve (ofertas, informe, consultas_reales).

    mode: "por_consulta"  una entrada por cada puesto (lo normal)
          "conjunto"      todos los puestos juntos (el portal los usa todos a la vez)
          "sin_consulta"  el portal no usa los puestos (trae lo último que haya)
    """
    queries = list(conf.get("queries", []))
    base = {k: v for k, v in conf.items() if k not in ("queries", "enabled")}
    units = [[q] for q in queries] if mode == "por_consulta" else [queries if mode == "conjunto" else []]
    jobs, report, reales = [], [], 0
    ttl = ttl_min()
    for unit in units:
        key = _key(portal, base, unit, mode)
        entry = _load(key, ttl)
        desde_cache = entry is not None
        if entry is None:
            with _lock_for(key):
                entry = _load(key, ttl)  # otro hilo pudo haberla llenado mientras esperábamos
                desde_cache = entry is not None
                if entry is None:
                    call = {**conf, "queries": unit} if mode == "por_consulta" else conf
                    try:
                        got, rep = fn(call)
                    except Exception as e:  # un portal roto nunca debe frenar la búsqueda de las demás fuentes
                        got, rep = [], [{"busqueda": ", ".join(unit), "encontradas": 0, "nota": f"Falló: {e}"}]
                    falla = any(r.get("nota") for r in rep) and not got
                    entry = {"jobs": got, "report": rep, "error": falla}
                    _save(key, entry)
                    reales += 1
                    health.record(portal, not falla, len(got), next((r.get("nota") for r in rep if r.get("nota")), ""))
        jobs += entry["jobs"]
        report += [{**r, "cache": desde_cache} for r in entry["report"]]
    return jobs, report, reales


def detalle(url, leer, dias=14):
    """Texto completo de una oferta, compartido entre cuentas. Devuelve (texto, fue_consulta_real)."""
    key = _key("detalle", url)
    e = _load(key, dias * 24 * 60, "detalles")
    if e is not None:
        return e["texto"], False
    texto = leer(url)
    if texto:
        _save(key, {"texto": texto}, "detalles")
    return texto, True


def limpiar():
    """Borra entradas viejas (búsquedas de más de 2 días, detalles de más de 15). Se llama al arrancar y cada tanto."""
    n = 0
    for sub, dias in (("", 2), ("detalles", 15)):
        try:
            for name in os.listdir(_dir(sub)):
                p = os.path.join(_dir(sub), name)
                if os.path.isfile(p) and time.time() - os.path.getmtime(p) > dias * 86400:
                    os.remove(p)
                    n += 1
        except OSError:
            pass
    return n


def stats():
    """Cuántas búsquedas y detalles hay guardados y cuánto pesan."""
    out = {}
    for nombre, sub in (("busquedas", ""), ("detalles", "detalles")):
        d = _dir(sub)
        try:
            files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")]
        except OSError:
            files = []
        out[nombre] = {"archivos": len(files), "kb": round(sum(os.path.getsize(f) for f in files) / 1024)}
    out["ttl_min"] = ttl_min()
    return out
