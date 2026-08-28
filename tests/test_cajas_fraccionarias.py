# tests/test_cajas_fraccionarias.py
"""Cantidades fraccionarias de caja (media caja, cuarto de caja).

Clientes piden fracciones de caja (media caja de atún, media de cooked
shoulder). El form y el backend deben aceptar múltiplos de 0.25 desde 0.25,
manteniendo correcto todo lo de aguas abajo: subtotales, línea de preparación,
payload de factura, objetivo de pesaje y precarga habitual.
"""
import os
import pytest
from datetime import datetime, timedelta
from decimal import Decimal

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

        _db.session.add(Cliente(
            nombre='Toko Grandi', territorio_id=territorio.id, qbo_id='77',
        ))

        _db.session.add(Producto(
            nombre='Atun Van Camps agua 48 x 160 g', descripcion='x',
            temperatura='Seco', se_pesa=False, tax_rate=10.0, qbo_id='201',
        ))
        _db.session.add(Producto(
            nombre='Cooked Shoulder 500 g', descripcion='x',
            temperatura='Congelado', se_pesa=True, tax_rate=10.0, qbo_id='202',
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


def _ids():
    from app import Cliente, Producto
    cliente = Cliente.query.filter_by(nombre='Toko Grandi').first()
    importado = Producto.query.filter_by(se_pesa=False).first()
    pesable = Producto.query.filter_by(se_pesa=True).first()
    return cliente.id, importado.id, pesable.id


# ── Parser compartido ──────────────────────────────────────────────


def test_parse_cajas_acepta_fracciones_de_cuarto(app):
    from app import _parse_cajas
    assert _parse_cajas('0.5') == 0.5
    assert _parse_cajas('0.25') == 0.25
    assert _parse_cajas('1.75') == 1.75
    assert _parse_cajas('3') == 3.0
    # Teclado decimal de iOS en locale holandés escribe coma.
    assert _parse_cajas('0,5') == 0.5


def test_parse_cajas_rechaza_valores_invalidos(app):
    from app import _parse_cajas
    for malo in ('0.3', '0', '-1', 'abc', '', None, '10000', '0.1'):
        with pytest.raises(ValueError):
            _parse_cajas(malo)


# ── Crear / editar pedido ──────────────────────────────────────────


def test_crear_pedido_con_media_caja_importado(app, logged_client):
    from app import Pedido, DetallePedido
    cliente_id, importado_id, _ = _ids()

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id,
        'notas': '',
        'productos[0][id]': importado_id,
        'productos[0][cajas]': '0.5',
        'productos[0][precio]': '13.00',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        pedido = Pedido.query.first()
        assert pedido is not None

        original = DetallePedido.query.filter_by(
            pedido_id=pedido.id, es_linea_pedido=True).one()
        assert original.cajas == pytest.approx(0.5)
        assert original.cajas_pedidas == pytest.approx(0.5)
        assert float(original.subtotal) == pytest.approx(6.50)

        # La línea de preparación auto-generada para importados copia la
        # cantidad fraccionaria.
        prep = DetallePedido.query.filter_by(
            pedido_id=pedido.id, es_linea_pedido=False).one()
        assert prep.cajas == pytest.approx(0.5)
        assert float(prep.subtotal) == pytest.approx(6.50)


def test_crear_pedido_rechaza_fraccion_que_no_es_cuarto(app, logged_client):
    from app import Pedido
    cliente_id, importado_id, _ = _ids()

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id,
        'notas': '',
        'productos[0][id]': importado_id,
        'productos[0][cajas]': '0.3',
        'productos[0][precio]': '13.00',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'cuarto' in resp.data

    with app.app_context():
        assert Pedido.query.count() == 0


def test_editar_pedido_a_media_caja(app, logged_client):
    from app import Pedido, DetallePedido
    cliente_id, importado_id, _ = _ids()

    logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id,
        'notas': '',
        'productos[0][id]': importado_id,
        'productos[0][cajas]': '2',
        'productos[0][precio]': '13.00',
    }, follow_redirects=True)

    with app.app_context():
        pedido_id = Pedido.query.first().id

    resp = logged_client.post(f'/pedidos/{pedido_id}/editar', data={
        'cliente_id': cliente_id,
        'notas': '',
        'productos[0][id]': importado_id,
        'productos[0][cajas]': '0.5',
        'productos[0][precio]': '13.00',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        original = DetallePedido.query.filter_by(
            pedido_id=pedido_id, es_linea_pedido=True).one()
        assert original.cajas == pytest.approx(0.5)
        assert original.cajas_pedidas == pytest.approx(0.5)
        assert float(original.subtotal) == pytest.approx(6.50)


# ── Pesaje: el objetivo de cajas físicas se redondea hacia arriba ──


def test_cajas_objetivo_redondea_hacia_arriba(app):
    from app import DetallePedido
    assert DetallePedido(cajas_pedidas=0.5).cajas_objetivo == 1
    assert DetallePedido(cajas_pedidas=2.5).cajas_objetivo == 3
    assert DetallePedido(cajas_pedidas=3).cajas_objetivo == 3
    assert DetallePedido(cajas_pedidas=0, cajas=1.25).cajas_objetivo == 2
    assert DetallePedido(cajas_pedidas=0, cajas=0).cajas_objetivo == 0


# ── Factura (payload N8N/QBO) ──────────────────────────────────────


def test_pedido_a_json_media_caja_importado(app):
    from app import Pedido, DetallePedido, pedido_a_json
    cliente_id, importado_id, _ = _ids()

    with app.app_context():
        pedido = Pedido(cliente_id=cliente_id, fecha_pedido=datetime.utcnow())
        _db.session.add(pedido)
        _db.session.flush()
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=importado_id,
            cajas=0.5, cajas_pedidas=0.5,
            precio_unitario=Decimal('13.00'), subtotal=Decimal('6.50'),
            es_linea_pedido=True,
        ))
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=importado_id,
            cajas=0.5, cajas_pedidas=0,
            precio_unitario=Decimal('13.00'), subtotal=Decimal('6.50'),
            es_linea_pedido=False,
        ))
        _db.session.commit()

        payload = pedido_a_json(pedido)
        assert len(payload['lines']) == 1
        linea = payload['lines'][0]
        assert linea['qty'] == pytest.approx(0.5)
        assert linea['amount'] == pytest.approx(6.50)
        assert payload['total'] == pytest.approx(6.50)


