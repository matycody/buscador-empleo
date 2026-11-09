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
| `BL_BACKUP_ENDPOINT`, `BL_BACKUP_BUCKET`, `BL_BACKUP_KEY_ID`, `BL_BACKUP_SECRET` | copia automática a almacenamiento S3 (R2, B2…); apagada si falta alguna | — |
| `BL_BACKUP_MINUTOS`, `BL_BACKUP_REGION`, `BL_BACKUP_PREFIX` | cada cuánto copia, región y carpeta dentro del bucket | 2, auto, buscador |

## Panel de administración
Con tu correo en `BL_ADMIN_EMAILS`, entrás con tu cuenta a `/admin`: ves cuántas cuentas hay, cuántas están activas, el estado de cada portal (si uno falla 3 veces seguidas te llega un mail, como máximo cada 12 horas) y el uso de la caché. Solo muestra números: nunca correos ni ofertas de nadie.

## Correos con Brevo (confirmación y recuperación de contraseña)
1. Creá una cuenta en brevo.com (plan gratis: 300 mails por día).
2. **Remitentes y dominios → Agregar un remitente** y confirmá el correo que te llega. Idealmente verificá tu dominio (DKIM) para que no caiga en spam.
3. **SMTP y API → Claves de API → Generar una clave**.
4. Cargá la clave en `BREVO_API_KEY` y el remitente en `BREVO_SENDER_EMAIL`.

Con esas dos variables, las cuentas nuevas deben confirmar el correo para ingresar, aparece «¿Olvidaste tu contraseña?» y se puede activar el resumen diario de ofertas (cada mail trae un link de baja firmado). Sin ellas, el programa funciona igual (modo local). Las cuentas creadas antes de activar los mails cuentan como confirmadas.

## Gratis, para probar con pocas personas (Render gratis + copia a Cloudflare R2)
El plan gratis de Render **no tiene disco** (los datos se borran en cada reinicio) y **se duerme a los 15 minutos**. Este camino lo resuelve sin pagar:
la app guarda una copia cifrada de `data/` en un almacenamiento gratis, la restaura sola al arrancar, y UptimeRobot evita que se duerma.

**1. Cloudflare R2 (almacenamiento de las copias, 10 GB gratis)**
1. Creá una cuenta en cloudflare.com → **R2 Object Storage** (puede pedir un método de pago para activarlo; con el uso de esta app no se cobra).
2. **Create bucket** (por ejemplo `buscador-copias`), privado.
3. **Manage R2 API Tokens → Create API token** con permiso *Object Read & Write* sobre ese bucket. Anotá el *Access Key ID*, el *Secret Access Key* y el endpoint (`https://<tu-cuenta>.r2.cloudflarestorage.com`).

**2. Render, servicio gratis**
1. **New → Web Service** → elegí el repositorio → *Runtime: Docker* → *Instance type: Free*. No agregues disco.
2. En **Environment** cargá:
   - `BL_PUBLIC` = `1`
   - `BL_SECRET_KEY` = un texto largo y secreto que inventes. **Guardalo aparte y no lo cambies nunca**: cifra las copias y las contraseñas guardadas; si cambia, no se pueden leer.
   - `BL_BASE_URL`, `BL_OPERADOR`, `BL_CONTACTO`, `BL_ADMIN_EMAILS` (y las de Brevo cuando las tengas)
   - `BL_BACKUP_ENDPOINT`, `BL_BACKUP_BUCKET`, `BL_BACKUP_KEY_ID`, `BL_BACKUP_SECRET` (los datos de R2). Opcional: `BL_BACKUP_MINUTOS` (por defecto 2).
3. Deploy. En el log tiene que aparecer «Copia de seguridad activa». En `/admin` ves la fecha de la última copia.

**3. UptimeRobot (que no se duerma)**
Cuenta gratis en uptimerobot.com → **Add New Monitor** → tipo *HTTP(s)* → URL `https://tu-servicio.onrender.com/api/me` → intervalo de 5 minutos. (750 horas gratis al mes alcanzan para un servicio encendido todo el mes.)

