"""Etiqueta de pedido 4x2 en ZPL, para imprimirla por Bluetooth desde la
pantalla de pesar (Zebra ZQ520 y cualquier Link-OS).

Una Zebra no entiende PDF: la app del fabricante en el teléfono es la que lo
convierte en imagen. Con ZPL el navegador manda el texto directo a la
impresora (Web Bluetooth en Chrome para Android) y la etiqueta sale al pie
de la báscula, caja por caja, sin salir de la pantalla de pesar.

El diseño replica `draw_order_label` (utils/label_utils.py): logo a la
izquierda, columna de filas a la derecha, medida grande, separador y el
producto centrado abajo. Las medidas están en puntos de impresora a 203 dpi
(4 x 2 pulgadas = 812 x 406 puntos).

El logo NO viaja en cada etiqueta: se carga una vez en la memoria flash de
la impresora (`~DG E:...`) y cada etiqueta lo invoca (`^XG`). Por Bluetooth
de baja energía se escriben 20 bytes por paquete, así que mandar el logo
con cada caja tardaría más que pesarla.
"""
import hashlib
import os
from io import BytesIO

from PIL import Image as PILImage

from utils.label_utils import logo_monocromo_para_etiqueta, normalize_temperature

DPI = 203
ANCHO = 812      # 4 in
ALTO = 406       # 2 in
MARGEN = 23      # 8 pt

# Logo: cuadro de 1,2 in en la esquina superior izquierda (como el PDF).
LOGO_MAX = 244

# Columna derecha: rótulos alineados a la derecha en x=568 (2,80 in), valores
# desde x=593 (2,92 in). Alturas: tope del texto, no línea base.
ROTULO_DERECHA = 568
VALOR_X = 593
FILA_Y = (45, 81, 118, 154, 191)
FILA_FUENTE = 27          # 9,5 pt
MEDIDA_Y = 250
MEDIDA_FUENTE_ROTULO = 44  # 15,6 pt
MEDIDA_FUENTE_VALOR = 47   # 16,8 pt
SEPARADOR_Y = 317
PRODUCTO_Y = 328
PRODUCTO_ANCHO = ANCHO - 2 * MARGEN


def escapar(texto):
    """Texto seguro dentro de ^FD: sin los caracteres de control de ZPL."""
    if texto is None:
        return ''
    return (str(texto)
            .replace('^', ' ')
            .replace('~', '-')
            .replace('\\', '/')
            .replace('\r', ' ')
            .replace('\n', ' '))


def _fuente_producto(nombre):
    """Tamaño y líneas para el nombre del producto según su largo, imitando
    el ajuste de `draw_center_wrap_text` (19,2 pt máximo, 12 pt mínimo)."""
    largo = len(nombre)
    if largo <= 24:
        return 54, 1
    if largo <= 34:
        return 40, 1
    return 34, 2


def etiqueta_pedido_zpl(item, cliente, mostrar_cliente=True, logo_nombre=None):
    """ZPL de una etiqueta de pedido.

    `item` es el dict de `_caja_pesada_to_label_item` / `_detalle_legacy_to_label_item`.
    `logo_nombre` es el objeto ya cargado en la impresora (p. ej. E:JA1B2C3.GRF);
    None imprime sin logo.
    """
    filas = [
        ('Client:', cliente or ''),
        ('Lot:', item.get('lote') or ''),
        ('Manufactured:', item.get('fecha_fabricacion') or ''),
        ('Expiration:', item.get('fecha_expiracion') or ''),
        ('When Kept at:', normalize_temperature(item.get('temperatura') or '')),
    ]
    if not mostrar_cliente:
        filas.pop(0)

    partes = [
        '^XA',
        '^CI28',                    # UTF-8: acentos y el símbolo de grados
        f'^PW{ANCHO}',
        f'^LL{ALTO}',
        '^LH0,0',
        '^MNY',                     # rollo de etiquetas troqueladas: sensor de separación
        '^MMT',                     # tear-off
    ]
    if logo_nombre:
        partes.append(f'^FO{MARGEN},{MARGEN}^XG{logo_nombre},1,1^FS')

    for (rotulo, valor), y in zip(filas, FILA_Y):
        partes.append(
            f'^FO{MARGEN},{y}^A0N,{FILA_FUENTE},{FILA_FUENTE}'
            f'^FB{ROTULO_DERECHA - MARGEN},1,0,R^FD{escapar(rotulo)}^FS')
        partes.append(
            f'^FO{VALOR_X},{y}^A0N,{FILA_FUENTE},{FILA_FUENTE}^FD{escapar(valor)}^FS')

    partes.append(
        f'^FO{MARGEN},{MEDIDA_Y}^A0N,{MEDIDA_FUENTE_ROTULO},{MEDIDA_FUENTE_ROTULO}'
        f'^FB{ROTULO_DERECHA - MARGEN},1,0,R^FD{escapar(item.get("medida_rotulo") or "")}^FS')
    partes.append(
        f'^FO{VALOR_X},{MEDIDA_Y}^A0N,{MEDIDA_FUENTE_VALOR},{MEDIDA_FUENTE_VALOR}'
        f'^FD{escapar(item.get("medida_valor") or "")}^FS')

    partes.append(f'^FO{MARGEN},{SEPARADOR_Y}^GB{PRODUCTO_ANCHO},2,2^FS')

    producto = escapar(item.get('producto_nombre') or 'N/A')
    fuente, lineas = _fuente_producto(producto)
    partes.append(
        f'^FO{MARGEN},{PRODUCTO_Y}^A0N,{fuente},{fuente}'
        f'^FB{PRODUCTO_ANCHO},{lineas},0,C^FD{producto}^FS')

    partes.append('^PQ1')
    partes.append('^XZ')
    return '\n'.join(partes)


