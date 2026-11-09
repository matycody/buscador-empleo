"""Envío de correos con Brevo (https://www.brevo.com, plan gratis: 300 mails por día).

Se activa con dos variables de entorno:
  BREVO_API_KEY       clave de la API (Brevo → SMTP y API → Claves de API)
  BREVO_SENDER_EMAIL  remitente verificado en Brevo (ej: no-reply@tudominio.com)
Opcional: BREVO_SENDER_NAME (por defecto «Buscador de empleo»).
Si no están, el programa funciona igual pero sin verificación de correo ni recuperación por mail.
"""
import json
import os
import urllib.request

API = "https://api.brevo.com/v3/smtp/email"


def enabled():
    return bool(os.environ.get("BREVO_API_KEY") and os.environ.get("BREVO_SENDER_EMAIL"))


def send(to, subject, html, text=""):
    """Manda un correo. Devuelve True si Brevo lo aceptó; nunca levanta error (el llamador decide qué avisar)."""
    if not enabled():
        return False
    payload = {
        "sender": {"name": os.environ.get("BREVO_SENDER_NAME", "Buscador de empleo"), "email": os.environ["BREVO_SENDER_EMAIL"]},
        "to": [{"email": to}], "subject": subject, "htmlContent": html, "textContent": text or subject,
    }
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), method="POST", headers={
        "api-key": os.environ["BREVO_API_KEY"], "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300
    except Exception as e:
        print("No se pudo enviar el correo:", e)
        return False


def _page(title, body, button, url):
    return (f'<div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:24px;color:#15212b">'
            f'<h2 style="margin:0 0 12px">{title}</h2><p style="line-height:1.5">{body}</p>'
            f'<p style="margin:24px 0"><a href="{url}" style="background:#15212b;color:#fff;padding:12px 22px;border-radius:8px;'
            f'text-decoration:none;font-weight:bold">{button}</a></p>'
            f'<p style="font-size:12px;color:#667">Si no fuiste vos, ignorá este correo. Si el botón no funciona, copiá este link:<br>{url}</p></div>')


def send_verify(to, nombre, url):
    hola = f"Hola {nombre.split()[0]}," if nombre else "Hola,"
    return send(to, "Confirmá tu correo", _page("Confirmá tu correo", f"{hola} para activar tu cuenta tocá el botón. El link vale 48 horas.", "Confirmar mi correo", url),
                f"Confirmá tu correo entrando a: {url}")


def send_reset(to, url):
    return send(to, "Recuperá tu contraseña", _page("Recuperá tu contraseña", "Pediste cambiar tu contraseña. Tocá el botón para elegir una nueva. El link vale 1 hora y se usa una sola vez.", "Cambiar mi contraseña", url),
                f"Cambiá tu contraseña entrando a: {url}")
