# Arreglos de seguridad del 2026-09-12

Revisión hecha tras el corte a QuickBooks por API. Lo que estaba bien:
hash de contraseñas, sesiones (8 h, Secure/HttpOnly/Lax, protección
fuerte), CSRF, redirecciones de login validadas, HSTS, CSP con nonces,
consultas por ORM, exportaciones y admin solo super_admin, webhook de
precios con token en tiempo constante, secretos fuera de logs.
Dependencias: una sola advertencia (click), corregida.

## Hecho en código (rama `claude/festive-goldberg-ds8ujn`, mergeado a `main`)

| Riesgo | Arreglo | Dónde |
|---|---|---|
| Tokens de QuickBooks en texto plano en Postgres y backups | Cifrado Fernet en reposo con `QBO_TOKEN_KEY`; prefijo `enc:`; una fila vieja en texto plano se lee y se recifra en el siguiente refresco. Sin clave sigue en texto plano y `/admin/quickbooks` lo avisa. | `_qbo_cifrar` / `_qbo_descifrar` / `_QboStoreDb` en `app.py` |
| Límite de intentos de login esquivable falsificando la IP | Se toma la **última** IP de `X-Forwarded-For` (la pone Heroku) y no la primera; `CF-Connecting-IP` solo con `TRUST_CF_CONNECTING_IP=1`. Segundo límite **por cuenta** (5/min, 30/h) que solo cuenta fallos: la cuenta atacada se cierra venga de donde venga. | `_client_ip`, `_login_username_key`, `_login_rate_limit` |
| Contador de intentos en memoria, por worker, reiniciado con el dyno | `redis` en requirements; `RATELIMIT_STORAGE_URI` ya se leía del entorno. Falta el add-on (abajo). | `requirements.txt` |
| Camino «usuario legacy» con todos los permisos | Permisos fail-closed: solo un `Vendedor` tiene permisos; `index` devuelve 403 a cualquier otra cosa autenticada. | `inject_permissions`, `index`, `lista_pedidos` |
| Advertencia en `click` | `click==8.3.3` | `requirements.txt` |

Tests: `tests/test_seguridad.py` (14), incluido el escenario de fuerza bruta
en subproceso con el limitador activo.

## Pendiente de JM (configuración, no código)

- [x] **Clave de cifrado.** (hecho 2026-09-12: tokens cifrados, verificado en /admin/quickbooks) Generar en la Mac y cargar en Heroku (nunca en
      el chat ni en el repo):

      ```bash
      python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
      heroku config:set QBO_TOKEN_KEY='<la clave>' --app pesosapp
      ```

      Los tokens actuales se recifran solos en el próximo refresco (a más
      tardar una hora después del siguiente uso). `/admin/quickbooks` pasa
      de «Texto plano» a «Sí». **Guardar la clave en el gestor de
      contraseñas**: si se pierde, Desconectar y Conectar de nuevo.
- [x] **Redis para el límite de login.** (hecho 2026-09-12: add-on heroku-redis:mini, login verificado)

      ```bash
      heroku addons:create heroku-redis:mini --app pesosapp
      heroku config:get REDIS_URL --app pesosapp
      heroku config:set RATELIMIT_STORAGE_URI='<REDIS_URL>?ssl_cert_reqs=none' --app pesosapp
      ```

      Desde `b3ea36e` la app agrega sola el `?ssl_cert_reqs=none` a un
      `rediss://`, y una URI inválida ya no impide arrancar (cae a memoria
      con error en el log). Alcanza con:
      `heroku config:set RATELIMIT_STORAGE_URI="$(heroku config:get REDIS_URL --app pesosapp)" --app pesosapp`.
- [x] **`TRUST_CF_CONNECTING_IP=1`.** (hecho 2026-09-12, login verificado) JM confirmó (2026-09-12) que
      `app.jomarfoods.com` pasa por Cloudflare y que el dominio de
      `herokuapp.com` sigue accesible en directo. Desde `_client_ip` con
      rangos, la cabecera de Cloudflare se acepta solo si quien se conectó a
      Heroku es Cloudflare; un acceso directo con la cabecera falsificada
      queda con su IP real. Sin la bandera, todo el tráfico por Cloudflare
      comparte la IP del borde y el límite por IP (10/min) se vuelve
      colectivo. Cargar:
      `heroku config:set TRUST_CF_CONNECTING_IP=1 --app pesosapp`.
