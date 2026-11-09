"""Alertas de empleo por Gmail (IMAP, solo lectura).

Los portales mandan mails con las ofertas nuevas de tus alertas. Acá se leen los mails
recientes de esos portales y se sacan los links que parecen puestos de trabajo.
No modifica la casilla: abre la carpeta en modo solo lectura y no marca nada como leído.

Requiere una "contraseña de aplicación" de Google (la contraseña normal no sirve).
"""
import email
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from ..scoring import norm
from .companies import _Links

DEFAULT_SENDERS = ["computrabajo", "bumeran", "linkedin", "indeed", "zonajobs", "jooble", "workana", "glassdoor"]
PORTAL_NAMES = {"computrabajo": "Computrabajo", "bumeran": "Bumeran", "linkedin": "LinkedIn", "indeed": "Indeed",
                "zonajobs": "ZonaJobs", "jooble": "Jooble", "workana": "Workana", "glassdoor": "Glassdoor"}

# Textos de botones y pie de mail que no son puestos de trabajo.
NOT_JOBS = ("darse de baja", "desuscrib", "cancelar suscripcion", "ver mas", "ver todas", "ver todos", "ver oferta",
            "ver empleo", "ver trabajo", "ver ofertas", "configur", "politica", "privacidad", "terminos", "ayuda",
            "descarg", "postular", "aplicar", "iniciar sesion", "ingresar", "crear alerta", "editar alerta",
            "administrar", "preferencias", "unsubscribe", "ver en el navegador", "mi cuenta", "ver el correo",
            "mas empleos", "buscar empleo", "contacto", "app store", "google play", "facebook", "instagram", "twitter")


def _header(msg, name):
    try:
        return str(make_header(decode_header(msg.get(name, ""))))
    except Exception:
        return msg.get(name, "") or ""


def _html_body(msg):
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", "replace")
    return ""


AGE_RE = re.compile(r"\s*(?:\(actualizada\))?\s*(?:hace\s+\d+\s+\w+|hoy|ayer)\s*(?:\(actualizada\))?\s*$", re.I)
RATING_RE = re.compile(r"(?<=[^\d\s])\s*(\d\.\d)(?=\s*[A-ZÁÉÍÓÚÑ])")
GLUE_RE = re.compile(r"(?<=[a-záéíóúñ\)])(?=[A-ZÁÉÍÓÚÑ])")


def split_card(text):
    """Los mails de Computrabajo traen todo el aviso pegado en un solo link:
    'Cajeros/as4.4 Randstad ArgentinaRetiro, Capital FederalHace 4 días (actualizada)'.
    Devuelve (puesto, empresa, lugar, antigüedad); lo que no se pueda separar queda vacío."""
    text = " ".join(text.split())
    age = ""
    m = AGE_RE.search(text)
    if m:
        age = m.group(0).replace("(actualizada)", "").strip()
        text = text[:m.start()]
    title, rest = text, ""
    m = RATING_RE.search(text)
    if m:
        title, rest = text[:m.start()].strip(), text[m.end():].strip()
    else:
        g = GLUE_RE.search(text)
        if g and g.start() > 5:
            title, rest = text[:g.start()].strip(), text[g.start():].strip()
    company, location = rest, ""
    if rest:
        cut = None
        for g in GLUE_RE.finditer(rest):  # el último pegado antes de la primera coma
            comma = rest.find(",")
            if comma == -1 or g.start() < comma:
                cut = g.start()
        if cut:
            company, location = rest[:cut].strip(), rest[cut:].strip()
        elif "," in rest:
            company, location = "", rest
    return title, company, location, age


def _age_to_iso(age, fallback):
    m = re.search(r"(\d+)\s*(minuto|hora|d[ií]a|semana|mes)", age or "", re.I)
    base = datetime.now(timezone.utc)
    if m:
        n, u = int(m.group(1)), m.group(2).lower()
        delta = {"minuto": timedelta(minutes=n), "hora": timedelta(hours=n), "semana": timedelta(weeks=n), "mes": timedelta(days=30 * n)}.get(u, timedelta(days=n))
        return (base - delta).isoformat()
    if (age or "").lower() == "ayer":
        return (base - timedelta(days=1)).isoformat()
    return fallback


def parse_message(msg, senders):
    """Devuelve las ofertas que se pueden leer en un mail, o [] si no es de un portal conocido."""
    sender = norm(_header(msg, "From"))
    portal = next((s for s in senders if norm(s) in sender), None)
    if not portal:
        return []
    posted = None
    try:
        posted = parsedate_to_datetime(msg["Date"]).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    parser = _Links()
    parser.feed(_html_body(msg))
    jobs, seen = [], set()
    for text, href in parser.links:
        n = norm(text)
        if not 8 <= len(text) <= 120 or not href.startswith("http") or any(b in n for b in NOT_JOBS):
            continue
        if re.fullmatch(r"[\W\d_]+", text) or text.lower().startswith("http"):
            continue
        title, company, location, age = split_card(text)
        if len(title) < 4:
            title, company, location, age = text, "", "", ""
        key = (norm(title), urlparse(href).path)
        if key in seen:
            continue
        seen.add(key)
        jobs.append({"title": title, "company": company, "location": location,
                     "description": f"Llegó por alerta de {PORTAL_NAMES.get(portal, portal)}.",
                     "posted": _age_to_iso(age, posted), "source": f"Alerta {PORTAL_NAMES.get(portal, portal)}", "url": href})
    return jobs


def fetch(conf, password, timeout=30):
    """Devuelve (ofertas, informe). Lanza una excepción si no puede iniciar sesión."""
    senders = conf.get("senders") or DEFAULT_SENDERS
    since = (datetime.now() - timedelta(days=int(conf.get("days", 7)))).strftime("%d-%b-%Y")
    jobs, report = [], []
    box = imaplib.IMAP4_SSL("imap.gmail.com", timeout=timeout)
    try:
        box.login(conf["email"], password)
        box.select("INBOX", readonly=True)
        status, data = box.search(None, "SINCE", since)
        ids = data[0].split() if status == "OK" and data and data[0] else []
        for num in ids[-200:]:
            status, parts = box.fetch(num, "(BODY.PEEK[])")
            if status != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            msg = email.message_from_bytes(parts[0][1])
            found = parse_message(msg, senders)
            if found:
                jobs += found
                report.append({"correo": _header(msg, "Subject")[:80], "encontradas": len(found)})
    finally:
        try:
            box.logout()
        except Exception:
            pass
    return jobs, report
