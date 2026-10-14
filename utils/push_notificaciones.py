"""Notificaciones push (Web Push + VAPID) para avisar de pedidos nuevos.

Qué hace y qué no
-----------------
La app ya es una PWA (manifest + icono en la pantalla de inicio). Esto le
agrega lo que le faltaba para avisar aunque esté cerrada: un service worker
(`static/sw.js`) que recibe el push y muestra la notificación, y este módulo,
que desde el servidor arma el mensaje y lo manda a cada suscripción.

No hay servicio de terceros (Firebase, OneSignal): Web Push habla directo con
el servicio de push del navegador (Apple, Google, Mozilla) usando un par de
claves VAPID que identifica a ESTA app. Las claves se generan una vez con
`flask push-generar-claves` y van en variables de entorno.

Por qué un módulo aparte
------------------------
`app.py` se queda con lo que necesita la base y las rutas (modelo, endpoints,
el gancho en `nuevo_pedido`). Todo lo que es puro —leer la configuración,
armar el texto, hablar con pywebpush— vive acá y se prueba sin levantar Flask.

iOS
---
Safari manda push solo si la app se abrió desde el icono de la pantalla de
inicio (iOS 16.4 en adelante). Desde el Safari "normal" ni siquiera existe
`PushManager`. La pantalla de Notificaciones lo explica al usuario.
"""
import base64
import json
import logging
import os

log = logging.getLogger(__name__)

# El TTL le dice al servicio de push cuánto guardar el mensaje si el teléfono
# está apagado o sin señal. Un pedido nuevo de hace 12 horas ya no es
# "nuevo": a esa altura el repartidor lo vio en el listado.
TTL_SEGUNDOS = 12 * 60 * 60
TIMEOUT_ENVIO = 8


# ── Configuración ───────────────────────────────────────────────────────────

def claves_vapid():
    """Devuelve (publica, privada, email) desde el entorno, o None si falta
    alguna. Sin claves la función queda apagada, nunca rota: los endpoints
    responden 503 con un mensaje claro y el resto de la app no se entera."""
    publica = (os.environ.get('VAPID_PUBLIC_KEY') or '').strip()
    privada = (os.environ.get('VAPID_PRIVATE_KEY') or '').strip()
    email = (os.environ.get('VAPID_CLAIMS_EMAIL') or '').strip()
    if not (publica and privada and email):
        return None
    if not email.startswith('mailto:'):
        email = 'mailto:' + email
    return publica, privada, email


def push_configurado():
    return claves_vapid() is not None


def generar_claves():
    """Genera un par VAPID nuevo. Devuelve (publica, privada) en base64url,
    que es el formato que esperan el navegador (`applicationServerKey`) y
    pywebpush (`vapid_private_key` como string crudo)."""
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    v = Vapid()
    v.generate_keys()
    publica = v.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    privada = v.private_key.private_numbers().private_value.to_bytes(32, 'big')
    return _b64url(publica), _b64url(privada)


def _b64url(datos):
    return base64.urlsafe_b64encode(datos).decode('ascii').rstrip('=')


# ── Mensaje ─────────────────────────────────────────────────────────────────

def armar_payload_nuevo_pedido(pedido_id, cliente, cajas, total, moneda,
                               vendedor=None, fecha_entrega=None, url='/pedidos'):
    """Texto de la notificación. Corto a propósito: en la pantalla bloqueada
    del teléfono entran dos líneas y lo primero que importa es QUIÉN pidió.

    `cajas` y `total` ya vienen como número; acá solo se formatean. El total
    sigue la convención del dashboard (coma de miles, punto decimal)."""
    partes = [cliente]
    if cajas:
        partes.append(f'{_fmt_num(cajas)} cajas')
    if total:
        partes.append(f'{_fmt_num(total, 2)} {moneda or "XCG"}')
    cuerpo = ' · '.join(partes)
    if fecha_entrega:
        cuerpo += f' · entrega {fecha_entrega.strftime("%d/%m")}'
    if vendedor:
        cuerpo += f'\nTomado por {vendedor}'
    return {
        'title': f'Nuevo pedido #{pedido_id}',
        'body': cuerpo,
        'url': url,
        # Mismo tag = la segunda notificación del mismo pedido reemplaza a la
        # primera en vez de apilarse (un reintento no genera dos avisos).
        'tag': f'pedido-{pedido_id}',
        'pedido_id': pedido_id,
    }


def _fmt_num(valor, decimales=0):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    if decimales == 0 and numero == int(numero):
        return f'{int(numero):,}'
    texto = f'{numero:,.{max(decimales, 1) if decimales else 2}f}'
    if decimales == 0:
        texto = texto.rstrip('0').rstrip('.')
    return texto


# ── Envío ───────────────────────────────────────────────────────────────────

def enviar(suscripcion, payload, claves=None):
    """Manda `payload` (dict) a UNA suscripción.

    `suscripcion` es un dict {'endpoint', 'p256dh', 'auth'}: se pasa el dato
    plano y no el modelo para poder llamar esto desde un hilo sin sesión de
    base de datos.

    Devuelve ('ok', None), ('baja', motivo) o ('error', motivo).
      - 'baja': el servicio de push dice que esa suscripción ya no existe
        (404/410: el usuario revocó el permiso o desinstaló la PWA). Quien
        llama la borra de la base; insistir sería ruido en el log para siempre.
      - 'error': falló esta vez (red, 5xx). Se deja la suscripción.
    """
    claves = claves or claves_vapid()
    if claves is None:
        return 'error', 'VAPID sin configurar'
    publica, privada, email = claves

    try:
        from pywebpush import WebPushException, webpush
    except ImportError as exc:  # pragma: no cover - dependencia instalada
        return 'error', f'pywebpush no instalado: {exc}'

    info = {
        'endpoint': suscripcion['endpoint'],
        'keys': {'p256dh': suscripcion['p256dh'], 'auth': suscripcion['auth']},
    }
    try:
        webpush(
            subscription_info=info,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=privada,
            # pywebpush muta el dict (le agrega `aud` y `exp`): uno nuevo por envío.
            vapid_claims={'sub': email},
            ttl=TTL_SEGUNDOS,
            timeout=TIMEOUT_ENVIO,
        )
        return 'ok', None
    except WebPushException as exc:
        respuesta = getattr(exc, 'response', None)
        status = getattr(respuesta, 'status_code', None)
        if status in (404, 410):
            return 'baja', f'HTTP {status}'
        return 'error', f'{exc} (HTTP {status})' if status else str(exc)
    except Exception as exc:  # red caída, DNS, timeout
        return 'error', str(exc)
