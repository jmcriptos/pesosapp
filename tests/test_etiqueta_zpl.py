"""Etiqueta 4x2 en ZPL para la Zebra por Bluetooth (utils/zpl.py)."""
import os
from io import BytesIO

from PIL import Image

from utils.zpl import etiqueta_pedido_zpl, logo_a_grf, escapar, ANCHO, ALTO

ROOT = os.path.join(os.path.dirname(__file__), '..')

ITEM = {
    'producto_nombre': 'Andouiline Pork Chorizo',
    'temperatura': '-18 oC',
    'medida_rotulo': 'Net Weight:',
    'medida_valor': '16.90 kg',
    'lote': 'L-2309202601',
    'fecha_fabricacion': '2026-09-23',
    'fecha_expiracion': '2027-09-23',
}


def test_etiqueta_zpl_lleva_todos_los_campos():
    zpl = etiqueta_pedido_zpl(ITEM, cliente='DeliNova', mostrar_cliente=True, logo_nombre='E:JABC123.GRF')
    assert zpl.startswith('^XA') and zpl.endswith('^XZ')
    assert f'^PW{ANCHO}' in zpl and f'^LL{ALTO}' in zpl
    assert '^CI28' in zpl                      # UTF-8: el «°» de la temperatura
    assert '^MNY' in zpl                       # rollo de etiquetas troqueladas
    assert '^XGE:JABC123.GRF,1,1^FS' in zpl    # logo ya cargado en la impresora
    for texto in ('Client:', 'DeliNova', 'Lot:', 'L-2309202601', 'Manufactured:', '2026-09-23',
                  'Expiration:', '2027-09-23', 'When Kept at:', '-18 _C2_B0C',
                  'Net Weight:', '16.90 kg', 'Andouiline Pork Chorizo'):
        assert texto in zpl, texto
    assert '^PQ1' in zpl


def test_etiqueta_zpl_sin_fila_cliente_cuando_lleva_logo_propio():
    zpl = etiqueta_pedido_zpl(ITEM, cliente='DeliNova', mostrar_cliente=False, logo_nombre=None)
    assert 'Client:' not in zpl
    assert 'DeliNova' not in zpl
    assert '^XG' not in zpl


def test_escapar_quita_caracteres_de_control_de_zpl():
    assert escapar('Lomo ^ Falda ~ Pollo\\') == 'Lomo   Falda - Pollo/'
    assert escapar(None) == ''


def test_escapar_deja_la_etiqueta_en_ascii_puro():
    """Browser Print (Android) manda el texto byte a byte: con «°» o acentos
    crudos y ^CI28 salían en blanco. Van como bytes UTF-8 en hexadecimal."""
    assert escapar('-18 °C') == '-18 _C2_B0C'
    assert escapar('Jamón') == 'Jam_C3_B3n'
    assert escapar('L_0001') == 'L_5F0001'
    zpl = etiqueta_pedido_zpl(dict(ITEM, producto_nombre='Jamón Ahumado'), cliente='Café Ñ')
    assert zpl.isascii()
    assert '^FH^FD' in zpl and '^FD' not in zpl.replace('^FH^FD', '')


def test_nombre_largo_baja_la_fuente_y_permite_dos_lineas():
    corto = etiqueta_pedido_zpl(dict(ITEM, producto_nombre='Pork Chorizo'), cliente='X')
    largo = etiqueta_pedido_zpl(dict(ITEM, producto_nombre='Chuleta de Cerdo Ahumada Sin Hueso Premium'), cliente='X')
    assert '^A0N,54,54' in corto
    assert '^A0N,34,34' in largo and ',2,0,C^FH^FD' in largo


def _png(ancho, alto, negro=True):
    imagen = Image.new('RGBA', (ancho, alto), (0, 0, 0, 255) if negro else (255, 255, 255, 0))
    buf = BytesIO()
    imagen.save(buf, format='PNG')
    return buf.getvalue()


def test_logo_a_grf_arma_el_comando_dg_con_los_bytes_correctos():
    # 16 x 4 píxeles negros: 2 bytes por fila, 8 bytes en total, filas
    # repetidas comprimidas con «:».
    nombre, zpl = logo_a_grf(logo_bytes=_png(16, 4))
    assert nombre.startswith('E:J') and nombre.endswith('.GRF')
    assert zpl.startswith(f'~DG{nombre},8,2,')
    datos = zpl.split(',', 3)[3]
    assert datos == 'FFFF:::'


def test_logo_a_grf_comprime_los_ceros_a_la_derecha():
    # Logo transparente: todo blanco → cada fila es «,» y se repite con «:».
    nombre, zpl = logo_a_grf(logo_bytes=_png(16, 2, negro=False))
    assert zpl.endswith(',2,,:')


def test_logo_a_grf_reduce_al_cuadro_del_logo():
    nombre, zpl = logo_a_grf(logo_bytes=_png(1000, 500))
    total, por_fila = (int(v) for v in zpl.split(',')[1:3])
    assert por_fila == 31            # 244 px → 31 bytes
    assert total == por_fila * 122   # proporción 2:1 conservada


def test_logo_de_jomar_se_convierte():
    ruta = os.path.join(ROOT, 'static', 'logo_etiquetas.png')
    nombre, zpl = logo_a_grf(logo_path=ruta)
    assert nombre and zpl.startswith('~DG')
    assert len(zpl) < 40000          # cabe en segundos por Bluetooth


def test_sin_logo_devuelve_none():
    assert logo_a_grf(logo_bytes=None, logo_path='/no/existe.png') == (None, None)


def test_el_nombre_cambia_si_cambia_el_logo():
    a, _ = logo_a_grf(logo_bytes=_png(16, 4))
    b, _ = logo_a_grf(logo_bytes=_png(16, 8))
    assert a != b
