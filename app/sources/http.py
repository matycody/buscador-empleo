"""Encabezados HTTP comunes: se identifican como un navegador normal de escritorio."""

CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/124.0.0.0 Safari/537.36")


def page_headers(referer=None):
    h = {
        "User-Agent": CHROME_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        h["Referer"] = referer
    return h


def api_headers(origin):
    return {
        "User-Agent": CHROME_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
        "Content-Type": "application/json",
        "Origin": origin,
        "Referer": origin + "/",
    }


def explain(err):
    """Mensaje corto y claro para los errores HTTP más comunes."""
    text = str(err)
    if "403" in text:
        return "el sitio rechazó el pedido (HTTP 403): probablemente bloquea las consultas automáticas desde tu conexión"
    if "429" in text:
        return "demasiados pedidos seguidos (HTTP 429): probá de nuevo más tarde"
    return text
