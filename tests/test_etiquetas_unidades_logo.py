"""Etiquetas por unidades (productos vendidos por caja) y logo del cliente.

Diseño: docs/superpowers/specs/2026-08-27-etiquetas-unidades-y-logo-cliente-design.md
"""
import os
from io import BytesIO

import pytest
from unittest.mock import patch

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()

        vendedor = Vendedor(
            username='admin',
            email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id,
            territorio_id=territorio.id,
            activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin',
        'password': 'testpass',
    }, follow_redirects=True)
    return client


def _crear_pedido_con_linea(se_pesa=False, unidades_por_caja=None, cajas=1,
                            peso=0, cliente_logo=None, cliente_mimetype=None):
    """Crea cliente + producto + pedido con UNA línea de preparación.

    Devuelve el pedido. Se llama dentro de un app_context activo.
    """
    from app import Cliente, Producto, Pedido, DetallePedido, Territorio

    territorio = Territorio.query.first()
    cliente = Cliente(
        nombre='Cliente Test',
        territorio_id=territorio.id,
        qbo_id=f'QBO-C{Cliente.query.count() + 1}',
    )
    if cliente_logo is not None:
        cliente.logo_etiqueta = cliente_logo
        cliente.logo_mimetype = cliente_mimetype
    _db.session.add(cliente)

    producto = Producto(
        nombre='Producto Test',
        descripcion='Test',
        temperatura='4°C',
        se_pesa=se_pesa,
        tax_rate=6.0,
        qbo_id=f'QBO-P{Producto.query.count() + 1}',
        unidades_por_caja=unidades_por_caja,
    )
    _db.session.add(producto)
    _db.session.flush()

    pedido = Pedido(cliente_id=cliente.id, estado='preparado')
    _db.session.add(pedido)
    _db.session.flush()

    detalle = DetallePedido(
        pedido_id=pedido.id,
        producto_id=producto.id,
        cajas=cajas,
        peso=peso,
        precio_unitario=10.00,
        subtotal=10.00,
        lote='L001',
        fecha_fabricacion='2026-01-15',
        fecha_expiracion='2026-06-15',
        es_linea_pedido=False,
    )
    _db.session.add(detalle)
    _db.session.commit()
    return pedido


def _generar_4x2(logged_client, pedido_id):
    return logged_client.get(
        f'/generar_etiqueta_detalle/{pedido_id}'
        '?fecha_inicio=2026-01-01&fecha_fin=2026-12-31'
    )


def _medidas(mock_draw):
    """(rotulo, valor) de cada invocación a draw_order_label."""
    return [
        (kwargs['medida_rotulo'], kwargs['medida_valor'])
        for _args, kwargs in mock_draw.call_args_list
    ]


# === Etiquetas por unidades ===

@patch('app.draw_order_label')
def test_caja_entera_emite_una_etiqueta_por_caja(mock_draw, logged_client, app):
    """3 cajas de un producto de 24 uds → 3 etiquetas de 'Units: 24'."""
    with app.app_context():
        pedido = _crear_pedido_con_linea(unidades_por_caja=24, cajas=3)

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        assert _medidas(mock_draw) == [('Units:', '24')] * 3


@patch('app.draw_order_label')
def test_cajas_fraccionarias_emiten_etiqueta_por_el_resto(mock_draw, logged_client, app):
    """2,5 cajas de 24 uds → dos etiquetas de 24 y una de 12."""
    with app.app_context():
        pedido = _crear_pedido_con_linea(unidades_por_caja=24, cajas=2.5)

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        assert _medidas(mock_draw) == [
            ('Units:', '24'), ('Units:', '24'), ('Units:', '12'),
        ]


@patch('app.draw_order_label')
def test_media_caja_lleva_la_mitad_de_las_unidades(mock_draw, logged_client, app):
    """0,5 cajas de 24 uds → una etiqueta de 12, NO de 24.

    Regresión contra redondear hacia arriba (cajas_objetivo): las cajas
    surtidas llevan media caja de verdad, con la mitad de las unidades.
    """
    with app.app_context():
        pedido = _crear_pedido_con_linea(unidades_por_caja=24, cajas=0.5)

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        assert _medidas(mock_draw) == [('Units:', '12')]


@patch('app.draw_order_label')
def test_cuarto_de_caja_lleva_un_cuarto_de_las_unidades(mock_draw, logged_client, app):
    """0,25 cajas de 24 uds → una etiqueta de 6."""
    with app.app_context():
        pedido = _crear_pedido_con_linea(unidades_por_caja=24, cajas=0.25)

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        assert _medidas(mock_draw) == [('Units:', '6')]


