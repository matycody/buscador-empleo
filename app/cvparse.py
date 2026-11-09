"""Lee el texto de un CV (txt, docx, odt, pdf) y detecta aptitudes para sumarlas al perfil."""
import re
import zipfile
import zlib
from html import unescape

from .presets import PRESETS
from .scoring import norm

COMMON_SKILLS = ["excel", "word", "office", "ingles", "atencion al cliente", "licencia de conducir", "autocad", "python",
                 "java", "javascript", "sql", "react", "html", "css", "git", "linux", "php", "c++", "docker",
                 "power bi", "tableau", "plc", "siemens", "logo", "scada", "soldadura", "manejo de autoelevador",
                 "facturacion", "tesoreria", "stock", "inventario", "primeros auxilios", "rcp", "cocina",
                 "barista", "soporte tecnico", "wordpress", "figma"]


def _txt(raw):
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def _xml_text(xml):
    xml = re.sub(r"</w:p>|</text:p>|<w:br/>|<w:tab/>", "\n", xml)
    return unescape(re.sub(r"<[^>]+>", "", xml))


def _cmaps(streams):
    """Une las tablas ToUnicode de los tipos de letra (glifo → texto)."""
    table = {}
    for s in streams:
        if b"beginbfchar" not in s and b"beginbfrange" not in s:
            continue
        t = s.decode("latin-1")
        for blk in re.findall(r"beginbfchar(.*?)endbfchar", t, re.S):
            for a, b in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
                table[int(a, 16)] = bytes.fromhex(b if len(b) % 2 == 0 else "0" + b).decode("utf-16-be", "ignore")
        for blk in re.findall(r"beginbfrange(.*?)endbfrange", t, re.S):
            for a, b, c in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
                lo, hi, base = int(a, 16), int(b, 16), int(c, 16)
                for i in range(lo, min(hi, lo + 512) + 1):
                    try:
                        table[i] = chr(base + i - lo)
                    except ValueError:
                        pass
    return table


def _pdf(raw):
    streams = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        data = m.group(1)
        try:
            data = zlib.decompress(data)
        except Exception:
            pass
        streams.append(data)
    table = _cmaps(streams)
    out = []
    for s in streams:
        if b"BT" not in s:
            continue
        t = s.decode("latin-1")
        for blk in re.findall(r"BT(.*?)ET", t, re.S):
            for op in re.finditer(r"\[(.*?)\]\s*TJ|(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]+>)\s*Tj", blk, re.S):
                body = op.group(1) if op.group(1) is not None else op.group(2)
                piece = ""
                for lit, hexs in re.findall(r"\(((?:\\.|[^\\)])*)\)|<([0-9A-Fa-f\s]+)>", body):
                    if hexs:
                        h = re.sub(r"\s", "", hexs)
                        w = 4 if table and max(table) > 255 else 2
                        piece += "".join(table.get(int(h[i:i + w], 16), "") for i in range(0, len(h) - w + 1, w))
                    else:
                        piece += re.sub(r"\\(.)", lambda mm: {"n": "\n", "r": "", "t": " "}.get(mm.group(1), mm.group(1)), lit)
                out.append(piece)
            out.append("\n")
    return " ".join(out)


def extract_text(path):
    ext = path.lower().rsplit(".", 1)[-1]
    try:
        if ext == "txt":
            return _txt(open(path, "rb").read())
        if ext == "docx":
            with zipfile.ZipFile(path) as z:
                return _xml_text(z.read("word/document.xml").decode("utf-8", "ignore"))
        if ext == "odt":
            with zipfile.ZipFile(path) as z:
                return _xml_text(z.read("content.xml").decode("utf-8", "ignore"))
        if ext == "pdf":
            return _pdf(open(path, "rb").read())
    except Exception:
        return ""
    return ""


def vocabulary():
    """término → peso sugerido, juntando todos los rubros y aptitudes comunes."""
    voc = {}
    for p in PRESETS.values():
        for k, w in p["keywords"].items():
            voc[k] = max(voc.get(k, 0), w)
    for k in COMMON_SKILLS:
        voc.setdefault(k, 5)
    return voc


def _has(text, term):
    return re.search(r"(?<![a-z0-9])" + re.escape(norm(term)) + r"(?![a-z0-9])", text) is not None


def analyze(text, keywords):
    """Devuelve (keywords nuevas, lista agregadas, lista reforzadas, rubros ordenados por coincidencias)."""
    t = norm(text)
    if len(re.findall(r"[a-z]{3,}", t)) < 15:
        return None
    kws, added, boosted = dict(keywords), [], []
    for term, w in vocabulary().items():
        if not _has(t, term):
            continue
        if term in kws:
            if kws[term] < 10:
                kws[term] = min(10, kws[term] + 2)
                boosted.append(term)
        else:
            kws[term] = min(8, max(5, w - 2))
            added.append(term)
    rubros = sorted(((sum(1 for k in p["keywords"] if _has(t, k)), key) for key, p in PRESETS.items()), reverse=True)
    return kws, added, boosted, [key for n, key in rubros if n >= 3][:3]
