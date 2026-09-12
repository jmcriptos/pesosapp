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
- [ ] **Revisar quién tiene acceso** a Heroku (`heroku access --app pesosapp`)
      y a n8n; dejar solo los imprescindibles.

## Mantenimiento anotado

- Heroku avisa que el stack Heroku-24 tiene sucesor (Heroku-26). No es
  urgente; se hace en un deploy tranquilo siguiendo
  https://devcenter.heroku.com/articles/upgrading-to-the-latest-stack.
- Heroku Redis mini no persiste datos: si se reinicia, el contador de
  intentos vuelve a cero. Aceptable para un límite de login.

## Fuera de este arreglo: segundo factor (2FA)

Con una sola contraseña de super_admin se llega a QuickBooks, exportaciones
y usuarios. Propuesta, para decidir aparte porque cambia el login de todos
los super_admin y necesita una app de autenticación en el teléfono:

- TOTP (Google Authenticator, 1Password, Authy) obligatorio para
  `super_admin`, opcional para el resto.
- Columna `totp_secret` en `vendedor` (cifrada con la misma `QBO_TOKEN_KEY`
  o una clave propia), pantalla de alta con código QR, segundo paso en el
  login, y códigos de respaldo de un solo uso.
- Dependencias: `pyotp` y `qrcode`.
- Esfuerzo: uno a dos días con tests.

## Nota

`tests/test_dashboard_kpis.py::test_dashboard_ventas_qbo_transacciones_con_home_amount_prioriza`
falla entre las 20:00 y las 24:00 hora de Curaçao: usa `date.today()` (UTC)
para una venta y la app corta el mes con la fecha local, así que la venta
queda «en el futuro». Preexistente, no tocado.
