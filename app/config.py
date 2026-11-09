"""Configuración persistente (data/config.json). Todo se edita desde la web."""
import copy
import json
import os

from . import ctx

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = ctx.ROOT_DATA  # datos globales (cuentas); los de cada usuario están en ctx.data_dir()

DEFAULT = {
    "location": "",
    "busquedas": [],
    "locations_ok": ["capital federal", "caba", "buenos aires", "remoto"],
    "min_score": 0,
    "profiles": {
        "electricidad": {
            "label": "CV Electricidad",
            "keywords": {
                "electricista": 10, "tablerista": 10, "montador": 8, "plc": 8, "logo": 6,
                "automatismos": 8, "siemens": 6, "mantenimiento": 5, "instalaciones": 5,
                "industrial": 4, "baja tension": 6, "media tension": 4, "tableros": 8,
                "ayudante": 3, "operario": 2, "pasante": 3,
            },
        },
        "programacion": {
            "label": "CV Programación",
            "keywords": {
                "programador": 10, "desarrollador": 10, "developer": 10, "python": 8,
                "javascript": 7, "sql": 6, "datos": 5, "data": 5, "analista": 5,
                "junior": 8, "trainee": 8, "pasante": 4, "backend": 6, "frontend": 6,
                "web": 4, "soporte": 3, "qa": 4, "ciencia de datos": 6,
            },
        },
    },
    "penalize": {"senior": -15, "semi senior": -8, "ssr": -8, "lider": -10, "gerente": -20, "5 años": -12, "3 años": -6},
    "empresas": [],
    "company_bonus": 10,
    "auto": {"enabled": False, "every_hours": 6},
    "avisos": {"puntaje": 80, "seguimiento_dias": 7},
    "postulacion": {
        "nombre": "",
        "telefono": "",
        "plantillas": {
            "electricidad": (
                "Hola, buenos días.\n\nMe postulo para el puesto de {puesto} en {empresa}. "
                "Busco mi primera experiencia laboral en el rubro eléctrico y tengo muchas ganas de aprender y sumarme al equipo.\n\n"
                "Adjunto mi CV ({cv}). Quedo a disposición para una entrevista.\n\nSaludos,\n{nombre}\n{telefono}"
            ),
            "programacion": (
                "Hola, buenos días.\n\nMe postulo para el puesto de {puesto} en {empresa}. "
                "Estoy estudiando programación y busco mi primera experiencia laboral para seguir creciendo.\n\n"
                "Adjunto mi CV ({cv}) con mis proyectos. Quedo a disposición para una entrevista.\n\nSaludos,\n{nombre}\n{telefono}"
            ),
        },
    },
    "gmail": {"enabled": False, "email": "", "days": 7,
              "senders": ["computrabajo", "bumeran", "linkedin", "indeed", "zonajobs", "jooble", "workana", "glassdoor"]},
    "portales": {
        "computrabajo": {
            "enabled": True,
            "region": "buenos-aires-gba",
            "max_pages": 2,
            "queries": ["electricista", "ayudante electricista", "tablerista", "mantenimiento electrico",
                        "programador", "desarrollador web", "desarrollador python", "analista de datos", "soporte tecnico"],
        },
        "talent": {
            "enabled": True,
            "location": "Buenos Aires",
            "queries": ["electricista", "tablerista", "mantenimiento electrico",
                        "programador junior", "desarrollador web", "analista de datos"],
        },
        "portalempleo": {"enabled": True, "max_pages": 2},
        "amia": {"enabled": True},
        "remoto": {"enabled": False},
        "linkedin": {
            "enabled": False,
            "max_pages": 1,
            "location": "Buenos Aires, Argentina",
            "queries": ["electricista", "programador junior", "analista de datos"],
        },
        "jooble": {
            "enabled": False,
            "max_pages": 2,
            "location": "Buenos Aires",
            "queries": ["electricista", "tablerista", "mantenimiento electrico",
                        "programador junior", "desarrollador web", "analista de datos"],
        },
        "buscojobs": {
            "enabled": True,
            "max_pages": 2,
            "zonas": ["buenos aires", "capital federal", "caba", "remoto"],
            "queries": ["electricista", "ayudante electricista", "tablerista", "mantenimiento electrico",
                        "programador", "desarrollador web", "analista de datos", "soporte tecnico"],
        },
        "zonajobs": {
            "enabled": True,
            "max_pages": 2,
            "zonas": ["buenos aires", "capital federal", "caba", "remoto"],
            "queries": ["electricista", "ayudante electricista", "tablerista", "mantenimiento electrico",
                        "programador", "desarrollador web", "analista de datos", "soporte tecnico"],
        },
        "bumeran": {
            "enabled": True,
            "max_pages": 2,
            "zonas": ["buenos aires", "capital federal", "caba", "remoto"],
            "queries": ["electricista", "ayudante electricista", "tablerista", "mantenimiento electrico",
                        "programador", "desarrollador web", "desarrollador python", "analista de datos", "soporte tecnico"],
        },
    },
    "rss_feeds": [],
}


