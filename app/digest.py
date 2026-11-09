"""Resumen diario por mail con las ofertas nuevas que valen la pena (Configuración → Automático y avisos).

Solo se manda si la persona lo activó, su correo está confirmado y hay al menos una oferta nueva con buen puntaje.
Cada mail trae un link de baja firmado que funciona sin iniciar sesión.
"""
import html
import os
import time
from datetime import datetime, timedelta, timezone

from . import config, ctx, db, mailer, search, users

MAX_OFERTAS = 10


def _base():
    return os.environ.get("BL_BASE_URL", "").rstrip("/")


def _local_hour():
    offset = float(os.environ.get("BL_TZ_OFFSET", -3))  # horas respecto de UTC (Argentina: -3)
    return time.gmtime(time.time() + offset * 3600).tm_hour


def nuevas(desde_iso, min_score):
    return [j for j in db.list_jobs(min_score=min_score, status="nueva") if (j.get("created") or "") > desde_iso][:MAX_OFERTAS]


def _link(j):
    return next((s["url"] for s in j.get("sources", []) if s.get("url")), "")


def render(nombre, ofertas, baja_url, app_url):
    filas = "".join(
        f'<tr><td style="padding:10px 0;border-bottom:1px solid #e3e7ea">'
        f'<a href="{html.escape(_link(j))}" style="color:#15212b;font-weight:bold;text-decoration:none">{html.escape(j["title"])}</a><br>'
        f'<span style="color:#667">{html.escape(j.get("company") or "")} · {html.escape(j.get("location") or "")}</span></td>'
        f'<td style="padding:10px 0 10px 12px;border-bottom:1px solid #e3e7ea;text-align:right;white-space:nowrap">'
        f'<b style="background:#e4f3e8;color:#1e6b34;border-radius:6px;padding:4px 8px">{j["score"]}</b></td></tr>'
        for j in ofertas)
    hola = f"Hola {html.escape(nombre.split()[0])}," if nombre else "Hola,"
    ver = f'<p style="margin:20px 0"><a href="{app_url}" style="background:#15212b;color:#fff;padding:11px 20px;border-radius:8px;text-decoration:none;font-weight:bold">Ver todas mis ofertas</a></p>' if app_url else ""
    pie = f'<p style="font-size:12px;color:#889;margin-top:24px">Recibís este resumen porque lo activaste en tu cuenta. <a href="{baja_url}" style="color:#889">Dejar de recibirlo</a>.</p>' if baja_url else ""
    return (f'<div style="font-family:Arial,sans-serif;max-width:540px;margin:auto;padding:20px;color:#15212b">'
            f'<h2 style="margin:0 0 6px">{len(ofertas)} oferta{"s" if len(ofertas) != 1 else ""} nueva{"s" if len(ofertas) != 1 else ""} para vos</h2>'
            f'<p style="margin:0 0 14px">{hola} estas son las ofertas nuevas que mejor encajan con tu perfil (el número es el puntaje).</p>'
            f'<table style="width:100%;border-collapse:collapse">{filas}</table>{ver}{pie}</div>')


def send_now(force=False):
    """Manda el resumen de la cuenta actual (ctx). Devuelve cuántas ofertas incluyó, o 0 si no mandó nada."""
    cfg = config.load()
    av = cfg.get("avisos") or {}
    if not mailer.enabled() or not (av.get("mail") or force):
        return 0
    uid = os.path.basename(os.path.normpath(ctx.data_dir()))
    user = users.find_by_id(uid)
    if not user or user.get("verified") is False:
        return 0
    st = search.load_state()
    desde = "" if force else (st.get("last_digest_iso") or (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat())
    ofertas = nuevas(desde, int(av.get("puntaje", 80)))
    if not force:  # el correo de prueba no corre la marca del resumen diario
        search._save_state(last_digest=time.time(), last_digest_iso=datetime.now(timezone.utc).isoformat())
    if not ofertas:
        return 0
    base = _base()
    baja = f"{base}/baja?u={uid}&s={users.sign('baja', uid)}" if base else ""
    ok = mailer.send(user["email"], f"{len(ofertas)} oferta{'s' if len(ofertas) != 1 else ''} nueva{'s' if len(ofertas) != 1 else ''} para vos",
                     render(user.get("nombre", ""), ofertas, baja, base + "/" if base else ""),
                     "Ofertas nuevas: " + "; ".join(f"{j['title']} ({j['score']})" for j in ofertas))
    return len(ofertas) if ok else 0


def maybe_send():
    """Lo llama el planificador cada minuto: manda una vez por día, desde BL_DIGEST_HORA (por defecto, las 8)."""
    av = (config.load().get("avisos") or {})
    if not av.get("mail"):
        return 0
    if _local_hour() < int(os.environ.get("BL_DIGEST_HORA", 8)):
        return 0
    if time.time() - search.load_state().get("last_digest", 0) < 20 * 3600:
        return 0
    return send_now()


def unsubscribe(uid):
    """Apaga el resumen de esa cuenta (desde el link de baja del mail)."""
    u = users.find_by_id(uid)
    if not u:
        return False
    with ctx.using(users.user_dir(uid)):
        cfg = config.load()
        cfg.setdefault("avisos", {})["mail"] = False
        config.save(cfg)
    return True
