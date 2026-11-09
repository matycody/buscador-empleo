"""Fuente genérica: cualquier feed RSS/Atom de empleos (se cargan desde la web)."""
import re
import urllib.request
import xml.etree.ElementTree as ET
from .http import page_headers
from email.utils import parsedate_to_datetime



def _text(el, *names):
    for n in names:
        found = el.find(n)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


def fetch_feed(url, timeout=15):
    req = urllib.request.Request(url, headers=page_headers())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        root = ET.fromstring(r.read())
    ns = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{ns}entry")
    out = []
    for it in items:
        title = _text(it, "title", f"{ns}title")
        link = _text(it, "link", f"{ns}link")
        if not link:
            le = it.find(f"{ns}link")
            link = le.get("href", "") if le is not None else ""
        desc = re.sub(r"<[^>]+>", " ", _text(it, "description", f"{ns}summary", f"{ns}content"))
        posted = None
        raw = _text(it, "pubDate", f"{ns}updated", f"{ns}published")
        if raw:
            try:
                posted = parsedate_to_datetime(raw).isoformat()
            except (TypeError, ValueError):
                posted = raw if re.match(r"\d{4}-\d{2}-\d{2}", raw) else None
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        out.append({"title": title, "company": "", "location": "", "description": desc.strip()[:2000],
                    "posted": posted, "source": host, "url": link})
    return out


def fetch(feeds):
    jobs, errors = [], []
    for url in feeds:
        try:
            jobs += fetch_feed(url)
        except Exception as e:  # red, XML inválido, etc.
            errors.append(f"{url}: {e}")
    return jobs, errors