@patch('app.draw_order_label')
def test_unidades_no_divisibles_redondean_al_entero_mas_cercano(mock_draw, logged_client, app):
    """10 uds por caja × 0,25 = 2,5 → se rotula 3 (las unidades son discretas)."""
    with app.app_context():
        pedido = _crear_pedido_con_linea(unidades_por_caja=10, cajas=0.25)

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        assert _medidas(mock_draw) == [('Units:', '3')]


@patch('app.draw_order_label')
def test_linea_sin_cajas_emite_una_etiqueta_con_unidades_completas(mock_draw, logged_client, app):
    """cajas=0 → una etiqueta con las unidades completas, no cero etiquetas."""
    with app.app_context():
        pedido = _crear_pedido_con_linea(unidades_por_caja=24, cajas=0)

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        assert _medidas(mock_draw) == [('Units:', '24')]


@patch('app.draw_order_label')
def test_producto_por_caja_sin_unidades_declaradas_dice_boxes(mock_draw, logged_client, app):
    """Sin unidades_por_caja → una sola etiqueta 'Boxes: 3' (nunca 'Net Weight')."""
    with app.app_context():
        pedido = _crear_pedido_con_linea(unidades_por_caja=None, cajas=3)

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        assert _medidas(mock_draw) == [('Boxes:', '3')]


@patch('app.draw_order_label')
def test_producto_pesado_sigue_diciendo_net_weight(mock_draw, logged_client, app):
    """Regresión: el producto pesado conserva 'Net Weight:' y los kg."""
    with app.app_context():
        pedido = _crear_pedido_con_linea(se_pesa=True, cajas=1, peso=12.50)

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        assert _medidas(mock_draw) == [('Net Weight:', '12.50 kg')]


# === Logo del cliente ===

def _png_bytes(size=(8, 8), color=(200, 30, 30)):
    """PNG real y pequeño, para probar la subida y el dibujo."""
    from PIL import Image
    buf = BytesIO()
    Image.new('RGB', size, color).save(buf, format='PNG')
    return buf.getvalue()


def _png_grande(min_bytes=1024 * 1024):
    """PNG real de más de 1 MB (ruido: no comprime)."""
    from PIL import Image
    lado = 700
    datos = os.urandom(lado * lado * 3)
    buf = BytesIO()
    Image.frombytes('RGB', (lado, lado), datos).save(buf, format='PNG')
    contenido = buf.getvalue()
    assert len(contenido) > min_bytes, f'PNG de prueba muy chico: {len(contenido)}'
    return contenido


def test_resolve_label_logo_con_bytes_devuelve_image_reader():
    """Con bytes del cliente devuelve un ImageReader, sin tocar el disco."""
    from reportlab.lib.utils import ImageReader
    from utils.label_utils import resolve_label_logo

    logo = resolve_label_logo('/cualquier/base', _png_bytes())

    assert isinstance(logo, ImageReader)


def test_resolve_label_logo_sin_bytes_devuelve_logo_de_jomar():
    """Sin bytes del cliente cae en la ruta del logo de Jomar."""
    from utils.label_utils import resolve_label_logo, get_logo_path

    assert resolve_label_logo('/cualquier/base', None) == get_logo_path('/cualquier/base')
    assert resolve_label_logo('/cualquier/base') == get_logo_path('/cualquier/base')


@patch('app.draw_order_label')
def test_pedido_de_cliente_con_logo_dibuja_el_logo_del_cliente(mock_draw, logged_client, app):
    """El logo del cliente reemplaza al de Jomar en la etiqueta 4x2.

    Se afirma sobre el argumento y no sobre los bytes del PDF: ReportLab
    recomprime las imágenes y buscarlas adentro del PDF sería frágil.
    """
    from reportlab.lib.utils import ImageReader

    with app.app_context():
        pedido = _crear_pedido_con_linea(
            unidades_por_caja=24, cajas=1,
            cliente_logo=_png_bytes(), cliente_mimetype='image/png',
        )

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        args, _kwargs = mock_draw.call_args
        assert isinstance(args[1], ImageReader)


@patch('app.draw_order_label')
def test_pedido_de_cliente_sin_logo_usa_el_de_jomar(mock_draw, logged_client, app):
    """Sin logo del cliente se sigue dibujando el logo de Jomar."""
    with app.app_context():
        from app import basedir
        from utils.label_utils import get_logo_path

        pedido = _crear_pedido_con_linea(unidades_por_caja=24, cajas=1)

        resp = _generar_4x2(logged_client, pedido.id)

        assert resp.status_code == 200
        args, _kwargs = mock_draw.call_args
        assert args[1] == get_logo_path(basedir)


