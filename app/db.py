"""SQLite: ofertas agrupadas (un registro por oferta, varias fuentes)."""
import json
import os
import sqlite3
from datetime import datetime, timezone

from . import config, ctx
from .scoring import dedupe_key, score_job

def conn():
    os.makedirs(ctx.data_dir(), exist_ok=True)
    c = sqlite3.connect(os.path.join(ctx.data_dir(), "jobs.db"))
    c.row_factory = sqlite3.Row
    c.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            title TEXT, company TEXT, location TEXT, description TEXT,
            posted TEXT, sources TEXT DEFAULT '[]',
            score INTEGER DEFAULT 0, cv TEXT, cv_scores TEXT DEFAULT '{}',
            status TEXT DEFAULT 'nueva', notes TEXT DEFAULT '',
            created TEXT
        )"""
    )
    cols = [r[1] for r in c.execute("PRAGMA table_info(jobs)")]
    if "applied_at" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN applied_at TEXT")
        # las ya marcadas como aplicadas cuentan desde hoy
        c.execute("UPDATE jobs SET applied_at=? WHERE status='aplicada'", (datetime.now(timezone.utc).isoformat(),))
        c.commit()
    for col in ("outcome", "followup_at"):
        if col not in cols:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT DEFAULT ''")
            c.commit()
    return c


def upsert_jobs(jobs):
    """Inserta ofertas; si ya existe (mismo título+empresa+lugar) suma la fuente."""
    cfg = config.load()
    added = merged = 0
    with conn() as c:
        for j in jobs:
            key = dedupe_key(j)
            src = {"name": j.get("source", "manual"), "url": j.get("url", "")}
            row = c.execute("SELECT id, sources FROM jobs WHERE key=?", (key,)).fetchone()
            if row:
                srcs = json.loads(row["sources"])
                if not any(s["name"] == src["name"] and s["url"] == src["url"] for s in srcs):
                    srcs.append(src)
                    c.execute("UPDATE jobs SET sources=? WHERE id=?", (json.dumps(srcs), row["id"]))
                    merged += 1
                continue
            score, cv, per_cv = score_job(j, cfg)
            c.execute(
                """INSERT INTO jobs (key,title,company,location,description,posted,sources,score,cv,cv_scores,created)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (key, j.get("title", ""), j.get("company", ""), j.get("location", ""),
                 j.get("description", ""), j.get("posted"), json.dumps([src]),
                 score, cv, json.dumps(per_cv), datetime.now(timezone.utc).isoformat()),
            )
            added += 1
    return {"agregadas": added, "fuentes_nuevas_en_existentes": merged}


def pending_descriptions(source, min_score=40, limit=25):
    """Ofertas de un portal con descripción corta (solo título) y puntaje prometedor, mejores primero."""
    out = []
    with conn() as c:
        for r in c.execute(
            "SELECT id, sources FROM jobs WHERE score>=? AND length(description)<200 AND status!='descartada' "
            "ORDER BY score DESC, created DESC", (min_score,)).fetchall():
            for src in json.loads(r["sources"]):
                if src["name"] == source and src.get("url"):
                    out.append({"id": r["id"], "url": src["url"]})
                    break
            if len(out) >= limit:
                break
    return out


def set_description(job_id, text):
    """Guarda la descripción completa y recalcula el puntaje de esa oferta."""
    cfg = config.load()
    with conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not r:
            return
        j = dict(r)
        j["description"] = text
        score, cv, per = score_job(j, cfg)
        c.execute("UPDATE jobs SET description=?, score=?, cv=?, cv_scores=? WHERE id=?",
                  (text, score, cv, json.dumps(per), job_id))


def recalc():
    cfg = config.load()
    n = 0
    with conn() as c:
        for r in c.execute("SELECT * FROM jobs").fetchall():
            s, cv, per = score_job(dict(r), cfg)
            c.execute("UPDATE jobs SET score=?, cv=?, cv_scores=? WHERE id=?", (s, cv, json.dumps(per), r["id"]))
            n += 1
    return {"recalculadas": n}


def list_jobs(q="", cv="", status="", min_score=0, location=""):
    sql, args = "SELECT * FROM jobs WHERE score>=?", [min_score]
    if q:
        sql += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"
        args += [f"%{q}%"] * 3
    if cv:
        sql += " AND cv=?"
        args.append(cv)
    if status:
        sql += " AND status=?"
        args.append(status)
    if location:
        sql += " AND location LIKE ?"
        args.append(f"%{location}%")
    sql += " ORDER BY score DESC, created DESC LIMIT 500"
    with conn() as c:
        out = []
        for r in c.execute(sql, args).fetchall():
            d = dict(r)
            d["sources"] = json.loads(d["sources"])
            d["cv_scores"] = json.loads(d["cv_scores"])
            d.pop("key", None)
            out.append(d)
        return out


def get_job(job_id):
    with conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(r) if r else None


OUTCOMES = ("", "respondieron", "entrevista", "oferta", "rechazada")


def update_job(job_id, status=None, notes=None, outcome=None, followup=None):
    with conn() as c:
        if status is not None:
            c.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
            if status == "aplicada":
                c.execute("UPDATE jobs SET applied_at=? WHERE id=? AND applied_at IS NULL",
                          (datetime.now(timezone.utc).isoformat(), job_id))
            else:
                c.execute("UPDATE jobs SET applied_at=NULL WHERE id=?", (job_id,))
        if notes is not None:
            c.execute("UPDATE jobs SET notes=? WHERE id=?", (notes, job_id))
        if outcome is not None and outcome in OUTCOMES:
            c.execute("UPDATE jobs SET outcome=? WHERE id=?", (outcome, job_id))
        if followup:
            c.execute("UPDATE jobs SET followup_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), job_id))
    return {"ok": True}


EXPORT_COLUMNS = [
    ("Puesto", "title"), ("Empresa", "company"), ("Lugar", "location"), ("Puntaje", "score"),
    ("CV usado", "cv"), ("Estado", "status"), ("Fecha de postulación", "applied_at"), ("Resultado", "outcome"), ("Último seguimiento", "followup_at"),
    ("Publicada", "posted"), ("Portales", "portales"), ("Link", "link"), ("Notas", "notes"),
]


def export_csv(status="aplicada"):
    """CSV (separado por ; para el Excel en español) con las ofertas de un estado."""
    import csv
    import io
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\r\n")
    w.writerow([h for h, _ in EXPORT_COLUMNS])
    for j in list_jobs(status=status):
        j["portales"] = ", ".join(s["name"] for s in j["sources"])
        j["link"] = next((s["url"] for s in j["sources"] if s.get("url")), "")
        for k in ("applied_at", "posted"):
            j[k] = (j.get(k) or "")[:10]
        w.writerow([str(j.get(k, "") or "").replace("\n", " ") for _, k in EXPORT_COLUMNS])
    return out.getvalue()


def clear():
    with conn() as c:
        c.execute("DELETE FROM jobs")
    return {"ok": True}


def clean_descriptions():
    """Limpia descripciones de Computrabajo guardadas antes con el texto de la interfaz del portal."""
    from .sources.computrabajo import clean_description
    n = 0
    with conn() as c:
        for r in c.execute("SELECT id, description FROM jobs WHERE description LIKE '%Gracias por ayudarnos%' OR description LIKE '%Aptitudes asociadas%'").fetchall():
            new = clean_description(r["description"])
            if new != r["description"]:
                c.execute("UPDATE jobs SET description=? WHERE id=?", (new, r["id"]))
                n += 1
    return n
