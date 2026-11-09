"""Arranca el servidor:  python run.py   (luego abrir http://127.0.0.1:8000)

Para usarlo también desde el celular (misma red WiFi):  python run.py --red
Olvidaste tu contraseña:  python run.py --reset-password tu@correo.com NuevaClave123
"""
import socket
import os
import sys

from app import users
from app.server import run


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no envía nada: solo elige la placa de red
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "--reset-password":
        try:
            users.reset_password(args[1], args[2])
            print("Listo: contraseña cambiada. Ya podés ingresar.")
        except users.AuthError as e:
            print("No se pudo:", e)
        sys.exit(0)
    red = "--red" in args
    nums = [a for a in args if a.isdigit()]
    port = int(nums[0]) if nums else 8000
    if red:
        ip = lan_ip()
        print("\nModo red: abrilo desde el celular (mismo WiFi) en  http://%s:%d" % (ip or "<IP de esta PC>", port))
        print("Ingresá con tu cuenta. Las cuentas nuevas solo se crean desde esta computadora.")
        print("Si no abre: permití Python en el Firewall de Windows para redes privadas.\n")
    publico = os.environ.get("BL_PUBLIC") == "1"
    if publico:
        print("Modo público: cuentas abiertas, cookies seguras. Ponelo detrás de HTTPS (ver DEPLOY.md).")
    run(host="0.0.0.0" if (red or publico) else "127.0.0.1", port=port)
