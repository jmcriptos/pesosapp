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


def _login(app, username='admin', password='pw'):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': password},
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


def test_asignar_rechaza_caja_de_otro_cliente(app):
    """El servidor no puede confiar en los ids que llegan del form: un id
    cambiado a mano no puede pegar el lote de OTRO cliente a este pedido."""
    from app import CajaPesada, Cliente
    from maquila import servicios
    with app.app_context():
        _corrida_con_cajas(1)
        otro_cliente = Cliente(nombre='Otro maquilero')
        _db.session.add(otro_cliente)
        _db.session.flush()
        corrida_ajena = servicios.abrir_corrida(
            cliente_id=otro_cliente.id, producto_id=IDS['producto'],
            lote='L-AJENA', fecha_produccion=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'])
        caja_ajena = servicios.agregar_caja_producida(corrida_ajena, Decimal('10'))
        _db.session.commit()
        caja_ajena_id = caja_ajena.id

    c = _login(app)
    r = c.post(f"/maquila/asignar/{IDS['detalle_maquila']}",
               data={'corrida_caja_id': [str(caja_ajena_id)]},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        pesadas = CajaPesada.query.filter_by(
            detalle_pedido_id=IDS['detalle_maquila']).all()
        assert pesadas == []


def test_asignar_rechaza_pedido_facturado(app):
    """La cifra de un pedido facturado ya está en QuickBooks: no se puede
    seguir metiendo cajas ahí aunque el POST llegue directo."""
    from app import CajaPesada, Pedido
    with app.app_context():
        corrida = _corrida_con_cajas(2)
        ids = [c.id for c in corrida.cajas]
        pedido = _db.session.get(Pedido, IDS['pedido_maquila'])
        pedido.estado = 'facturado'
        _db.session.commit()

    c = _login(app)
    r = c.post(f"/maquila/asignar/{IDS['detalle_maquila']}",
               data={'corrida_caja_id': [str(i) for i in ids]},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        pesadas = CajaPesada.query.filter_by(
            detalle_pedido_id=IDS['detalle_maquila']).all()
        assert pesadas == []


def test_pesar_operario_no_ve_el_bloque_de_asignar(app):
    """El módulo sigue siendo solo de super_admin: un operario con permiso
    para pesar no debe ver un botón que su rol no puede usar. Sigue pesando
    a mano, que es la escotilla prevista para cuando falta producción."""
    from app import Rol, Vendedor, ClienteVendedor
    with app.app_context():
        _corrida_con_cajas(3)
        rol_operario = Rol(nombre='vendedor', descripcion='Vendedor')
        _db.session.add(rol_operario)
        _db.session.flush()
        operario = Vendedor(username='operario', email='op@t.com',
                            nombre_completo='Operario', rol_id=rol_operario.id,
                            activo=True)
        operario.set_password('pw')
        _db.session.add(operario)
        _db.session.flush()
        _db.session.add(ClienteVendedor(cliente_id=IDS['cliente'],
                                        vendedor_id=operario.id, activo=True))
        _db.session.commit()

    c = _login(app, username='operario', password='pw')
    r = c.get(f"/pedidos/{IDS['pedido_maquila']}/pesar")
    assert r.status_code == 200
    assert b'Asignar de produccion' not in r.data
    assert 'Asignar de producción'.encode() not in r.data
