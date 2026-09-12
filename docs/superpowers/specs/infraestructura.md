# Infraestructura de PesosApp

Estado al 2026-09-12, tras el corte a QuickBooks por API directa
(`plans/2026-09-11-qbo-api-directa.md`) y los arreglos de seguridad
(`plans/2026-09-12-seguridad.md`). Actualizar este archivo cuando cambie
algo de la tabla.

## Dónde corre

| Pieza | Dónde | Notas |
|---|---|---|
| Aplicación web | Heroku, app `pesosapp`, dyno `web` con gunicorn (`Procfile`), stack Heroku-24 | Heroku-26 disponible; migrar en un deploy tranquilo |
| Base de datos | Heroku Postgres `postgresql-dimensional-16123` (PostgreSQL 16) | Backups automáticos diarios (retención del plan); contienen los tokens cifrados |
| Redis | Heroku Redis mini `redis-defined-07562` | Solo el contador de intentos de login; no persiste datos, y no hace falta |
| Tareas programadas | Heroku Scheduler `scheduler-convex-94702` | Job diario 09:00 UTC (05:00 Curaçao): `flask --app app qbo-fijar-tasa`. Se administra con `heroku addons:open scheduler --app pesosapp` |
| Dominio | `https://app.jomarfoods.com` por Cloudflare | `pesosapp-caa46963237c.herokuapp.com` sigue accesible en directo; por eso la IP de Cloudflare solo se acepta si la petición llegó desde sus rangos |
| Código | GitHub `jmcriptos/pesosapp`, rama `main` | Deploy manual: `git push heroku main` |
| Sesiones de desarrollo | Claude Code en la nube, rama `claude/*`, merge directo a `main` (decisión de JM 2026-09-12) | No tiene acceso a Heroku ni a cuentas; los `config:set` y deploys los corre JM |

## Integraciones

| Integración | Cómo | Estado |
|---|---|---|
| QuickBooks Online: crear factura, leer factura para el PDF | API v3 directa desde la app (`utils/qbo_client.py`, `utils/qbo_factura.py`), OAuth2 con tokens cifrados en `qbo_conexion` | `FACTURACION_BACKEND=qbo` desde 2026-09-12 |
| QuickBooks Online: ventas del dashboard | API v3 directa (`utils/qbo_ventas.py`), caché en `ventas_qb_cache` | `QB_SALES_BACKEND=qbo` desde 2026-09-12 |
| QuickBooks Online: tasa USD→ANG diaria | Antes de cada factura USD desde la app, y job diario en Heroku Scheduler (`flask --app app qbo-fijar-tasa`) | Desde 2026-09-12; el workflow de n8n se apaga tras verificar la tasa del 13 |
| Google Drive: archivo de PDF de facturas | n8n Cloud, webhook `N8N_DRIVE_WEBHOOK_URL`; app OAuth de Google publicada (sin caducidad de 7 días) | Queda en n8n |
| Alertas HACCP | n8n Cloud, webhook `N8N_HACCP_ALERT_WEBHOOK_URL` | Queda en n8n |
| Webhook de entrada de precios | Ruta de la app autenticada con `WEBHOOK_SECRET` | Activo |
| n8n Cloud: facturación, consulta de factura, tasa, ventas | Workflows activos como red de seguridad | Se apagan en el paso 10 del runbook `2026-09-11-qbo-corte-heroku.md` |

## Variables de entorno en Heroku (nombres; los valores no van en el repo)

| Variable | Para qué |
|---|---|
| `SECRET_KEY` | Firma de sesiones y cookies |
| `DATABASE_URL`, `REDIS_URL` | Las pone Heroku |
| `RATELIMIT_STORAGE_URI` | Redis para el límite de login (= `REDIS_URL`; la app agrega el TLS) |
| `TRUST_CF_CONNECTING_IP=1` | Cloudflare delante; `CLOUDFLARE_IP_RANGES` opcional si cambian los rangos |
| `QBO_CLIENT_ID`, `QBO_CLIENT_SECRET`, `QBO_ENVIRONMENT=production`, `QBO_REDIRECT_URI`, `QBO_MINOR_VERSION`, `QBO_TIMEOUT` | Conexión a QuickBooks |
| `QBO_TOKEN_KEY` | Clave Fernet: cifra los tokens de QuickBooks y los secretos del segundo factor. **Está en el gestor de contraseñas de JM.** Si se pierde: reconectar QuickBooks y los usuarios reconfiguran el 2FA |
| `QBO_TASA_USD=1.78` | Tasa que se fija en QBO y con la que se convierten las ventas USD del dashboard |
| `FACTURACION_BACKEND=qbo`, `QB_SALES_BACKEND=qbo` | Backends; `n8n` vuelve al camino anterior sin deploy |
| `TOTP_OBLIGATORIO_ROLES=super_admin` | Segundo factor obligatorio para administradores |
| `N8N_*` | Webhooks de n8n (Drive, HACCP, y los de facturación/ventas mientras sigan como red) |
| `WEBHOOK_SECRET`, `N8N_OUTBOUND_SECRET` | Tokens de los webhooks de entrada y salida |

## Cuentas y accesos (revisado 2026-09-12)

- Heroku: un solo usuario, el dueño, con segundo factor.
- n8n Cloud: solo JM.
- Google Cloud (app OAuth «Jomar n8n», proyecto `bill-extractor-2025`): cuenta Gmail de la empresa, con segundo factor.
- Intuit Developer (app de QuickBooks): la misma app sirve a n8n y a PesosApp, cada uno con su propio refresh token.
- PesosApp: los super_admin con segundo factor obligatorio.

## Comandos de operación

```bash
heroku logs --tail --app pesosapp                      # logs en vivo
heroku pg:psql --app pesosapp                          # consola de Postgres
heroku config --app pesosapp                           # variables (muestra secretos: no pegar en chats)
heroku run --app pesosapp -- flask --app app qbo-fijar-tasa   # fija la tasa USD hoy y mañana
heroku run --app pesosapp -- flask --app app 2fa-reset USUARIO # quita el 2FA de un usuario
heroku run --app pesosapp -- python scripts/comparar_ventas_qbo.py  # ventas n8n vs API
heroku config:set FACTURACION_BACKEND=n8n --app pesosapp       # vuelta atrás de facturación
heroku config:set QB_SALES_BACKEND=n8n --app pesosapp          # vuelta atrás del dashboard
```

## Qué pasa si…

| Situación | Qué hacer |
|---|---|
| QuickBooks rechaza la conexión («no está conectado») | Configuración → QuickBooks → Desconectar y Conectar de nuevo con la cuenta que administra la empresa |
| Se pierde `QBO_TOKEN_KEY` | Generar otra, cargarla, reconectar QuickBooks; los usuarios vuelven a configurar el 2FA |
| Un administrador pierde el teléfono | Códigos de respaldo; si no, otro admin lo restablece desde Usuarios o `flask 2fa-reset` |
| Redis caído | La app arranca igual; el límite de login pasa a memoria y avisa en el log |
| Cloudflare cambia sus rangos | `CLOUDFLARE_IP_RANGES` con la lista nueva, sin deploy |
| Una factura sale mal por API | `FACTURACION_BACKEND=n8n` mientras se corrige; los workflows siguen activos hasta el paso 10 |
