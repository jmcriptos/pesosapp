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
