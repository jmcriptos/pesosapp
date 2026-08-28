"""Tests for pedido_a_json payload structure — specifically that it emits
one line per CajaPesada so N8N can reconstruct individual box weights
in the QBO invoice Description column.
"""
import os
from datetime import date, datetime
from decimal import Decimal

import pytest

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
        yield flask_app
        _db.drop_all()


def _build_pedido_pesable_con_cajas(app, pesos):
    """Crea un pedido con 1 producto pesable y N CajaPesada con los pesos
    indicados. Devuelve (pedido, producto) dentro del app_context activo."""
    from app import (
        Rol, Territorio, Vendedor, Cliente, Producto,
        Pedido, DetallePedido, CajaPesada,
    )

    rol = Rol(nombre='super_admin', descripcion='Admin')
    _db.session.add(rol)
    territorio = Territorio(nombre='t1', descripcion='T1')
    _db.session.add(territorio)
    _db.session.flush()

    vendedor = Vendedor(
        username='tester', email='t@test.com', nombre_completo='Tester',
        rol_id=rol.id, territorio_id=territorio.id, activo=True,
    )
    vendedor.set_password('x')
    _db.session.add(vendedor)

    cliente = Cliente(
        nombre='Cliente QBO', territorio_id=territorio.id, qbo_id='QBO-C1',
    )
    _db.session.add(cliente)

    producto = Producto(
        nombre='Atún Van Camps 170g', descripcion='Atún', temperatura='Seco',
        se_pesa=True, tax_rate=6.0, qbo_id='QBO-P1',
    )
    _db.session.add(producto)
    _db.session.flush()

    pedido = Pedido(cliente_id=cliente.id, estado='preparado', tipo_cambio=1.0)
    _db.session.add(pedido)
    _db.session.flush()

    detalle = DetallePedido(
        pedido_id=pedido.id,
        producto_id=producto.id,
        cajas=len(pesos),
        cajas_pedidas=len(pesos),
        peso=0,
        precio_unitario=Decimal('10.00'),
        subtotal=Decimal('0'),
        es_linea_pedido=True,
    )
    _db.session.add(detalle)
    _db.session.flush()

    for idx, peso in enumerate(pesos, start=1):
        caja = CajaPesada(
            detalle_pedido_id=detalle.id,
            numero=idx,
            peso=Decimal(str(peso)),
            lote=f'L{idx}',
            fecha_elaboracion=date(2026, 1, 1),
            fecha_vencimiento=date(2026, 6, 1),
            pesado_por=vendedor.id,
            pesado_en=datetime(2026, 4, 22, 12, 0, 0),
        )
        _db.session.add(caja)
    _db.session.commit()
    return pedido, producto


def test_pedido_a_json_emite_una_linea_por_caja(app):
    """Cada CajaPesada debe producir una línea independiente en el payload
    con qty=peso de esa caja, preservando el orden por `numero`."""
    from app import pedido_a_json

    with app.app_context():
        pesos = [2.50, 3.10, 2.80]
        pedido, producto = _build_pedido_pesable_con_cajas(app, pesos)

        payload = pedido_a_json(pedido)

        assert len(payload['lines']) == 3, (
            f"Esperaba 3 líneas (una por caja), recibí {len(payload['lines'])}"
        )
        qtys = [line['qty'] for line in payload['lines']]
        assert qtys == pesos, f"Pesos en orden esperado={pesos}, recibido={qtys}"

        for line in payload['lines']:
            assert line['product_qbo_id'] == producto.qbo_id
            assert line['unit_price'] == 10.00
            assert line['descripcion'] == producto.nombre


def test_pedido_a_json_total_y_amounts_coinciden(app):
    """El total del payload debe ser sum(peso_i * precio_unitario) y cada
    `amount` debe ser qty * unit_price redondeado a 2 decimales."""
    from app import pedido_a_json

    with app.app_context():
        pesos = [2.50, 3.10, 2.80]
        pedido, _producto = _build_pedido_pesable_con_cajas(app, pesos)

        payload = pedido_a_json(pedido)

        expected_amounts = [round(p * 10.00, 2) for p in pesos]
        assert [line['amount'] for line in payload['lines']] == expected_amounts
        assert payload['total'] == round(sum(expected_amounts), 2)


def _build_pedido_por_caja(unidades_por_caja, cajas, precio_por_caja='10.00'):
    """Pedido de un producto vendido POR CAJA (no se pesa), con línea original
    y línea de preparación. Devuelve el pedido dentro del app_context activo."""
    from app import (
        Rol, Territorio, Vendedor, Cliente, Producto, Pedido, DetallePedido,
    )

    rol = Rol(nombre='super_admin', descripcion='Admin')
    _db.session.add(rol)
    territorio = Territorio(nombre='t1', descripcion='T1')
    _db.session.add(territorio)
    _db.session.flush()

    vendedor = Vendedor(
        username='tester', email='t@test.com', nombre_completo='Tester',
        rol_id=rol.id, territorio_id=territorio.id, activo=True,
    )
    vendedor.set_password('x')
    _db.session.add(vendedor)

    cliente = Cliente(
        nombre='Cliente QBO', territorio_id=territorio.id, qbo_id='QBO-C1',
    )
    _db.session.add(cliente)

    producto = Producto(
        nombre='Caja Surtida', descripcion='Por caja', temperatura='4°C',
        se_pesa=False, tax_rate=6.0, qbo_id='QBO-P1',
        unidades_por_caja=unidades_por_caja,
    )
    _db.session.add(producto)
    _db.session.flush()

    pedido = Pedido(cliente_id=cliente.id, estado='preparado', tipo_cambio=1.0)
    _db.session.add(pedido)
    _db.session.flush()

    for es_linea_pedido in (True, False):
        _db.session.add(DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cajas=cajas,
            cajas_pedidas=cajas,
            peso=0,
            precio_unitario=Decimal(precio_por_caja),
            subtotal=Decimal('0'),
            lote='L1',
            fecha_fabricacion='2026-01-15',
            fecha_expiracion='2026-06-15',
            es_linea_pedido=es_linea_pedido,
        ))
    _db.session.commit()
    return pedido


def test_unidades_por_caja_no_se_filtra_a_la_facturacion(app):
    """`unidades_por_caja` es SOLO un dato de etiqueta.

    Un producto de 24 unidades por caja con 2,5 cajas se factura como 2,5
    cajas al precio por caja: qty nunca es 24 (unidades por caja) ni 60
    (unidades totales), y el importe no se multiplica por las unidades.
    """
    from app import pedido_a_json

    with app.app_context():
        pedido = _build_pedido_por_caja(unidades_por_caja=24, cajas=2.5)

        payload = pedido_a_json(pedido)

        assert len(payload['lines']) == 1
        linea = payload['lines'][0]
        assert linea['qty'] == 2.5, f"qty debe ser cajas (2.5), recibí {linea['qty']}"
        assert linea['qty'] not in (24, 60, 24.0, 60.0)
        assert linea['unit_price'] == 10.00, 'unit_price debe ser el precio POR CAJA'
        assert linea['amount'] == 25.00, 'amount = precio por caja x cajas'
        assert payload['total'] == 25.00
