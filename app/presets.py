"""Rubros predefinidos: puestos a buscar y palabras que suman puntaje en cada uno."""

PRESETS = {
    "electricidad": {
        "label": "Electricidad",
        "queries": ["electricista", "ayudante electricista", "tablerista", "mantenimiento electrico", "montador electrico"],
        "keywords": {"electricista": 10, "tablerista": 10, "montador": 8, "plc": 8, "automatismos": 8, "tableros": 8,
                     "mantenimiento": 5, "instalaciones": 5, "baja tension": 6, "industrial": 4, "ayudante": 3, "operario": 2},
    },
    "programacion": {
        "label": "Programación y datos",
        "queries": ["programador", "desarrollador web", "desarrollador python", "analista de datos", "soporte tecnico"],
        "keywords": {"programador": 10, "desarrollador": 10, "developer": 10, "python": 8, "javascript": 7, "sql": 6,
                     "backend": 6, "frontend": 6, "datos": 5, "analista": 5, "junior": 8, "trainee": 8, "qa": 4, "soporte": 3},
    },
    "salud": {
        "label": "Salud",
        "queries": ["enfermero", "auxiliar de enfermeria", "medico", "kinesiologo", "farmaceutico", "cuidador"],
        "keywords": {"enfermero": 10, "enfermera": 10, "medico": 10, "kinesiologo": 9, "farmacia": 7, "cuidador": 8,
                     "paciente": 5, "clinica": 5, "hospital": 5, "sanatorio": 5, "guardia": 4},
    },
    "construccion": {
        "label": "Construcción y oficios",
        "queries": ["carpintero", "plomero", "albañil", "pintor", "soldador", "gasista", "oficial de obra"],
        "keywords": {"carpintero": 10, "plomero": 10, "albañil": 10, "pintor": 9, "soldador": 10, "gasista": 10,
                     "obra": 6, "oficial": 5, "ayudante": 3, "mantenimiento": 4, "herrero": 8, "durlock": 7},
    },
    "administracion": {
        "label": "Administración y contabilidad",
        "queries": ["administrativo", "auxiliar administrativo", "asistente administrativo", "contador", "recepcionista"],
        "keywords": {"administrativo": 10, "administrativa": 10, "contable": 8, "contador": 9, "facturacion": 7,
                     "recepcion": 7, "excel": 5, "tesoreria": 6, "liquidacion": 6, "junior": 5},
    },
    "ventas": {
        "label": "Ventas y atención al cliente",
        "queries": ["vendedor", "atencion al cliente", "cajero", "promotor", "ejecutivo de ventas", "call center"],
        "keywords": {"vendedor": 10, "vendedora": 10, "ventas": 9, "atencion al cliente": 9, "cajero": 8, "cajera": 8,
                     "promotor": 7, "comercial": 7, "telemarketing": 6, "call center": 6, "mostrador": 6},
    },
    "logistica": {
        "label": "Logística y transporte",
        "queries": ["chofer", "repartidor", "operario de deposito", "auxiliar de deposito", "autoelevadorista", "armador de pedidos"],
        "keywords": {"chofer": 10, "repartidor": 9, "deposito": 8, "autoelevadorista": 9, "picking": 7, "stock": 6,
                     "logistica": 8, "operario": 4, "carga": 5, "reparto": 7, "almacen": 6},
    },
    "gastronomia": {
        "label": "Gastronomía y hotelería",
        "queries": ["cocinero", "ayudante de cocina", "mozo", "barista", "bachero", "pastelero"],
        "keywords": {"cocinero": 10, "cocina": 8, "mozo": 10, "moza": 10, "barista": 9, "bachero": 8, "pastelero": 9,
                     "salon": 6, "bar": 5, "restaurante": 6, "hotel": 6},
    },
    "educacion": {
        "label": "Educación",
        "queries": ["docente", "profesor", "maestra", "auxiliar docente", "preceptor", "tutor"],
        "keywords": {"docente": 10, "profesor": 10, "maestra": 10, "maestro": 10, "preceptor": 9, "tutor": 7,
                     "colegio": 5, "escuela": 5, "clases": 6, "ingles": 5},
    },
    "limpieza": {
        "label": "Limpieza y seguridad",
        "queries": ["personal de limpieza", "vigilador", "seguridad", "portero", "encargado de edificio"],
        "keywords": {"limpieza": 10, "vigilador": 10, "seguridad": 8, "portero": 9, "encargado": 6, "sereno": 7, "mantenimiento": 4},
    },
}

GENERIC_TEMPLATE = (
    "Hola, buenos días.\n\nMe postulo para el puesto de {puesto} en {empresa}. "
    "Adjunto mi CV ({cv}). Quedo a disposición para una entrevista.\n\nSaludos,\n{nombre}\n{telefono}"
)


def listing():
    return [{"key": k, "label": p["label"], "queries": p["queries"]} for k, p in PRESETS.items()]