@patch('app.draw_order_label_a4')
def test_etiqueta_a4_de_cliente_con_logo_dibuja_el_logo_del_cliente(mock_draw, logged_client, app):
    """El formato A4 también recibe el logo del cliente."""
    from reportlab.lib.utils import ImageReader

    with app.app_context():
        pedido = _crear_pedido_con_linea(
            unidades_por_caja=24, cajas=1,
            cliente_logo=_png_bytes(), cliente_mimetype='image/png',
        )

        resp = logged_client.get(
            f'/generar_etiqueta_detalle_a4/{pedido.id}'
            '?fecha_inicio=2026-01-01&fecha_fin=2026-12-31'
        )

        assert resp.status_code == 200
        args, _kwargs = mock_draw.call_args
        assert isinstance(args[1], ImageReader)


def test_pdf_real_con_logo_del_cliente_se_genera(logged_client, app):
    """Sin mocks: dibujar un ImageReader no debe explotar (os.path.exists)."""
    with app.app_context():
        pedido = _crear_pedido_con_linea(
            unidades_por_caja=24, cajas=1,
            cliente_logo=_png_bytes(), cliente_mimetype='image/png',
        )

        resp_4x2 = _generar_4x2(logged_client, pedido.id)
        resp_a4 = logged_client.get(
            f'/generar_etiqueta_detalle_a4/{pedido.id}'
            '?fecha_inicio=2026-01-01&fecha_fin=2026-12-31'
        )

        for resp in (resp_4x2, resp_a4):
            assert resp.status_code == 200
            assert resp.content_type == 'application/pdf'
            assert len(resp.data) > 100


# === Subida del logo ===

def _editar_cliente(logged_client, cliente_id, **campos):
    data = {'nombre': 'Cliente Test', 'qbo_id': '', 'moneda': 'XCG'}
    data.update(campos)
    return logged_client.post(
        f'/clientes/{cliente_id}/editar', data=data,
        content_type='multipart/form-data', follow_redirects=True,
    )


def test_subir_logo_png_valido_lo_guarda(logged_client, app):
    with app.app_context():
        from app import Cliente
        pedido = _crear_pedido_con_linea(unidades_por_caja=24)
        cliente_id = pedido.cliente_id
        png = _png_bytes()

        resp = _editar_cliente(
            logged_client, cliente_id,
            logo=(BytesIO(png), 'delinova.png'),
        )

        assert resp.status_code == 200
        cliente = _db.session.get(Cliente, cliente_id)
        assert cliente.logo_etiqueta == png
        assert cliente.logo_mimetype == 'image/png'


def test_subir_archivo_que_no_es_imagen_se_rechaza(logged_client, app):
    with app.app_context():
        from app import Cliente
        pedido = _crear_pedido_con_linea(unidades_por_caja=24)
        cliente_id = pedido.cliente_id

        resp = _editar_cliente(
            logged_client, cliente_id,
            logo=(BytesIO(b'esto no es una imagen'), 'virus.png'),
        )

        assert resp.status_code == 200
        cliente = _db.session.get(Cliente, cliente_id)
        assert cliente.logo_etiqueta is None
        assert cliente.logo_mimetype is None


def test_subir_logo_de_mas_de_1mb_se_rechaza(logged_client, app):
    with app.app_context():
        from app import Cliente
        pedido = _crear_pedido_con_linea(unidades_por_caja=24)
        cliente_id = pedido.cliente_id

        resp = _editar_cliente(
            logged_client, cliente_id,
            logo=(BytesIO(_png_grande()), 'enorme.png'),
        )

        assert resp.status_code == 200
        cliente = _db.session.get(Cliente, cliente_id)
        assert cliente.logo_etiqueta is None


def test_subir_logo_no_pisa_el_guardado_si_falla(logged_client, app):
    """Un archivo inválido deja intacto el logo que ya tenía el cliente."""
    with app.app_context():
        from app import Cliente
        png = _png_bytes()
        pedido = _crear_pedido_con_linea(
            unidades_por_caja=24, cliente_logo=png, cliente_mimetype='image/png',
        )
        cliente_id = pedido.cliente_id

        _editar_cliente(
            logged_client, cliente_id,
            logo=(BytesIO(b'no soy imagen'), 'falso.png'),
        )

        cliente = _db.session.get(Cliente, cliente_id)
        assert cliente.logo_etiqueta == png
        assert cliente.logo_mimetype == 'image/png'


