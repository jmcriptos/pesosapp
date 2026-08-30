# tests/test_pedido_impuesto.py
"""`tax_rate` es un CÓDIGO de QuickBooks, no un porcentaje.

Antes de esta tarea la traducción código→OB vivía duplicada en tres
plantillas (`productos.html:71,108`, `editar_producto.html:92`) y no existía
en el form de pedidos, que le mostraba al vendedor el código crudo
(«Impuesto 10», «Impuesto 14») — un número que no le dice nada y que, peor,
un código desconocido podía leerse como "sin impuesto" cuando en realidad sí
paga uno. `_ob_de_codigo` es el único dueño de esa traducción; el resto de
la app (incluida `_etiqueta_grupo`) la reusa.
"""
import json
import os
import re

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()

        vendedor = Vendedor(
            username='admin', email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)

        _db.session.add(Cliente(nombre='Cliente OB6', territorio_id=territorio.id))
        _db.session.add(Cliente(nombre='Cliente OB0', territorio_id=territorio.id))

        for nombre, tax in [
            ('Chuleta de cerdo ahumada 5 kg', 10.0),   # imp:10 -> OB 6%
            ('Ham di Pasku 4 kg', 14.0),                # imp:14 -> OB 0%
        ]:
            _db.session.add(Producto(
                nombre=nombre, descripcion='x', temperatura='Congelado',
                se_pesa=True, tax_rate=tax,
            ))
        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin', 'password': 'testpass',
    }, follow_redirects=True)
    return client


def _cliente(nombre):
    from app import Cliente
    return Cliente.query.filter_by(nombre=nombre).first()


# === `_ob_de_codigo`: la traducción, con un solo dueño ===

def test_los_dos_codigos_de_produccion_se_traducen(app):
    with app.app_context():
        from app import _ob_de_codigo
        assert _ob_de_codigo(10) == {'pct': 6.0, 'etiqueta': 'OB 6%'}
        assert _ob_de_codigo(14) == {'pct': 0.0, 'etiqueta': 'OB 0%'}


def test_un_codigo_desconocido_no_se_asume_exento(app):
    """Asumir 0% en un código que no conocemos es inventar que no paga
    impuesto, y eso se le canta al cliente como precio final."""
    with app.app_context():
        from app import _ob_de_codigo
        r = _ob_de_codigo(99)
        assert r['pct'] is None
        assert '99' in r['etiqueta']


def test_la_etiqueta_del_grupo_deja_de_ser_el_codigo_crudo(app):
    """El código no le dice nada al vendedor; el propio app.py lo advierte
    tres veces. La app YA traduce en /productos: acá se reusa."""
    with app.app_context():
        from app import _etiqueta_grupo
        assert _etiqueta_grupo(10) == 'OB 6%'
        assert _etiqueta_grupo(14) == 'OB 0%'


def test_un_codigo_desconocido_en_la_etiqueta_del_grupo_no_dice_impuesto_cero(app):
    """Mismo peligro que arriba pero en el punto donde de verdad se usa."""
    with app.app_context():
        from app import _etiqueta_grupo
        etiqueta = _etiqueta_grupo(99)
        assert '0%' not in etiqueta
        assert '99' in etiqueta


# === El chip de grupo del form de pedidos ya no muestra el código crudo ===

def test_el_chip_de_grupo_muestra_ob_6_no_impuesto_10(app, logged_client):
    cliente = _cliente('Cliente OB6')
    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    boton = re.search(r'<a[^>]*id="ph-grupo-actual"[^>]*>.*?</a>', html, re.S)
    assert boton, 'falta el botón de grupo en el paso del pedido'
    assert 'OB 6%' in boton.group(0)
    assert 'Impuesto' not in boton.group(0)


def test_el_chip_de_grupo_muestra_ob_0_no_impuesto_14(app, logged_client):
    cliente = _cliente('Cliente OB0')
    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:14').get_data(as_text=True)

    boton = re.search(r'<a[^>]*id="ph-grupo-actual"[^>]*>.*?</a>', html, re.S)
    assert boton, 'falta el botón de grupo en el paso del pedido'
    assert 'OB 0%' in boton.group(0)
    assert 'Impuesto' not in boton.group(0)


# === El mapa OB que viaja al JS es el mismo diccionario de Python ===

def _extraer_const(html, marca):
    inicio = html.index(marca) + len(marca)
    fin = html.index('\n', inicio)
    return json.loads(html[inicio:fin].rstrip().rstrip(';'))


def test_el_mapa_de_ob_que_llega_al_js_trae_los_porcentajes_reales(app, logged_client):
    """La pantalla calcula el desglose en el navegador (el vendedor edita
    cajas en vivo), así que el porcentaje tiene que viajar del servidor: si
    este bloque no trae los números correctos, ninguna cuenta del lado del
    cliente puede estar bien."""
    cliente = _cliente('Cliente OB6')
    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    mapa = _extraer_const(html, 'const OB_POR_CODIGO = ')
    assert mapa == {'10': 6.0, '14': 0.0}


# === El footer del paso 2 deja de mostrar un número desnudo ===

def test_el_footer_del_pedido_rotula_el_numero_como_subtotal(app, logged_client):
    cliente = _cliente('Cliente OB6')
    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    fila = re.search(
        r'<div class="pn-footer-row">.*?</div>\s*</div>', html, re.S)
    assert fila, 'no se encontró la fila del footer del paso 2'
    # No es solo "el rótulo dice Subtotal en algún lado": tiene que estar
    # pegado al número (`total-pedido`), no suelto en otra parte del footer.
    etiqueta = re.search(r'pn-footer-total-label">([^<]*)<', fila.group(0))
    assert etiqueta and etiqueta.group(1).strip().lower() == 'subtotal'
    assert 'id="total-pedido"' in fila.group(0)


# === El desglose de la revisión: tres filas, no una que miente ===

def test_la_revision_tiene_fila_de_subtotal_ob_y_total(app, logged_client):
    cliente = _cliente('Cliente OB6')
    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    assert 'id="pn-revision-subtotal"' in html
    assert 'id="pn-revision-ob-monto"' in html
    assert 'id="pn-revision-total"' in html

    # La fila de OB arranca oculta: la decide el JS según el grupo del
    # pedido en curso, no el servidor al renderizar la página en blanco.
    fila_ob = re.search(r'<div[^>]*id="pn-revision-fila-ob"[^>]*>', html).group(0)
    assert 'hidden' in fila_ob
