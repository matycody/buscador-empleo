"""Puntaje 0-100 y recomendación de CV."""
import re
import unicodedata
from datetime import datetime, timezone


def norm(text):
    text = unicodedata.normalize("NFD", text or "").lower()
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def _profile_score(profile, title, desc):
    kws = profile["keywords"]
    total_possible = sum(kws.values()) or 1
    raw = 0
    for kw, w in kws.items():
        k = norm(kw)
        if k in title:
            raw += w * 2
        elif k in desc:
            raw += w
    # Con ~45% del total posible ya es una coincidencia excelente.
    return min(100.0, raw / (total_possible * 0.45) * 100)


NO_MATCH_CAP = 10


def score_job(job, cfg):
    title = norm(job.get("title"))
    desc = norm(job.get("description"))
    loc = norm(job.get("location"))

    per_cv = {name: _profile_score(p, title, desc) for name, p in cfg["profiles"].items()}
    best_cv = max(per_cv, key=per_cv.get)
    base = per_cv[best_cv]

    pen = 0
    for word, p in cfg.get("penalize", {}).items():
        if norm(word) in title or norm(word) in desc:
            pen += p

    loc_bonus = 0
    oks = [norm(x) for x in cfg.get("locations_ok", [])]
    if any(o and o in loc for o in oks) or "remoto" in loc or "remoto" in desc:
        loc_bonus = 10

    rec_bonus = experience_adjust(title, desc)
    age = _age_points(job.get("posted"))
    if age:
        rec_bonus += age[1]

    comp = norm(job.get("company"))
    comp_bonus = 0
    if comp and any(norm(e.get("name")) and norm(e["name"]) in comp for e in cfg.get("empresas", [])):
        comp_bonus = cfg.get("company_bonus", 10)

    score = max(0, min(100, round(base * 0.82 + loc_bonus + rec_bonus + comp_bonus + pen)))
    if base == 0:  # no nombra nada de lo que buscás: nunca debería verse como buena opción
        score = min(score, NO_MATCH_CAP)
    return score, best_cv, {k: round(v) for k, v in per_cv.items()}


_YEARS = re.compile(r"(\d+)\s*\+?\s*anos?[^.\n]{0,30}experiencia|experiencia[^.\n]{0,40}?(\d+)\s*\+?\s*anos?")
_SENIOR_TITLE = re.compile(r"\b(sr|ssr|sr\.|semi ?sr|senior|semi ?senior|lider|gerente|jefe|coordinador|encargado)\b")
_NO_EXP = ("sin experiencia", "no requiere experiencia", "no es necesaria experiencia", "primer empleo", "primera experiencia")


def experience_breakdown(title, desc):
    """Lista de (motivo, puntos) por experiencia pedida y nivel del puesto."""
    out = []
    if _SENIOR_TITLE.search(title):
        out.append(("Puesto de nivel senior o de mando", -12))
    years = [int(g) for m in _YEARS.finditer(desc) for g in m.groups() if g]
    years = [y for y in years if 1 <= y <= 20]
    if years:
        n = max(years)
        out.append((f"Pide {n} {'año' if n == 1 else 'años'} de experiencia", -3 if n == 1 else -min(24, 6 * n)))
    elif any(k in desc for k in _NO_EXP) or any(k in title for k in _NO_EXP):
        out.append(("Abierto a primera experiencia", 6))
    if re.search(r"\b(trainee|pasante|junior|jr|ayudante|aprendiz|practicante)\b", title):
        out.append(("Puesto de nivel inicial", 4))
    return out


def experience_adjust(title, desc):
    """Penaliza lo que pide años de experiencia y premia lo abierto a primer empleo."""
    return sum(p for _, p in experience_breakdown(title, desc))


def _age_points(posted):
    if not posted:
        return None
    try:
        d = datetime.fromisoformat(posted)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    days = (datetime.now(timezone.utc) - d).days
    pts = 8 if days <= 3 else 4 if days <= 10 else 0 if days <= 21 else -8 if days <= 45 else -15
    return days, pts


def explain(job, cfg):
    """Desglose del puntaje: qué sumó y qué restó. Devuelve {"items": [...], "total": n}."""
    title = norm(job.get("title"))
    desc = norm(job.get("description"))
    loc = norm(job.get("location"))
    score, best_cv, _ = score_job(job, cfg)
    prof = cfg["profiles"][best_cv]
    hits = [k for k in prof["keywords"] if norm(k) in title or norm(k) in desc]
    base = round(_profile_score(prof, title, desc) * 0.82)
    items = []
    if hits:
        items.append({"label": f"Coincide con {prof.get('label', best_cv)}: " + ", ".join(hits[:6]), "points": base})
    else:
        items.append({"label": f"Casi no coincide con las palabras de {prof.get('label', best_cv)}", "points": base})
    oks = [norm(x) for x in cfg.get("locations_ok", [])]
    if any(o and o in loc for o in oks) or "remoto" in loc or "remoto" in desc:
        items.append({"label": "Lugar que te sirve o remoto", "points": 10})
    comp = norm(job.get("company"))
    if comp and any(norm(e.get("name")) and norm(e["name"]) in comp for e in cfg.get("empresas", [])):
        items.append({"label": "Es una de tus empresas de interés", "points": cfg.get("company_bonus", 10)})
    for label, pts in experience_breakdown(title, desc):
        items.append({"label": label, "points": pts})
    age = _age_points(job.get("posted"))
    if age and age[1]:
        days, pts = age
        items.append({"label": "Publicada hace %d días" % days if days > 1 else "Publicada recién", "points": pts})
    for word, p in cfg.get("penalize", {}).items():
        if norm(word) in title or norm(word) in desc:
            items.append({"label": f'Menciona "{word}"', "points": p})
    suma = sum(i["points"] for i in items)
    if score < max(0, min(100, suma)):
        items.append({"label": f"No menciona nada de lo que buscás: el puntaje se limita a {NO_MATCH_CAP}", "points": score - max(0, min(100, suma))})
    return {"items": items, "total": score}


def dedupe_key(job):
    return norm(f"{job.get('title')}|{job.get('company')}|{job.get('location')}")
