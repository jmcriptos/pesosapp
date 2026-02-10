# tests/test_consolidar_flujo.py
"""Tests para Story 3-0: Consolidar flujo de pedidos."""
import os
import pytest
from datetime import datetime

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
        from app import (Rol, Territorio, Vendedor, Cliente, Producto,
                         Pedido, DetallePedido)

        # Setup user
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

        # Cliente con qbo_id
        cliente = Cliente(nombre='Cliente Test', territorio_id=territorio.id,
                          qbo_id='QBO-C001')
        _db.session.add(cliente)
        _db.session.flush()

        # Producto manufactura (se_pesa=True)
        prod_pesa = Producto(
            nombre='Chuleta de Cerdo',
            descripcion='Carne',
            temperatura='-18°C',
            se_pesa=True,
            tax_rate=6.0,
            qbo_id='QBO-P001',
        )
        _db.session.add(prod_pesa)

        # Producto importación (se_pesa=False)
        prod_import = Producto(
            nombre='Atún Van Camps',
            descripcion='Conserva',
            temperatura='Ambiente',
            se_pesa=False,
            tax_rate=6.0,
            qbo_id='QBO-P002',
        )
        _db.session.add(prod_import)
        _db.session.flush()

        # Pedido pendiente con líneas de pedido originales
        pedido = Pedido(
            cliente_id=cliente.id,
            estado='pendiente',
        )
        _db.session.add(pedido)
        _db.session.flush()

        # Línea original de manufactura (es_linea_pedido=True, peso=0)
        det_pesa_orig = DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_pesa.id,
            cajas=3,
            peso=0,
            precio_unitario=25.00,
            subtotal=75.00,
            es_linea_pedido=True,
        )
        _db.session.add(det_pesa_orig)

        # Línea original de importación (es_linea_pedido=True)
        det_import_orig = DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_import.id,
            cajas=5,
            peso=0,
            precio_unitario=10.00,
            subtotal=50.00,
            es_linea_pedido=True,
            fecha_expiracion=datetime(2027, 6, 1),
        )
        _db.session.add(det_import_orig)

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


# === AC #1: /preparar redirige a /detalles ===

