"""Países donde se puede buscar. Cada uno dice qué portales internacionales funcionan (verificados uno por uno).

- computrabajo: subdominio de Computrabajo (https://<sub>.computrabajo.com)
- navent: sitio del grupo Bumeran en ese país (clave de bumeran.SITES), o None si no hay
Los portales de Argentina (ZonaJobs, BuscoJobs, Portal Empleo, AMIA, Talent) solo se usan con país Argentina.
"""
PAISES = {
    "ar": {"nombre": "Argentina", "computrabajo": "ar", "navent": "bumeran"},
    "mx": {"nombre": "México", "computrabajo": "mx", "navent": "bumeran_mx"},
    "cl": {"nombre": "Chile", "computrabajo": "cl", "navent": "laborum"},
    "pe": {"nombre": "Perú", "computrabajo": "pe", "navent": "bumeran_pe"},
    "ec": {"nombre": "Ecuador", "computrabajo": "ec", "navent": "multitrabajos"},
    "pa": {"nombre": "Panamá", "computrabajo": "pa", "navent": "konzerta"},
    "co": {"nombre": "Colombia", "computrabajo": "co", "navent": None},
    "uy": {"nombre": "Uruguay", "computrabajo": "uy", "navent": None},
    "cr": {"nombre": "Costa Rica", "computrabajo": "cr", "navent": None},
    "do": {"nombre": "República Dominicana", "computrabajo": "do", "navent": None},
    "gt": {"nombre": "Guatemala", "computrabajo": "gt", "navent": None},
    "bo": {"nombre": "Bolivia", "computrabajo": "bo", "navent": None},
    "py": {"nombre": "Paraguay", "computrabajo": "py", "navent": None},
}


def get(code):
    return PAISES.get(code) or PAISES["ar"]
