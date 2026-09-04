"""La asignación FEFO dentro de pesar, sin molestar a quien no hace maquila."""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import (Rol, Territorio, Vendedor, Cliente, Producto,
                         Pedido, DetallePedido)
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        otro = Cliente(nombre='Cliente normal')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        _db.session.add_all([v, cli, otro, prod])
        _db.session.flush()
        for cliente in (cli, otro):
            p = Pedido(cliente_id=cliente.id, estado='pendiente')
            _db.session.add(p)
            _db.session.flush()
            d = DetallePedido(pedido_id=p.id, producto_id=prod.id, cajas=2,
                              cajas_pedidas=2, peso=0, precio_unitario=0,
                              subtotal=0, es_linea_pedido=True)
            _db.session.add(d)
            _db.session.flush()
            clave = 'maquila' if cliente is cli else 'normal'
            IDS[f'pedido_{clave}'] = p.id
            IDS[f'detalle_{clave}'] = d.id
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id)
        yield flask_app
        _db.drop_all()


def _login(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'pw'},
           follow_redirects=True)
    return c


def _corrida_con_cajas(n):
    from maquila import servicios
    c = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-0903',
        fecha_produccion=date(2026, 9, 1), vendedor_id=IDS['vendedor'],
        fecha_vencimiento=date(2026, 12, 1))
    for i in range(n):
        servicios.agregar_caja_producida(c, Decimal('10'))
    _db.session.commit()
    return c


def test_pesar_de_un_cliente_sin_corridas_no_cambia(app):
    """Regresión: los otros 48 clientes no deben ver nada nuevo."""
    c = _login(app)
    r = c.get(f"/pedidos/{IDS['pedido_normal']}/pesar")
    assert r.status_code == 200
    assert b'Asignar de produccion' not in r.data
    assert b'Asignar de producci' not in r.data


def test_pesar_de_un_cliente_con_corridas_ofrece_la_propuesta(app):
    with app.app_context():
        _corrida_con_cajas(3)
    c = _login(app)
    r = c.get(f"/pedidos/{IDS['pedido_maquila']}/pesar")
    assert r.status_code == 200
    assert 'Asignar de producción'.encode() in r.data


def test_asignar_crea_las_cajas_pesadas_con_su_lote(app):
    from app import CajaPesada
    with app.app_context():
        corrida = _corrida_con_cajas(3)
        ids = [c.id for c in corrida.cajas[:2]]
    c = _login(app)
    r = c.post(f"/maquila/asignar/{IDS['detalle_maquila']}",
               data={'corrida_caja_id': [str(i) for i in ids]},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        pesadas = CajaPesada.query.filter_by(
            detalle_pedido_id=IDS['detalle_maquila']).all()
        assert len(pesadas) == 2
        assert {p.lote for p in pesadas} == {'L-0903'}
        assert {p.numero for p in pesadas} == {1, 2}
