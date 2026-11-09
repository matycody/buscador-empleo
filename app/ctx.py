"""Carpeta de datos del usuario que está usando la app en este momento (una por cuenta)."""
import contextlib
import contextvars
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DATA = os.path.join(BASE, "data")
_dir = contextvars.ContextVar("user_dir", default=None)


def data_dir():
    return _dir.get() or ROOT_DATA


def set_dir(path):
    return _dir.set(path)


@contextlib.contextmanager
def using(path):
    tok = _dir.set(path)
    try:
        yield
    finally:
        _dir.reset(tok)