# ---------------------------------------------------------------------------
# Logo → objeto gráfico en la impresora
# ---------------------------------------------------------------------------

def _abrir_logo_para_zpl(logo_bytes=None, logo_path=None):
    """Imagen en escala de grises sobre fondo blanco, lista para binarizar.

    El logo de un cliente pasa por `logo_monocromo_para_etiqueta` (tinta
    negra sobre transparente); el de Jomar ya es artwork negro."""
    if logo_bytes:
        try:
            logo_bytes = logo_monocromo_para_etiqueta(logo_bytes)
        except Exception:
            pass
        imagen = PILImage.open(BytesIO(logo_bytes)).convert('RGBA')
    else:
        imagen = PILImage.open(logo_path).convert('RGBA')
    fondo = PILImage.new('RGBA', imagen.size, (255, 255, 255, 255))
    fondo.alpha_composite(imagen)
    return fondo.convert('L')


def _binarizar(imagen, max_w, max_h):
    imagen = imagen.copy()
    imagen.thumbnail((max_w, max_h), PILImage.LANCZOS)
    # 1 = tinta. Pillow '1' usa 255 para blanco, así que se invierte a mano.
    return imagen.point(lambda v: 1 if v < 128 else 0, mode='1')


def _fila_hex(fila_bytes):
    """Una fila en hexadecimal, con la compresión mínima y segura de ZPL:
    «,» rellena el resto de la fila con ceros."""
    hexs = fila_bytes.hex().upper()
    recortado = hexs.rstrip('0')
    if not recortado:
        return ','
    if len(recortado) < len(hexs):
        return recortado + ','
    return hexs


def logo_a_grf(logo_bytes=None, logo_path=None, max_w=LOGO_MAX, max_h=LOGO_MAX):
    """(nombre, zpl) del logo como objeto gráfico en memoria flash.

    El nombre lleva un hash del contenido: si el cliente cambia de logo, el
    nombre cambia y la impresora recibe el nuevo en vez de reutilizar el
    viejo. `zpl` es el comando ~DG completo; se manda una sola vez por
    conexión y persiste apagado (E: es flash).
    """
    if not logo_bytes and not (logo_path and os.path.exists(logo_path)):
        return None, None

    fuente = logo_bytes if logo_bytes else open(logo_path, 'rb').read()
    digest = hashlib.sha1(fuente).hexdigest()[:6].upper()
    nombre = f'E:J{digest}.GRF'

    imagen = _binarizar(_abrir_logo_para_zpl(logo_bytes, logo_path), max_w, max_h)
    ancho, alto = imagen.size
    bytes_por_fila = (ancho + 7) // 8
    # Pillow empaqueta el modo '1' a bytes por fila, MSB primero: justo lo
    # que espera ~DG.
    crudo = imagen.tobytes()
    filas = []
    anterior = None
    for i in range(alto):
        fila = crudo[i * bytes_por_fila:(i + 1) * bytes_por_fila]
        if fila == anterior:
            filas.append(':')      # «:» repite la fila anterior
        else:
            filas.append(_fila_hex(fila))
        anterior = fila
    datos = ''.join(filas)
    total = bytes_por_fila * alto
    return nombre, f'~DG{nombre},{total},{bytes_por_fila},{datos}'