def _path(name):
    os.makedirs(ctx.data_dir(), exist_ok=True)
    return os.path.join(ctx.data_dir(), name)


def load():
    path = _path("config.json")
    if not os.path.exists(path):
        save(DEFAULT)
        return copy.deepcopy(DEFAULT)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    migrar = "busquedas" not in cfg
    for k, v in DEFAULT.items():
        cfg.setdefault(k, copy.deepcopy(v))
    for k, v in DEFAULT["portales"].items():  # portales agregados en versiones nuevas
        cfg["portales"].setdefault(k, copy.deepcopy(v))
    if migrar:  # configuraciones viejas: unir los puestos que tenía cada portal
        union = []
        for p in (cfg.get("portales") or {}).values():
            for q in p.get("queries", []):
                if q not in union:
                    union.append(q)
        cfg["busquedas"] = union
        cfg["setup_done"] = True  # quien ya venía usando la app no necesita el asistente
    return cfg


def save(cfg):
    with open(_path("config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class SecretError(Exception):
    pass


PREFIX = "enc:v1:"


def _fernet():
    """Cifrador de esta cuenta, o None si el servidor no tiene BL_SECRET_KEY (uso local: se guarda sin cifrar).

    La clave de cada cuenta sale de BL_SECRET_KEY + el id de la cuenta, así que el archivo de una cuenta
    no sirve para leer el de otra. Si BL_SECRET_KEY cambia o se pierde, los secretos guardados no se pueden leer
    (cada persona tendría que volver a cargarlos)."""
    master = os.environ.get("BL_SECRET_KEY", "")
    if not master:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        raise SecretError("Falta instalar «cryptography» (pip install -r requirements.txt) para cifrar los secretos.") from e
    import base64, hashlib, hmac
    uid = os.path.basename(os.path.normpath(ctx.data_dir()))
    key = hmac.new(master.encode(), b"bl-secrets:" + uid.encode(), hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def cifrado_listo():
    """True si se pueden guardar secretos de forma segura (con clave, o en uso local sin modo público)."""
    if os.environ.get("BL_SECRET_KEY"):
        return True
    return os.environ.get("BL_PUBLIC") != "1"


def _read_secrets():
    try:
        with open(_path("secrets.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get_secret(name, env=None):
    """Primero la variable de entorno (si se indica), después el archivo de secretos de la cuenta."""
    if env and os.environ.get(env):
        return os.environ[env]
    value = _read_secrets().get(name, "")
    if isinstance(value, str) and value.startswith(PREFIX):
        try:
            return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
        except Exception:  # clave cambiada, archivo dañado o falta la biblioteca
            return ""
    return value


def _write_secrets(data):
    sp = _path("secrets.json")
    tmp = sp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    try:
        os.chmod(tmp, 0o600)  # solo el usuario del servidor puede leerlo
    except OSError:
        pass
    os.replace(tmp, sp)


def set_secret(name, value):
    if value and not cifrado_listo():
        raise SecretError("Este servidor no tiene configurada la clave de cifrado (BL_SECRET_KEY): no puede guardar contraseñas ni claves de forma segura.")
    data = _read_secrets()
    if value:
        f = _fernet()
        data[name] = PREFIX + f.encrypt(value.encode()).decode() if f else value
    else:
        data.pop(name, None)
    _write_secrets(data)


def encrypt_existing():
    """Cifra los secretos que quedaron sin cifrar (por ejemplo, guardados antes de configurar BL_SECRET_KEY)."""
    f = _fernet()
    data = _read_secrets()
    if not f or not data:
        return 0
    n = 0
    for k, v in list(data.items()):
        if isinstance(v, str) and v and not v.startswith(PREFIX):
            data[k] = PREFIX + f.encrypt(v.encode()).decode()
            n += 1
    if n:
        _write_secrets(data)
    return n