# ── Modal de detalles (cajas viajan en el campo peso) ──────────────


def test_actualizar_detalle_media_caja_sincroniza_original(app, logged_client):
    from app import Pedido, DetallePedido
    cliente_id, importado_id, _ = _ids()

    logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id,
        'notas': '',
        'productos[0][id]': importado_id,
        'productos[0][cajas]': '2',
        'productos[0][precio]': '13.00',
    }, follow_redirects=True)

    with app.app_context():
        pedido_id = Pedido.query.first().id
        prep_id = DetallePedido.query.filter_by(
            pedido_id=pedido_id, es_linea_pedido=False).one().id

    resp = logged_client.post(f'/detalles_pedido/{prep_id}/editar', data={
        'producto_id': importado_id,
        'peso': '0.5',   # el modal manda cajas en el campo peso
        # Obligatorios también para productos por caja desde 2026-08-28: la
        # etiqueta los imprime y sin ellos la línea no genera etiqueta.
        'lote': 'L-TEST',
        'fecha_fabricacion': '2026-08-01',
        'fecha_expiracion': '2026-12-31',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        prep = DetallePedido.query.get(prep_id)
        assert prep.cajas == pytest.approx(0.5)
        assert float(prep.subtotal) == pytest.approx(6.50)

        original = DetallePedido.query.filter_by(
            pedido_id=pedido_id, es_linea_pedido=True).one()
        assert original.cajas == pytest.approx(0.5)
        assert original.cajas_pedidas == pytest.approx(0.5)
        assert float(original.subtotal) == pytest.approx(6.50)


def test_actualizar_detalle_rechaza_fraccion_invalida(app, logged_client):
    from app import Pedido, DetallePedido
    cliente_id, importado_id, _ = _ids()

    logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id,
        'notas': '',
        'productos[0][id]': importado_id,
        'productos[0][cajas]': '2',
        'productos[0][precio]': '13.00',
    }, follow_redirects=True)

    with app.app_context():
        pedido_id = Pedido.query.first().id
        prep_id = DetallePedido.query.filter_by(
            pedido_id=pedido_id, es_linea_pedido=False).one().id

    resp = logged_client.post(f'/detalles_pedido/{prep_id}/editar', data={
        'producto_id': importado_id,
        'peso': '0.3',
        # Obligatorios también para productos por caja desde 2026-08-28: la
        # etiqueta los imprime y sin ellos la línea no genera etiqueta.
        'lote': 'L-TEST',
        'fecha_fabricacion': '2026-08-01',
        'fecha_expiracion': '2026-12-31',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'cuarto' in resp.data

    with app.app_context():
        # Nada cambió: ni la prep ni la original.
        assert DetallePedido.query.get(prep_id).cajas == pytest.approx(2)


# ── Precarga habitual ──────────────────────────────────────────────


def test_habitual_respeta_media_caja(app, logged_client):
    """Un cliente que siempre pide media caja precarga 0.5, no 1."""
    from app import Pedido, DetallePedido
    cliente_id, importado_id, _ = _ids()

    with app.app_context():
        for dias in (14, 7):
            pedido = Pedido(
                cliente_id=cliente_id,
                fecha_pedido=datetime.utcnow() - timedelta(days=dias),
            )
            _db.session.add(pedido)
            _db.session.flush()
            _db.session.add(DetallePedido(
                pedido_id=pedido.id, producto_id=importado_id,
                cajas=0.5, cajas_pedidas=0.5,
                precio_unitario=Decimal('13.00'), subtotal=Decimal('6.50'),
                es_linea_pedido=True,
            ))
        _db.session.commit()

    datos = logged_client.get(
        f'/api/clientes/{cliente_id}/pedido-habitual').get_json()
    assert len(datos['lineas']) == 1
    assert datos['lineas'][0]['cajas'] == pytest.approx(0.5)


def test_mediana_cajas_enteros_se_comporta_como_hoy(app):
    from app import _mediana_cajas, _mediana_int
    for valores in ([5], [2, 3], [5, 5, 40], [1, 2, 3, 4]):
        assert _mediana_cajas(valores) == _mediana_int(valores)
        assert isinstance(_mediana_cajas(valores), int)


def test_mediana_cajas_fracciones_redondea_al_cuarto(app):
    from app import _mediana_cajas
    assert _mediana_cajas([0.5, 0.5, 0.5]) == pytest.approx(0.5)
    assert _mediana_cajas([0.5, 1.0]) == pytest.approx(0.75)
    assert _mediana_cajas([0.5, 0.5, 3]) == pytest.approx(0.5)


# ── Display ────────────────────────────────────────────────────────


def test_fmt_cajas(app):
    from app import _fmt_cajas
    assert _fmt_cajas(3) == '3'
    assert _fmt_cajas(3.0) == '3'
    assert _fmt_cajas(0.5) == '0.5'
    assert _fmt_cajas(1.75) == '1.75'
    assert _fmt_cajas(None) == '0'
