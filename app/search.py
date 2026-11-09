"""Ejecuta una búsqueda completa en todas las fuentes activas."""
import json
import os
import threading
import time

from . import config, countries, ctx, db
from .sources import amia, bumeran, buscojobs, companies, computrabajo, gmail, jooble, linkedin, portalempleo, remoto, rss, talent, zonajobs

_locks = {}
_guard = threading.Lock()


def _lock_for():
    with _guard:
        return _locks.setdefault(ctx.data_dir(), threading.Lock())


def _state_path():
    os.makedirs(ctx.data_dir(), exist_ok=True)
    return os.path.join(ctx.data_dir(), "state.json")


def load_state():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(**kw):
    st = load_state()
    st.update(kw)
    with open(_state_path(), "w", encoding="utf-8") as f:
        json.dump(st, f)


def enrich_computrabajo(conf, pause=1.0):
    """Lee el aviso completo de las ofertas de Computrabajo con buen puntaje y las vuelve a puntuar."""
    if not conf.get("enabled"):
        return {"leidos": 0, "fallos": 0}
    ok = bad = 0
    for item in db.pending_descriptions("Computrabajo", limit=int(conf.get("max_details", 25))):
        try:
            text = computrabajo.fetch_detail(item["url"])
            if text:
                db.set_description(item["id"], text)
                ok += 1
        except Exception:
            bad += 1
            if bad >= 3:  # si falla seguido, mejor frenar que insistir
                break
        time.sleep(pause)
    return {"leidos": ok, "fallos": bad}


_progress = {}


def progress():
    return _progress.setdefault(ctx.data_dir(), {"running": False, "steps": [], "encontradas": 0})


def _step(name, estado):
    for st in progress()["steps"]:
        if st["name"] == name:
            st["estado"] = estado


def run_search():
    """Devuelve el resultado, o None si ya hay otra búsqueda corriendo."""
    lock = _lock_for()
    if not lock.acquire(blocking=False):
        return None
    PROGRESS = progress()
    try:
        cfg = config.load()
        feeds = cfg.get("rss_feeds", [])
        con_url = [e for e in cfg.get("empresas", []) if e.get("url")]
        portales = cfg.get("portales", {})
        busquedas = cfg.get("busquedas") or []
        pais = countries.get((cfg.get("perfil") or {}).get("pais"))
        navent = pais["navent"]
        candidatos = [("Computrabajo", "computrabajo", lambda c: computrabajo.fetch({**c, "pais_sub": pais["computrabajo"]}))]
        if navent:
            candidatos.append((bumeran.SITES[navent]["name"], "bumeran", lambda c: bumeran.fetch(c, site=navent)))
        if pais is countries.PAISES["ar"]:  # portales que solo existen para Argentina
            candidatos += [("ZonaJobs", "zonajobs", zonajobs.fetch), ("BuscoJobs", "buscojobs", buscojobs.fetch), ("Talent", "talent", talent.fetch),
                           ("PortalEmpleo", "portalempleo", portalempleo.fetch), ("AMIA", "amia", amia.fetch)]
        candidatos += [("Jooble", "jooble", jooble.fetch), ("Remoto", "remoto", remoto.fetch), ("LinkedIn", "linkedin", linkedin.fetch)]
        activos = [(name, key, fn) for name, key, fn in candidatos
                   if portales.get(key, {}).get("enabled") and busquedas
                   and (key != "jooble" or config.get_secret("jooble_key", "JOOBLE_API_KEY"))]
        gm = cfg.get("gmail", {})
        gm_pass = config.get_secret("gmail_password", "GMAIL_APP_PASSWORD")
        use_gm = bool(gm.get("enabled") and gm.get("email") and gm_pass)
        if not feeds and not con_url and not activos and not use_gm:
            return {"agregadas": 0, "errores": [], "empresas": [], "portales": [], "gmail": [],
                    "aviso": "No hay fuentes cargadas. Activá un portal, agregá feeds RSS o empresas con link en Configuración."}

        use_emp = bool(feeds or con_url)
        names = [n for n, _, _ in activos] + (["Empresas y feeds"] if use_emp else []) + (["Gmail"] if use_gm else []) + ["Guardando"]
        PROGRESS["steps"] = [{"name": n, "estado": "espera"} for n in names]
        PROGRESS["running"] = True
        PROGRESS["encontradas"] = 0
        _step(names[0], "corriendo")
        jobs, errors, cjobs, report = [], [], [], []
        pjobs, preport = [], []
        for name, key, fn in activos:
            _step(name, "corriendo")
            got, rep = fn({**portales[key], "queries": busquedas, "zonas": (cfg.get("perfil") or {}).get("zonas") or []})
            pjobs += got
            PROGRESS["encontradas"] += len(got)
            preport += [{**r, "portal": name} for r in rep]
            _step(name, "listo" if got or not any(r.get("nota") for r in rep) else "falló")
        if use_emp:
            _step("Empresas y feeds", "corriendo")
            jobs, errors = rss.fetch(feeds) if feeds else ([], [])
            cjobs, report = companies.fetch(cfg)
            PROGRESS["encontradas"] += len(jobs) + len(cjobs)
            _step("Empresas y feeds", "listo")
        gjobs, greport = [], []
        if use_gm:
            _step("Gmail", "corriendo")
            try:
                gjobs, greport = gmail.fetch(gm, gm_pass)
                PROGRESS["encontradas"] += len(gjobs)
                _step("Gmail", "listo")
            except Exception as e:
                greport = [{"correo": "", "encontradas": 0, "nota": f"No se pudo leer Gmail: {e}"}]
                _step("Gmail", "falló")
        _step("Guardando", "corriendo")
        res = db.upsert_jobs(jobs + cjobs + pjobs + gjobs)
        res["detalles"] = enrich_computrabajo({**portales.get("computrabajo", {}), "queries": busquedas})
        res.update({"errores": errors, "empresas": report, "portales": preport, "gmail": greport})
        _save_state(last_search=time.time(), last_added=res["agregadas"])
        _step("Guardando", "listo")
        return res
    finally:
        PROGRESS["running"] = False
        lock.release()


def scheduler_loop(stop):
    """Cada minuto mira, cuenta por cuenta, si toca buscar según Configuración → Búsqueda automática."""
    from . import users
    while not stop.wait(60):
        for folder in users.all_dirs():
            try:
                with ctx.using(folder):
                    auto = config.load().get("auto", {})
                    if not auto.get("enabled"):
                        continue
                    every = max(1, float(auto.get("every_hours", 6))) * 3600
                    if time.time() - load_state().get("last_search", 0) >= every:
                        run_search()
            except Exception as e:  # el planificador nunca debe caerse
                print("Búsqueda automática falló:", e)
