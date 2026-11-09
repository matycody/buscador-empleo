# Guía de uso

Detalle de cada pantalla y función.

## Rubro y puestos a buscar

La primera vez que se abre la app pregunta qué trabajo buscás (salud, construcción, ventas, administración, logística, gastronomía, educación, electricidad, programación, limpieza/seguridad, o puestos propios). Con eso se arman los **puestos que se buscan en todos los portales** y el puntaje de cada oferta. Se puede cambiar en Configuración → Portales → "Cambiar de rubro". Las configuraciones anteriores se migran solas.

## Mientras busca

Aparece un cartel con el avance por fuente (portales, empresas, Gmail, guardado). Las alertas de Computrabajo que llegan por Gmail ahora separan puesto, empresa, lugar y antigüedad.

## Registro inicial (perfil)

La primera vez se abre un asistente de 4 pasos: datos personales (nombre, correo, teléfono), rubro y puestos, zona/modalidad/nivel de experiencia y CV (opcional, se guarda en `data/cvs`). De ahí salen los puestos buscados, las zonas que sirven, las penalizaciones por nivel y los datos de las postulaciones. Se puede repetir desde Configuración → "Editar mi perfil y rubro".

Las ofertas que no nombran nada de lo que buscás se limitan a 10 puntos y quedan ocultas con el filtro "Relevantes" (el de por defecto); "Todas" las muestra.

## Postularse en ventana lateral

"Abrir oferta" abre el aviso en una ventana al costado (55% del ancho, a la derecha). Al volver a la app o cerrar esa ventana, pregunta "¿Te postulaste a…?": **Sí, apliqué** la marca como aplicada y pasa a la siguiente oferta; **Todavía no** la deja como está; **No me sirve** la descarta. Los portales no permiten mostrarse dentro de la propia app (bloquean los marcos), por eso es una ventana aparte. Si el navegador bloquea ventanas emergentes, se abre como pestaña común.

## Cuentas

Al abrir la app hay que **crear una cuenta** (nombre, correo y contraseña de 8+ caracteres) o ingresar. Cada cuenta tiene su propia carpeta en `data/users/<id>/` con su perfil, ofertas, CV, claves (Gmail, Jooble) y búsqueda automática; una cuenta no ve los datos de otra. La primera cuenta que se crea se queda con los datos que ya hubiera de la versión sin cuentas.

- Las contraseñas se guardan con PBKDF2-SHA256 (200 mil vueltas y sal propia), nunca en texto. La sesión dura 30 días y se cierra desde **Mi cuenta → Cerrar sesión**.
- Tras 5 intentos fallidos se bloquea el ingreso de ese correo por 10 minutos.
- **Mi cuenta** permite cambiar la contraseña (cierra las demás sesiones), editar el perfil y eliminar la cuenta con todos sus datos.
- Si olvidaste la contraseña: `python run.py --reset-password tu@correo.com NuevaClave123` (hace falta acceso a la carpeta del programa).
- El servidor escucha solo en `127.0.0.1`. Para abrirlo a otras personas habría que ponerlo detrás de HTTPS y de un dominio; no está hecho.

## Configuración

Está organizada en secciones (Mi perfil, Qué busco, Dónde, Portales, Empresas, Alertas por Gmail, Mensajes de postulación, Automático y avisos, Mis datos). Los puestos, lugares y zonas se editan como etiquetas (se escribe y se aprieta Enter), las palabras que suman o restan puntos se ajustan con su número al lado, las empresas son una lista con nombre y link, y cada portal se activa con un interruptor.

## Empresas según tu rubro

Al elegir rubros en el asistente se cargan empresas de ese rubro (ventas: Coto, Carrefour, Jumbo…; limpieza y seguridad: Prosegur, Brink's…; programación: Mercado Libre, Globant…) más agencias de empleo. En el menú **Mis empresas** aparece además **Contratando ahora**: las empresas con más ofertas relevantes entre las que trajo Buscar ofertas, con un botón **+ Seguir** para sumarlas. Tocar el nombre filtra sus ofertas.

## Lectura del CV

Al subir el CV (Word, texto, ODT o PDF hecho desde un editor) se lee su texto y se suman al perfil las aptitudes que aparecen (herramientas, programas, oficios) y se refuerzan las palabras que ya estaban. Un PDF escaneado como imagen no se puede leer: en ese caso se guarda el archivo y se avisa.

## Usarlo desde el celular

`python run.py --red` abre la app a tu red WiFi y muestra la dirección para escribir en el celular. Las cuentas nuevas solo se pueden crear desde la computadora. En el celular se puede "Agregar a la pantalla de inicio" para usarla como app.

## Seguimiento de postulaciones

En la pestaña **Aplicadas** hay un resumen (aplicadas, esperando, para seguimiento, entrevistas, ofertas, rechazadas). En cada oferta aplicada se anota cómo va (sin novedades, me respondieron, entrevista, me ofrecieron el puesto, rechazada) y se marca "Hice seguimiento hoy"; el aviso de seguimiento cuenta desde el último contacto y se apaga cuando hay entrevista, oferta o rechazo. El CSV exportado incluye el resultado y la fecha del último seguimiento.

## Portal Empleo y alertas por mail
- **Portal Empleo** (portalempleo.gob.ar, Estado nacional): se lee con tus búsquedas y se quedan solo las ofertas de tus zonas. Se activa en Configuración → Portales.
- **Indeed / LinkedIn**: no se consultan directo; creá alertas en cada portal con tu Gmail y activá «Alertas por Gmail» (hay una guía en ese panel).