def apply(cfg, rubros, extra=None):
    """Arma `busquedas` y `profiles` según los rubros elegidos. `extra`: puestos sueltos del usuario."""
    queries, profiles, plantillas = [], {}, dict((cfg.get("postulacion") or {}).get("plantillas") or {})
    for key in rubros:
        p = PRESETS.get(key)
        if not p:
            continue
        for q in p["queries"]:
            if q not in queries:
                queries.append(q)
        profiles[key] = {"label": "CV " + p["label"], "keywords": dict(p["keywords"])}
        old = (cfg.get("profiles") or {}).get(key, {}).get("cv_file")
        if old:
            profiles[key]["cv_file"] = old
        plantillas.setdefault(key, GENERIC_TEMPLATE)
    for q in (extra or []):
        q = q.strip()
        if q and q not in queries:
            queries.append(q)
    if extra and not profiles:  # solo puestos propios: un perfil genérico con esas palabras
        profiles["general"] = {"label": "Mi CV", "keywords": {w: 8 for q in queries for w in q.lower().split() if len(w) > 3}}
        plantillas.setdefault("general", GENERIC_TEMPLATE)
    if not profiles:
        return cfg
    cfg["busquedas"] = queries
    cfg["profiles"] = profiles
    cfg.setdefault("postulacion", {})["plantillas"] = plantillas
    cfg["setup_done"] = True
    return cfg


NIVELES = {
    "sin": {"label": "Sin experiencia / primer empleo", "penalize": {"senior": -15, "semi senior": -8, "ssr": -8, "lider": -10, "gerente": -20, "5 años": -12, "3 años": -6}},
    "algo": {"label": "Con algo de experiencia", "penalize": {"senior": -10, "gerente": -20, "lider": -6, "5 años": -8}},
    "mucha": {"label": "Con experiencia", "penalize": {"gerente": -10}},
}


def _lista(v):
    if isinstance(v, str):
        v = v.replace(",", "\n").split("\n")
    return [x.strip() for x in (v or []) if x.strip()]


def apply_perfil(cfg, perfil):
    """Datos personales, zona, nivel y modalidad del registro inicial."""
    perfil = perfil or {}
    keep = {k: str(perfil.get(k, "")).strip() for k in ("nombre", "email", "telefono", "localidad", "nivel", "modalidad")}
    keep["pais"] = str(perfil.get("pais") or "ar").strip().lower()[:2]
    keep["zonas"] = _lista(perfil.get("zonas"))
    cfg["perfil"] = {**(cfg.get("perfil") or {}), **keep}
    post = cfg.setdefault("postulacion", {})
    post["nombre"], post["telefono"] = keep["nombre"], keep["telefono"]
    if keep["email"]:
        cfg.setdefault("gmail", {})["email"] = cfg.get("gmail", {}).get("email") or keep["email"]
    zonas = [z.lower() for z in keep["zonas"]]
    if keep["localidad"]:
        zonas.insert(0, keep["localidad"].lower())
    mod = keep["modalidad"] or "ambos"
    oks = [] if mod == "remoto" else zonas
    if mod in ("remoto", "ambos"):
        oks = oks + ["remoto"]
    if oks:
        cfg["locations_ok"] = list(dict.fromkeys(oks))
        cfg["location"] = zonas[0] if zonas and mod != "remoto" else ""
        for name in ("bumeran", "zonajobs", "buscojobs"):
            if name in cfg.get("portales", {}):
                cfg["portales"][name]["zonas"] = list(dict.fromkeys(zonas + (["remoto"] if mod != "presencial" else [])))
    nivel = NIVELES.get(keep["nivel"])
    if nivel:
        cfg["penalize"] = dict(nivel["penalize"])
    return cfg


EMPRESAS = {
    "electricidad": ["Edesur", "Edenor", "Schneider Electric", "Siemens", "ABB", "Prysmian", "Transener", "Tenaris"],
    "programacion": ["Mercado Libre", "Ualá", "Globant", "Accenture", "Despegar", "Naranja X", "Endava", "Belatrix"],
    "salud": ["Hospital Italiano", "Hospital Alemán", "Swiss Medical", "OSDE", "Galeno", "Sanatorio Otamendi", "Farmacity", "Hospital Británico"],
    "construccion": ["Techint", "Sacde", "Grupo Roggio", "Easy", "Sodimac", "Camuzzi", "Metrogas"],
    "administracion": ["Banco Galicia", "Banco Santander", "BBVA", "Banco Nación", "Telecom", "Deloitte", "PwC", "Arcor"],
    "ventas": ["Coto", "Carrefour", "Jumbo", "Disco", "Frávega", "Musimundo", "Falabella", "Cencosud"],
    "logistica": ["Mercado Libre", "Andreani", "OCA", "Correo Argentino", "DHL", "PedidosYa", "Rappi", "Cruz del Sur"],
    "gastronomia": ["Arcos Dorados", "Alsea", "Mostaza", "Havanna", "Café Martínez", "Burger King", "Hilton", "Sheraton"],
    "educacion": ["Wall Street English", "Universidad Austral", "UADE", "Siglo 21", "ORT Argentina", "Universidad de Belgrano"],
    "limpieza": ["Prosegur", "Brink's", "Securitas", "ISS", "Sodexo", "Compass Group"],
}
AGENCIAS = ["Randstad", "Adecco", "Manpower", "Grupo Gestión"]


def apply_empresas(cfg, rubros):
    """Empresas de interés según los rubros elegidos (se conservan las que el usuario cargó con su link)."""
    nombres = []
    for r in rubros:
        for n in EMPRESAS.get(r, []):
            if n not in nombres:
                nombres.append(n)
    if not nombres:
        return cfg
    nombres += [a for a in AGENCIAS if a not in nombres]
    propias = [e for e in cfg.get("empresas", []) if e.get("url")]
    prop_n = {e["name"].lower() for e in propias}
    cfg["empresas"] = propias + [{"name": n, "url": ""} for n in nombres if n.lower() not in prop_n]
    return cfg