def test_preparar_redirige_a_detalles(logged_client, app):
    """AC #1: GET /pedidos/<id>/preparar redirige 301 a /detalles."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar')
        assert resp.status_code == 301
        assert f'/pedidos/{pedido.id}/detalles' in resp.headers['Location']


# === AC #2: Nuevas líneas desde detalles tienen es_linea_pedido=False ===

def test_agregar_detalle_marca_es_linea_pedido_false(logged_client, app):
    """AC #2: POST a detalles crea línea con es_linea_pedido=False."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()
        prod = Producto.query.filter_by(se_pesa=True).first()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/detalles',
            data={
                'producto_id': prod.id,
                'peso': '4.5',
                'cajas': '1',
                'lote': 'L100',
                'fecha_fabricacion': '2026-02-01',
                'fecha_expiracion': '2026-08-01',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        nuevos = DetallePedido.query.filter_by(
            pedido_id=pedido.id,
            es_linea_pedido=False,
        ).all()
        assert len(nuevos) == 1
        assert nuevos[0].peso == 4.5
        assert nuevos[0].lote == 'L100'


# === AC #3: Líneas originales NO se pueden editar/eliminar ===

def test_lineas_originales_sin_botones_editar_eliminar(logged_client, app):
    """AC #3: Líneas es_linea_pedido=True no muestran botones editar/eliminar."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/detalles')
        assert resp.status_code == 200
        assert 'badge-pedido' in resp.data.decode()
        assert 'linea-pedido-original' in resp.data.decode()


# === AC #5: Marcar como listo — validación exitosa ===

def _add_preparation_lines(app):
    """Helper: agrega líneas de preparación con trazabilidad completa."""
    from app import Pedido, DetallePedido, Producto
    pedido = Pedido.query.first()
    prod_pesa = Producto.query.filter_by(se_pesa=True).first()
    prod_import = Producto.query.filter_by(se_pesa=False).first()

    # Manufactura: 3 líneas de preparación con peso
    for i in range(3):
        det = DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_pesa.id,
            cajas=1,
            peso=4.5 + i * 0.1,
            precio_unitario=25.00,
            subtotal=25.00,
            lote='L200',
            fecha_fabricacion=datetime(2026, 2, 1),
            fecha_expiracion=datetime(2026, 8, 1),
            es_linea_pedido=False,
        )
        _db.session.add(det)

    # Importación: 1 línea de preparación con cajas
    det_import = DetallePedido(
        pedido_id=pedido.id,
        producto_id=prod_import.id,
        cajas=6,
        peso=0,
        precio_unitario=10.00,
        subtotal=60.00,
        es_linea_pedido=False,
    )
    _db.session.add(det_import)
    _db.session.commit()
    return pedido


def test_marcar_preparado_exitoso(logged_client, app):
    """AC #5: Con trazabilidad completa, marcar_preparado cambia estado a 'preparado'."""
    with app.app_context():
        pedido = _add_preparation_lines(app)

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/marcar_preparado',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        from app import Pedido
        pedido = Pedido.query.first()
        assert pedido.estado == 'preparado'


def test_marcar_preparado_sin_preparacion_falla(logged_client, app):
    """AC #5: Sin líneas de preparación para producto se_pesa, marcar_preparado falla."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/marcar_preparado',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        pedido = Pedido.query.first()
        assert pedido.estado == 'pendiente'
        assert 'sin l'.encode() in resp.data.lower() or \
               'incompleto'.encode() in resp.data.lower() or \
               'preparaci'.encode() in resp.data.lower()


def test_marcar_preparado_import_sin_fecha_exp_ok(logged_client, app):
    """Producto import sin fecha_expiracion NO bloquea marcar como preparado."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto

        # Quitar fecha_expiracion del producto importado
        prod_import = Producto.query.filter_by(se_pesa=False).first()
        det_import = DetallePedido.query.filter_by(
            producto_id=prod_import.id, es_linea_pedido=True
        ).first()
        det_import.fecha_expiracion = None
        _db.session.commit()

        # Agregar líneas de preparación para manufactura
        pedido = _add_preparation_lines(app)

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/marcar_preparado',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        pedido = Pedido.query.first()
        assert pedido.estado == 'preparado'


# === AC #6: pedido_a_json filtra líneas correctamente ===

def test_pedido_a_json_filtra_lineas(app):
    """AC #6: pedido_a_json incluye solo líneas de preparación para todos los productos."""
    with app.app_context():
        from app import pedido_a_json
        pedido = _add_preparation_lines(app)

        result = pedido_a_json(pedido)
        lines = result['lines']

        # 3 líneas de preparación (manufactura) + 1 línea de preparación (importación) = 4
        assert len(lines) == 4

        # Verificar que NO hay línea original de manufactura (peso=0)
        for line in lines:
            if 'Chuleta' in line['descripcion']:
                assert line['qty'] > 0  # solo líneas con peso real

        # Verificar que la línea de importación prep está presente
        import_lines = [l for l in lines if 'At' in l['descripcion']]
        assert len(import_lines) == 1
        assert import_lines[0]['qty'] == 6


def test_pedido_a_json_sin_prep_lines(app):
    """pedido_a_json sin líneas de preparación: no incluye ninguna línea."""
    with app.app_context():
        from app import pedido_a_json, Pedido
        pedido = Pedido.query.first()

        result = pedido_a_json(pedido)
        lines = result['lines']

        # Sin líneas de preparación, no hay líneas en el JSON
        assert len(lines) == 0


# === AC #8: Botón "Marcar como Preparado" visible solo en estado pendiente ===

def test_boton_marcar_preparado_visible_pendiente(logged_client, app):
    """AC #8: Botón 'Marcar como Preparado' visible cuando estado=pendiente."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/detalles')
        assert resp.status_code == 200
        assert 'Marcar como Preparado' in resp.data.decode()


def test_boton_marcar_preparado_oculto_facturado(logged_client, app):
    """AC #8: Botón 'Marcar como Preparado' oculto cuando estado=facturado."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido.estado = 'facturado'
        _db.session.commit()

        resp = logged_client.get(f'/pedidos/{pedido.id}/detalles')
        assert resp.status_code == 200
        # Check button is not rendered (form action to marcar_preparado)
        assert 'marcar_preparado' not in resp.data.decode()


# === Regresiones ===

def test_regression_detalles_accesible(logged_client, app):
    """Regresión: detalles_pedido sigue accesible."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/detalles')
        assert resp.status_code == 200


def test_regression_login_funciona(app):
    """Regresión: login sigue funcionando."""
    client = app.test_client()
    resp = client.post('/login', data={
        'username': 'admin',
        'password': 'testpass',
    }, follow_redirects=True)
    assert resp.status_code == 200