def test_quitar_logo_borra_las_dos_columnas(logged_client, app):
    with app.app_context():
        from app import Cliente
        pedido = _crear_pedido_con_linea(
            unidades_por_caja=24,
            cliente_logo=_png_bytes(), cliente_mimetype='image/png',
        )
        cliente_id = pedido.cliente_id

        resp = _editar_cliente(logged_client, cliente_id, quitar_logo='1')

        assert resp.status_code == 200
        cliente = _db.session.get(Cliente, cliente_id)
        assert cliente.logo_etiqueta is None
        assert cliente.logo_mimetype is None


# === Vista previa del logo ===

def test_ver_logo_devuelve_la_imagen_con_nosniff(logged_client, app):
    with app.app_context():
        pedido = _crear_pedido_con_linea(
            unidades_por_caja=24,
            cliente_logo=_png_bytes(), cliente_mimetype='image/png',
        )

        resp = logged_client.get(f'/clientes/{pedido.cliente_id}/logo')

        assert resp.status_code == 200
        assert resp.headers['Content-Type'] == 'image/png'
        assert resp.headers['X-Content-Type-Options'] == 'nosniff'


def test_ver_logo_de_cliente_sin_logo_da_404(logged_client, app):
    with app.app_context():
        pedido = _crear_pedido_con_linea(unidades_por_caja=24)

        resp = logged_client.get(f'/clientes/{pedido.cliente_id}/logo')

        assert resp.status_code == 404


def test_ver_logo_de_cliente_ajeno_da_403(app):
    """Un vendedor sin acceso a ese cliente no puede ver su logo."""
    with app.app_context():
        from app import Rol, Vendedor, Territorio

        pedido = _crear_pedido_con_linea(
            unidades_por_caja=24,
            cliente_logo=_png_bytes(), cliente_mimetype='image/png',
        )

        rol_vend = Rol(nombre='vendedor', descripcion='Vendedor')
        _db.session.add(rol_vend)
        _db.session.flush()
        ajeno = Vendedor(
            username='ajeno', email='ajeno@test.com', nombre_completo='Ajeno',
            rol_id=rol_vend.id, territorio_id=Territorio.query.first().id,
            activo=True,
        )
        ajeno.set_password('testpass')
        _db.session.add(ajeno)
        _db.session.commit()

        client = flask_app.test_client()
        client.post('/login', data={'username': 'ajeno', 'password': 'testpass'},
                    follow_redirects=True)

        resp = client.get(f'/clientes/{pedido.cliente_id}/logo')

        assert resp.status_code == 403


# === Pantalla de Facturación ===

@patch('app.draw_order_label_a4')
def test_etiqueta_de_facturacion_usa_label_utils_y_el_logo_del_cliente(mock_draw, logged_client, app):
    """La etiqueta de Facturación se dibuja con label_utils y el logo del cliente."""
    from reportlab.lib.utils import ImageReader

    with app.app_context():
        from app import Facturacion, Cliente, Producto

        pedido = _crear_pedido_con_linea(
            unidades_por_caja=24,
            cliente_logo=_png_bytes(), cliente_mimetype='image/png',
        )
        cliente = _db.session.get(Cliente, pedido.cliente_id)
        producto = Producto.query.first()
        _db.session.add(Facturacion(
            producto_id=producto.id, cliente_id=cliente.id, peso=1.5,
            lote='L001', fecha_fabricacion='2026-01-15',
            fecha_expiracion='2026-06-15',
        ))
        _db.session.commit()

        resp = logged_client.post('/generar_etiqueta', data={
            'cliente': cliente.nombre,
            'fecha_inicio': '2026-01-01',
            'fecha_fin': '2026-12-31',
        })

        assert resp.status_code == 200
        assert mock_draw.call_count == 1
        args, _kwargs = mock_draw.call_args
        assert isinstance(args[1], ImageReader)


def test_form_de_cliente_permite_subir_el_logo(logged_client, app):
    """El form necesita enctype multipart, el campo de archivo y el de quitar.

    Sin enctype el navegador manda solo el nombre del archivo y el logo nunca
    llega, aunque el POST responda 200.
    """
    with app.app_context():
        pedido = _crear_pedido_con_linea(
            unidades_por_caja=24,
            cliente_logo=_png_bytes(), cliente_mimetype='image/png',
        )

        resp = logged_client.get(f'/clientes/{pedido.cliente_id}/editar')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert 'enctype="multipart/form-data"' in html
        assert 'name="logo"' in html
        assert 'name="quitar_logo"' in html
        # Vista previa del logo actual
        assert f'/clientes/{pedido.cliente_id}/logo' in html
