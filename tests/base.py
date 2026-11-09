"""Ayudas comunes: cada test trabaja en una carpeta de datos temporal para no tocar datos reales."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import ctx, users  # noqa: E402


class TempData(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bl-test-")
        self._old = (ctx.ROOT_DATA, users.ROOT, users.USERS_PATH, users.SESSIONS_PATH, users.TOKENS_PATH, users.USERS_DIR)
        ctx.ROOT_DATA = users.ROOT = self.tmp
        users.USERS_PATH = os.path.join(self.tmp, "users.json")
        users.SESSIONS_PATH = os.path.join(self.tmp, "sessions.json")
        users.TOKENS_PATH = os.path.join(self.tmp, "tokens.json")
        users.USERS_DIR = os.path.join(self.tmp, "users")
        self._env = dict(os.environ)
        for k in ("BL_PUBLIC", "BL_SECRET_KEY", "BL_CACHE_MINUTOS", "BL_ADMIN_EMAILS", "BREVO_API_KEY"):
            os.environ.pop(k, None)

    def tearDown(self):
        (ctx.ROOT_DATA, users.ROOT, users.USERS_PATH, users.SESSIONS_PATH, users.TOKENS_PATH, users.USERS_DIR) = self._old
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)
