# Publicarlo en internet para que lo usen otras personas

Hoy el programa corre en tu computadora. Estos pasos lo dejan en un servidor con HTTPS. **No lo abras al público sin HTTPS**: las contraseñas viajarían sin cifrar.

## Qué hace el modo público (`BL_PUBLIC=1`)
- Permite crear cuentas desde internet (máximo 5 por hora por conexión).
- Marca la cookie de sesión como `Secure` y envía `Strict-Transport-Security`.
- Lee la IP real desde `X-Forwarded-For` (la pone el proxy HTTPS).
- Cifra las contraseñas de Gmail y claves de API guardadas (necesita `BL_SECRET_KEY` y `pip install -r requirements.txt`).
- Limita los pedidos de mails (10 por hora por conexión y 3 por correo).
- Limita los intentos de ingreso (30 por conexión y 10 por correo cada 10 minutos) y las búsquedas manuales (`BL_MAX_BUSQUEDAS_HORA`, 6 por cuenta y hora).
- Cabeceras `X-Frame-Options`, `nosniff`, `Referrer-Policy` y `Content-Security-Policy` (solo corre JavaScript propio); están siempre activas.

## ¿Vercel o Render?
**Render.** Vercel ejecuta funciones que se apagan después de cada pedido y no tienen disco: esta app necesita un proceso que quede encendido (busca ofertas sola cada tanto) y guarda cuentas, CVs y una base SQLite en disco. En Vercel se perderían los datos y la búsqueda automática. Render (o Railway, Fly.io o un VPS) sí corre un servidor permanente con disco.

## Publicarlo en Render
1. Subí el repositorio (el limpio, ver abajo) a GitHub.
2. En Render: **New → Blueprint** y elegí el repositorio. Lee `render.yaml` y crea el servicio con un disco de 1 GB. Necesita un plan pago (el gratuito no tiene disco persistente y se duerme).
3. Cuando Render te dé la URL, cargala en la variable `BL_BASE_URL` (los links de los mails se arman con ella). Si usás dominio propio, agregalo en Render y usá ese.
4. Cargá `BL_OPERADOR` (tu nombre o razón social) y `BL_CONTACTO` (correo de contacto): aparecen en los términos y en la política de privacidad.
5. Cargá `BREVO_API_KEY` y `BREVO_SENDER_EMAIL` (ver más abajo) y esperá el deploy. Render pone el HTTPS solo.

## Variables de entorno
| Variable | Para qué | Por defecto |
|---|---|---|
| `BL_PUBLIC` | modo servidor público | — |
| `BL_SECRET_KEY` | cifra contraseñas y claves guardadas (guardala aparte) | — |
| `BL_BASE_URL` | URL pública, para los links de los mails | — |
| `BL_OPERADOR`, `BL_CONTACTO` | datos que aparecen en términos y privacidad | — |
| `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME` | envío de mails | — |
| `BL_ADMIN_EMAILS` | quién ve `/admin` y recibe alertas de portales caídos | — |
| `BL_CACHE_MINUTOS` | minutos que se reutiliza una búsqueda entre cuentas | 180 (público) / 10 |
| `BL_DIGEST_HORA`, `BL_TZ_OFFSET` | hora y huso del resumen diario | 8 y -3 |
| `BL_MAX_BUSQUEDAS_HORA` | búsquedas manuales por cuenta y hora | 6 |

## Panel de administración
Con tu correo en `BL_ADMIN_EMAILS`, entrás con tu cuenta a `/admin`: ves cuántas cuentas hay, cuántas están activas, el estado de cada portal (si uno falla 3 veces seguidas te llega un mail, como máximo cada 12 horas) y el uso de la caché. Solo muestra números: nunca correos ni ofertas de nadie.

## Correos con Brevo (confirmación y recuperación de contraseña)
1. Creá una cuenta en brevo.com (plan gratis: 300 mails por día).
2. **Remitentes y dominios → Agregar un remitente** y confirmá el correo que te llega. Idealmente verificá tu dominio (DKIM) para que no caiga en spam.
3. **SMTP y API → Claves de API → Generar una clave**.
4. Cargá la clave en `BREVO_API_KEY` y el remitente en `BREVO_SENDER_EMAIL`.

Con esas dos variables, las cuentas nuevas deben confirmar el correo para ingresar, aparece «¿Olvidaste tu contraseña?» y se puede activar el resumen diario de ofertas (cada mail trae un link de baja firmado). Sin ellas, el programa funciona igual (modo local). Las cuentas creadas antes de activar los mails cuentan como confirmadas.

## Otra opción: un servidor propio con Docker
Un VPS chico con Docker y un dominio apuntando a su IP. En `docker-compose.yml` cambiá `empleo.tudominio.com` por tu dominio y ejecutá `docker compose up -d`; Caddy consigue el HTTPS solo. Los datos quedan en `./data`: copialos seguido.

## Antes de abrirlo a desconocidos (pendiente)
- [ ] **Revisar con un abogado los términos y la privacidad** (`app/static/terminos.html` y `privacidad.html`): son un modelo general. Se piden al registrarse y queda guardada la versión aceptada. Si cambiás el texto, subí `LEGAL_VERSION` en `app/server.py`.
- [ ] **Inscribir la base de datos ante la AAIP** (Registro Nacional de Bases de Datos Personales), obligación de la Ley 25.326 para quien administra datos de terceros.
- [x] **Contraseña de Gmail y claves de API cifradas**: con `BL_SECRET_KEY` se cifran con una clave distinta por cuenta (Render la genera sola con `render.yaml`). Sin esa variable, el modo público no deja guardarlas. **Guardá esa clave aparte**: si se pierde o cambia, nadie podrá descifrar lo guardado y cada persona tendría que volver a cargar su contraseña.
- [x] **Búsquedas desde un solo servidor**: hay una caché compartida entre cuentas (mismo portal, país y zona = una sola consulta real). Aun así los portales pueden bloquear la IP del servidor: mirá `/admin` los primeros días.
- [ ] **Copias de seguridad automáticas** del disco (en Render, activá los snapshots del disco; en un VPS, copiá `data/` a diario); SQLite alcanza para decenas de usuarios, no para miles.
- [ ] **Pagos (Mercado Pago)**: todavía no hay planes ni cobros. Antes de agregarlos hay que definir precios y revisar lo legal (facturación, defensa del consumidor).
- [ ] **Condiciones de uso de cada portal**: revisá que permitan mostrar sus ofertas en un servicio con otros usuarios (Remotive, por ejemplo, prohíbe reenviarlas a terceros).
- [x] **Repositorio limpio**: el proyecto se publica desde `buscador-empleo` (ver abajo).

## Tests
`python -m unittest discover -s tests -t .` (25 pruebas de lectores, puntaje, cuentas, cifrado y caché). GitHub Actions los corre en cada push (`.github/workflows/tests.yml`). Los lectores de portales se prueban con HTML de ejemplo, no con los sitios reales: si un portal cambia su página, el panel `/admin` lo muestra.

## Repositorio limpio
El repositorio original (`BusquedaLaboral`) tiene en su historial datos personales del autor y es público. El proyecto se publica desde un repositorio nuevo con historial propio (`buscador-empleo`). Regla para no repetirlo: **nunca** subir `data/`, CVs, capturas con datos reales ni claves; `.gitignore` ya excluye `data/`, `*.db`, `.env` y `cvs/`. Para las capturas del README usá siempre cuentas de ejemplo.
