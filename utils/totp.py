"""Segundo factor (TOTP) para PesosApp: secretos, códigos, respaldo y QR.

Funciones puras: sin Flask ni base de datos. El cifrado del secreto en
reposo y el flujo de login viven en `app.py`.
"""
from __future__ import annotations

import hashlib
import secrets
import string

import pyotp
import qrcode
import qrcode.image.svg

EMISOR = 'PesosApp'
CANTIDAD_CODIGOS_RESPALDO = 8
ALFABETO_RESPALDO = string.ascii_lowercase + string.digits


def nuevo_secreto() -> str:
    return pyotp.random_base32()


def uri_provision(secreto: str, cuenta: str) -> str:
    """URI `otpauth://` para la app de autenticación (Google Authenticator,
    1Password, Authy…)."""
    return pyotp.TOTP(secreto).provisioning_uri(name=cuenta, issuer_name=EMISOR)


def _normalizar(codigo) -> str:
    return ''.join(ch for ch in str(codigo or '') if ch.isalnum()).lower()


def verificar_codigo(secreto: str, codigo) -> bool:
    """Acepta el código actual y los de ±30 s (relojes desfasados)."""
    limpio = _normalizar(codigo)
    if not secreto or not limpio.isdigit() or len(limpio) != 6:
        return False
    return pyotp.TOTP(secreto).verify(limpio, valid_window=1)


def generar_codigos_respaldo(cantidad: int = CANTIDAD_CODIGOS_RESPALDO) -> list[str]:
    """Códigos de un solo uso, `xxxx-xxxx`, para cuando no está el teléfono."""
    codigos = []
    for _ in range(cantidad):
        cuerpo = ''.join(secrets.choice(ALFABETO_RESPALDO) for _ in range(8))
        codigos.append(f'{cuerpo[:4]}-{cuerpo[4:]}')
    return codigos


def hash_codigo_respaldo(codigo) -> str:
    """SHA-256 del código normalizado. Los códigos tienen 40 bits de azar, así
    que no hace falta un hash lento; sí hace falta no guardarlos en claro."""
    return hashlib.sha256(_normalizar(codigo).encode()).hexdigest()


def consumir_codigo_respaldo(hashes: list[str], codigo) -> tuple[bool, list[str]]:
    """Devuelve (válido, hashes_restantes). Un código vale una sola vez."""
    objetivo = hash_codigo_respaldo(codigo)
    restantes = [h for h in (hashes or []) if h != objetivo]
    return (len(restantes) != len(hashes or [])), restantes


TAMANO_QR_PX = 240


def qr_svg(uri: str) -> str:
    """El QR como SVG inline, listo para escanear en cualquier tema.

    `qrcode` emite el trazado sin color ni fondo y en milímetros (2,5 cm):
    sobre el tema oscuro de la app quedaba negro sobre negro y chico. Se
    fija fondo blanco, trazado negro y 240 px, que es lo que la cámara
    necesita.
    """
    import re
    imagen = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=6, border=2)
    svg = imagen.to_string(encoding='unicode')
    svg = re.sub(r'width="[^"]+" height="[^"]+"',
                 f'width="{TAMANO_QR_PX}" height="{TAMANO_QR_PX}"', svg, count=1)
    svg = svg.replace('<path ', '<path fill="#000" ', 1)
    svg = re.sub(r'(<svg[^>]*>)', r'\1<rect width="100%" height="100%" fill="#fff"/>', svg, count=1)
    return svg
