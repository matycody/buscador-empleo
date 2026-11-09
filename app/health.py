"""Estado de cada portal: cuántas veces funcionó o falló, cuándo fue la última vez y qué dijo.

Se actualiza solo con consultas reales (las que sirve la caché no cuentan). Si un portal falla 3 veces seguidas
se avisa por mail a los administradores (BL_ADMIN_EMAILS), como máximo una vez cada 12 horas por portal.
"""
import json
import os
import threading
import time

from . import ctx, mailer

_lock = threading.Lock()
FALLAS_PARA_AVISAR = 3
HORAS_ENTRE_AVISOS = 12


def _path():
    return os.path.join(ctx.ROOT_DATA, "health.json")


def _load():
    try:
        with open(_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def admins():
    return [e.strip().lower() for e in os.environ.get("BL_ADMIN_EMAILS", "").split(",") if e.strip()]


def record(portal, ok, found=0, nota=""):
    """Anota el resultado de una consulta real a `portal`."""
    avisar = None
    with _lock:
        data = _load()
        p = data.setdefault(portal, {"ok": 0, "fail": 0, "seguidas": 0})
        now = time.time()
        if ok:
            p["ok"] += 1
            p["seguidas"] = 0
            p["last_ok"], p["last_found"] = now, found
        else:
            p["fail"] += 1
            p["seguidas"] += 1
            p["last_fail"], p["last_note"] = now, str(nota)[:300]
            if p["seguidas"] >= FALLAS_PARA_AVISAR and now - p.get("alertado", 0) > HORAS_ENTRE_AVISOS * 3600:
                p["alertado"] = now
                avisar = (portal, p["seguidas"], p["last_note"])
        os.makedirs(ctx.ROOT_DATA, exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _path())
    if avisar and admins() and mailer.enabled():
        portal, n, note = avisar
        for to in admins():
            mailer.send(to, f"Portal con fallas: {portal}",
                        f"<p>El portal <b>{portal}</b> falló {n} veces seguidas.</p><p>Último error: {note}</p>"
                        "<p>Puede haber cambiado su página o estar bloqueando el servidor. Revisá el panel de administración.</p>",
                        f"{portal} falló {n} veces seguidas. Último error: {note}")


def snapshot():
    return _load()
