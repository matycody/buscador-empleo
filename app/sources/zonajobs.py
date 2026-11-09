"""ZonaJobs Argentina: mismo sistema que Bumeran, con su propio sitio (ver bumeran.py).

Si no tiene puestos/zonas propios, usa los de Bumeran.
"""
from . import bumeran


def fetch(conf, pause=1.0, fallback=None):
    conf = dict(conf or {})
    for k in ("queries", "zonas", "max_pages"):
        if not conf.get(k) and fallback:
            conf[k] = fallback.get(k)
    return bumeran.fetch(conf, pause=pause, site="zonajobs")
