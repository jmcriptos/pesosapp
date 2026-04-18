# tests/test_pesar.py
import os
from datetime import date
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
        from app import Rol, Territorio, Vendedor, Cliente, Producto, Pedido, DetallePedido

        rol = Rol(nombre='super_admin', descripcion='Admin')
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add_all([rol, territorio])
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

        cliente = Cliente(nombre='Cliente Test', territorio_id=territorio.id, qbo_id='QBO-C001')
        _db.session.add(cliente)
        _db.session.flush()

        prod_pesa = Producto(
            nombre='Chuleta de Cerdo',
            descripcion='Carne',
            temperatura='-18°C',
            se_pesa=True,
            tax_rate=6.0,
            qbo_id='QBO-P001',
        )
        prod_import = Producto(
            nombre='Atún Van Camps',
            descripcion='Conserva',
            temperatura='Ambiente',
            se_pesa=False,
            tax_rate=6.0,
            qbo_id='QBO-P002',
        )
        _db.session.add_all([prod_pesa, prod_import])
        _db.session.flush()

        pedido = Pedido(cliente_id=cliente.id, estado='pendiente')
        _db.session.add(pedido)
        _db.session.flush()

        _db.session.add(DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_pesa.id,
            cajas=3,
            cajas_pedidas=3,
            peso=0,
            precio_unitario=Decimal('25.00'),
            subtotal=Decimal('75.00'),
            es_linea_pedido=True,
        ))
        _db.session.add(DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_import.id,
            cajas=5,
            cajas_pedidas=5,
            peso=0,
            precio_unitario=Decimal('10.00'),
            subtotal=Decimal('50.00'),
            es_linea_pedido=True,
        ))
        _db.session.add(DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_import.id,
            cajas=5,
            cajas_pedidas=0,
            peso=0,
            precio_unitario=Decimal('10.00'),
            subtotal=Decimal('50.00'),
            es_linea_pedido=False,
            fecha_expiracion='2027-06-01',
        ))

        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'}, follow_redirects=True)
    return client


def test_pesar_screen_loads(logged_client, app):
    with app.app_context():
        from app import Pedido

        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/pesar')
        html = resp.data.decode('utf-8')

        assert resp.status_code == 200
        assert 'Pesar PED-' in html
        assert 'Chuleta de Cerdo' in html
        assert 'cajas-list-producto-' in html


def test_registrar_caja_pesada(logged_client, app):
    with app.app_context():
        from app import Pedido, DetallePedido, CajaPesada

        pedido = Pedido.query.first()
        detalle = DetallePedido.query.filter_by(pedido_id=pedido.id, es_linea_pedido=True).join(DetallePedido.producto).filter_by(se_pesa=True).first()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/pesar/caja',
            data={
                'detalle_pedido_id': detalle.id,
                'peso': '12.450',
                'lote': 'L-2643',
                'fecha_elaboracion': '2026-04-18',
                'fecha_vencimiento': '2027-04-18',
            },
            headers={'HX-Request': 'true'},
        )

        assert resp.status_code == 200
        caja = CajaPesada.query.filter_by(detalle_pedido_id=detalle.id).one()
        assert caja.numero == 1
        assert caja.lote == 'L-2643'
        assert float(caja.peso) == pytest.approx(12.45)


def test_finalizar_pesaje_marca_pedido_preparado(logged_client, app):
    with app.app_context():
        from app import Pedido, DetallePedido, CajaPesada

        pedido = Pedido.query.first()
        detalle = DetallePedido.query.filter_by(pedido_id=pedido.id, es_linea_pedido=True).join(DetallePedido.producto).filter_by(se_pesa=True).first()

        for idx, peso in enumerate([11.1, 12.2, 13.3], start=1):
            _db.session.add(CajaPesada(
                detalle_pedido_id=detalle.id,
                numero=idx,
                peso=Decimal(str(peso)),
                lote='L-2643',
                fecha_elaboracion=date(2026, 4, 18),
                fecha_vencimiento=date(2027, 4, 18),
            ))
        _db.session.commit()

        resp = logged_client.post(f'/pedidos/{pedido.id}/pesar/finalizar', follow_redirects=True)
        assert resp.status_code == 200

        pedido = Pedido.query.first()
        assert pedido.estado == 'preparado'