- [ ] **Desactivar en n8n** los workflows de facturación, consulta de
      factura y tasa (paso 10 del runbook del corte) apenas cierre el paso 8.
- [x] **Revisar quién tiene acceso** a Heroku: un solo usuario, el dueño
      (2026-09-12). Recomendado: segundo factor en la cuenta de Heroku y en
      el Gmail que la respalda; es la llave maestra de la app. Falta la
      misma revisión en n8n.

## Mantenimiento anotado

- Heroku avisa que el stack Heroku-24 tiene sucesor (Heroku-26). No es
  urgente; se hace en un deploy tranquilo siguiendo
  https://devcenter.heroku.com/articles/upgrading-to-the-latest-stack.
- Heroku Redis mini no persiste datos: si se reinicia, el contador de
  intentos vuelve a cero. Aceptable para un límite de login.

## Segundo factor (2FA) — hecho el 2026-09-12

TOTP con app de autenticación (Google Authenticator, 1Password, Authy…).
Código: `utils/totp.py` (puro), rutas `/login/2fa`, `/mi-cuenta/2fa*`,
`/admin/vendedores/<id>/2fa/reset`, comando `flask 2fa-reset USUARIO`,
hook `forzar_segundo_factor`. Tests: `tests/test_2fa.py` (20).

Cómo funciona:
- **Activar:** Mi cuenta → Segundo factor muestra un QR y la clave manual;
  se confirma con un código de la app. Al activarlo se muestran **una sola
  vez** ocho códigos de respaldo de un solo uso (guardados como hash).
- **Login:** contraseña correcta → si el usuario tiene 2FA, pantalla de
  código (TOTP con ±30 s, o un código de respaldo). Lo pendiente vive en la
  cookie de sesión firmada y caduca a los 5 minutos. Límite: 5 intentos por
  minuto por usuario, solo se cuentan fallos.
- **Secreto en reposo:** cifrado con `QBO_TOKEN_KEY` (la clave de la app),
  prefijo `enc:`, igual que los tokens de QuickBooks.
- **Obligatorio por rol:** `TOTP_OBLIGATORIO_ROLES=super_admin`. Un
  super_admin sin 2FA solo puede activarlo, cambiar contraseña o salir. Un
  rol obligado no puede desactivarlo. **Vacío por defecto** para que el
  deploy no deje a nadie afuera.
- **Recuperación:** códigos de respaldo; otro super_admin lo restablece
  desde Usuarios → panel del usuario → «Restablecer segundo factor»; o por
  terminal: `heroku run --app pesosapp -- flask --app app 2fa-reset USUARIO`.

### Despliegue (JM), en este orden

Estado 2026-09-12: migración, deploy y enrolamiento de JM hechos; login en
dos pasos verificado; `TOTP_OBLIGATORIO_ROLES=super_admin` cargada. Cerrado.

- [ ] Migración, **antes** del deploy:

      ```bash
      heroku pg:psql --app pesosapp
      ```
      ```sql
      ALTER TABLE vendedor ADD COLUMN IF NOT EXISTS totp_secret TEXT;
      ALTER TABLE vendedor ADD COLUMN IF NOT EXISTS totp_confirmado_en TIMESTAMP;
      ALTER TABLE vendedor ADD COLUMN IF NOT EXISTS codigos_respaldo TEXT;
      ```
- [ ] Deploy: `git pull origin main && git push heroku main`.
- [ ] Con tu usuario: menú → **Segundo factor** → escanear el QR con la app
      del teléfono → confirmar con el código → **guardar los ocho códigos de
      respaldo** en el gestor de contraseñas.
- [ ] Cerrar sesión y volver a entrar: contraseña y luego el código.
- [ ] Recién entonces, hacerlo obligatorio para los administradores:
      `heroku config:set TOTP_OBLIGATORIO_ROLES=super_admin --app pesosapp`.
      Cualquier otro super_admin verá la pantalla de activación al entrar.

## Nota

`tests/test_dashboard_kpis.py::test_dashboard_ventas_qbo_transacciones_con_home_amount_prioriza`
falla entre las 20:00 y las 24:00 hora de Curaçao: usa `date.today()` (UTC)
para una venta y la app corta el mes con la fecha local, así que la venta
queda «en el futuro». Preexistente, no tocado.