**Cómo protege los datos**
- Cada 2 minutos sube solo lo que cambió, cifrado con `BL_SECRET_KEY` (el bucket nunca ve datos en claro). Una cuenta borrada también se borra de la copia.
- Al recibir la señal de apagado de Render (en cada reinicio o deploy) hace una **última copia completa** antes de cerrar.
- Si arranca con la carpeta vacía, **restaura todo** desde la copia. Nunca restaura encima de datos existentes.
- **Límite honesto:** si el servidor se cae de golpe, sin avisar, se pierden como máximo los cambios de los últimos 2 minutos. No reemplaza a un disco real: cuando tengas usuarios de verdad, pasá a Render Starter con disco (la copia sigue sirviendo de respaldo).

## Otra opción: un servidor propio con Docker
Un VPS chico con Docker y un dominio apuntando a su IP. En `docker-compose.yml` cambiá `empleo.tudominio.com` por tu dominio y ejecutá `docker compose up -d`; Caddy consigue el HTTPS solo. Los datos quedan en `./data`: copialos seguido.

## Antes de abrirlo a desconocidos (pendiente)
- [ ] **Revisar con un abogado los términos y la privacidad** (`app/static/terminos.html` y `privacidad.html`): son un modelo general. Se piden al registrarse y queda guardada la versión aceptada. Si cambiás el texto, subí `LEGAL_VERSION` en `app/server.py`.
- [ ] **Inscribir la base de datos ante la AAIP** (Registro Nacional de Bases de Datos Personales), obligación de la Ley 25.326 para quien administra datos de terceros.
- [x] **Contraseña de Gmail y claves de API cifradas**: con `BL_SECRET_KEY` se cifran con una clave distinta por cuenta (Render la genera sola con `render.yaml`). Sin esa variable, el modo público no deja guardarlas. **Guardá esa clave aparte**: si se pierde o cambia, nadie podrá descifrar lo guardado y cada persona tendría que volver a cargar su contraseña.
- [x] **Búsquedas desde un solo servidor**: hay una caché compartida entre cuentas (mismo portal, país y zona = una sola consulta real). Aun así los portales pueden bloquear la IP del servidor: mirá `/admin` los primeros días.
- [x] **Copias de seguridad automáticas**: con las variables `BL_BACKUP_*` la app copia `data/` cifrada a un almacenamiento externo (ver «Gratis» arriba). Con disco propio (Render Starter) activá además los snapshots del disco; SQLite alcanza para decenas de usuarios, no para miles.
- [ ] **Pagos (Mercado Pago)**: todavía no hay planes ni cobros. Antes de agregarlos hay que definir precios y revisar lo legal (facturación, defensa del consumidor).
- [ ] **Condiciones de uso de cada portal**: revisá que permitan mostrar sus ofertas en un servicio con otros usuarios (Remotive, por ejemplo, prohíbe reenviarlas a terceros).
- [x] **Repositorio limpio**: el proyecto se publica desde `buscador-empleo` (ver abajo).

## Tests
`python -m unittest discover -s tests -t .` (38 pruebas de lectores, puntaje, cuentas, cifrado, caché, copia de seguridad y modo oscuro). GitHub Actions los corre en cada push (`.github/workflows/tests.yml`). Los lectores de portales se prueban con HTML de ejemplo, no con los sitios reales: si un portal cambia su página, el panel `/admin` lo muestra.

## Repositorio limpio
El repositorio original (`BusquedaLaboral`) tiene en su historial datos personales del autor y es público. El proyecto se publica desde un repositorio nuevo con historial propio (`buscador-empleo`). Regla para no repetirlo: **nunca** subir `data/`, CVs, capturas con datos reales ni claves; `.gitignore` ya excluye `data/`, `*.db`, `.env` y `cvs/`. Para las capturas del README usá siempre cuentas de ejemplo.
