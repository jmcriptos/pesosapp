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


def test_asignar_deja_rastro_en_el_historial_del_pedido(app):
    """Las tres operaciones equivalentes de app.py (caja_pesada, caja_editada,
    caja_eliminada) registran un PedidoEvento; asignar_cajas era el único
    camino por el que entraban cajas a un pedido sin dejar rastro."""
    from app import PedidoEvento
    with app.app_context():
        corrida = _corrida_con_cajas(2)
        ids = [c.id for c in corrida.cajas]
    c = _login(app)
    r = c.post(f"/maquila/asignar/{IDS['detalle_maquila']}",
               data={'corrida_caja_id': [str(i) for i in ids]},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        eventos = PedidoEvento.query.filter_by(
            pedido_id=IDS['pedido_maquila']).all()
        assert len(eventos) == 2
        assert {e.tipo for e in eventos} == {'caja_asignada'}


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


def test_asignar_rechaza_pedido_entregado(app):
    """Espejo del test de `facturado`: acá se factura ANTES de que salga el
    camión, así que `entregado` ya está en QuickBooks. Si la guarda solo mira
    `facturado`, marcar la entrega vuelve a abrir el pedido para meterle
    cajas y la factura deja de cuadrar con lo que se despachó."""
    from app import CajaPesada, Pedido
    with app.app_context():
        corrida = _corrida_con_cajas(2)
        ids = [c.id for c in corrida.cajas]
        pedido = _db.session.get(Pedido, IDS['pedido_maquila'])
        pedido.estado = 'entregado'
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


# ---------------------------------------------------------------------------
# Vincular cajas producidas con cajas ya pesadas a mano en un pedido
# ---------------------------------------------------------------------------


def _pesada_a_mano(detalle_id, numero, peso, lote='L-MANO', estado_pedido=None):
    """Una CajaPesada tecleada en pesar, sin pasar por «Asignar de producción»."""
    from app import CajaPesada, DetallePedido
    pesada = CajaPesada(detalle_pedido_id=detalle_id, numero=numero,
                        peso=Decimal(str(peso)), lote=lote,
                        fecha_elaboracion=date(2026, 9, 1),
                        fecha_vencimiento=date(2026, 12, 1),
                        pesado_por=IDS['vendedor'])
    _db.session.add(pesada)
    if estado_pedido:
        _db.session.get(DetallePedido, detalle_id).pedido.estado = estado_pedido
    _db.session.commit()
    return pesada.id


def test_vincular_ata_la_caja_producida_a_la_pesada_sin_tocar_el_pedido(app):
    """El pedido ya está facturado: la caja del pedido no cambia (ni peso ni
    lote), pero la caja producida deja de estar disponible y el historial
    del pedido lo dice, con la diferencia de peso."""
    from app import CajaPesada, PedidoEvento
    from maquila import servicios
    from maquila.models import CorridaCaja
    with app.app_context():
        corrida = _corrida_con_cajas(2)
        corrida_id, caja_id, codigo = corrida.id, corrida.cajas[0].id, corrida.codigo
        pesada_id = _pesada_a_mano(IDS['detalle_maquila'], 1, '10.4',
                                   estado_pedido='facturado')
    c = _login(app)
    r = c.get(f'/maquila/corridas/{corrida_id}')
    assert r.status_code == 200
    assert b'Vincular con cajas ya pesadas' in r.data
    assert f'vinculo_{caja_id}'.encode() in r.data
    r = c.post(f'/maquila/corridas/{corrida_id}/vincular',
               data={f'vinculo_{caja_id}': str(pesada_id)}, follow_redirects=True)
    assert r.status_code == 200
    assert b'1 caja(s)' in r.data
    with app.app_context():
        caja = _db.session.get(CorridaCaja, caja_id)
        assert caja.caja_pesada_id == pesada_id
        assert not caja.disponible
        pesada = _db.session.get(CajaPesada, pesada_id)
        assert pesada.peso == Decimal('10.400') and pesada.lote == 'L-MANO'
        # Ya no se propone por FEFO: queda la otra caja de la corrida.
        assert [x.id for x in servicios.cajas_disponibles(
            IDS['cliente'], IDS['producto'])] != [caja_id]
        assert caja_id not in [x.id for x in servicios.cajas_disponibles(
            IDS['cliente'], IDS['producto'])]
        eventos = PedidoEvento.query.filter_by(pedido_id=IDS['pedido_maquila']).all()
        assert [e.tipo for e in eventos] == ['caja_vinculada']
        assert '+0.400 kg' in eventos[0].descripcion
        assert codigo in eventos[0].descripcion
        # Y la candidata desaparece de la lista para vincular.
        assert servicios.cajas_pesadas_sin_vincular(IDS['cliente'], IDS['producto']) == []


def test_vincular_rechaza_caja_de_otro_cliente_y_no_escribe_nada(app):
    from app import PedidoEvento
    from maquila.models import CorridaCaja
    with app.app_context():
        corrida = _corrida_con_cajas(1)
        corrida_id, caja_id = corrida.id, corrida.cajas[0].id
        ajena_id = _pesada_a_mano(IDS['detalle_normal'], 1, '10')
    c = _login(app)
    r = c.post(f'/maquila/corridas/{corrida_id}/vincular',
               data={f'vinculo_{caja_id}': str(ajena_id)}, follow_redirects=True)
    assert r.status_code == 200
    assert b'no es de este cliente y producto' in r.data
    with app.app_context():
        assert _db.session.get(CorridaCaja, caja_id).caja_pesada_id is None
        assert PedidoEvento.query.count() == 0


def test_vincular_rechaza_una_pesada_que_ya_viene_de_una_corrida(app):
    """Todo o nada: si una de dos filas falla, la otra tampoco se escribe."""
    from maquila.models import CorridaCaja
    with app.app_context():
        corrida = _corrida_con_cajas(3)
        corrida_id = corrida.id
        c0, c1, c2 = [x.id for x in corrida.cajas]
        p1 = _pesada_a_mano(IDS['detalle_maquila'], 1, '10')
        p2 = _pesada_a_mano(IDS['detalle_maquila'], 2, '10')
    c = _login(app)
    r = c.post(f'/maquila/corridas/{corrida_id}/vincular',
               data={f'vinculo_{c0}': str(p1)}, follow_redirects=True)
    assert r.status_code == 200
    r = c.post(f'/maquila/corridas/{corrida_id}/vincular',
               data={f'vinculo_{c1}': str(p2), f'vinculo_{c2}': str(p1)},
               follow_redirects=True)
    assert r.status_code == 200
    assert b'ya viene de' in r.data
    with app.app_context():
        assert _db.session.get(CorridaCaja, c0).caja_pesada_id == p1
        assert _db.session.get(CorridaCaja, c1).caja_pesada_id is None
        assert _db.session.get(CorridaCaja, c2).caja_pesada_id is None


def test_vincular_ignora_filas_vacias_y_exige_al_menos_una(app):
    with app.app_context():
        corrida = _corrida_con_cajas(1)
        corrida_id, caja_id = corrida.id, corrida.cajas[0].id
        _pesada_a_mano(IDS['detalle_maquila'], 1, '10')
    c = _login(app)
    r = c.post(f'/maquila/corridas/{corrida_id}/vincular',
               data={f'vinculo_{caja_id}': ''}, follow_redirects=True)
    assert r.status_code == 200
    assert b'al menos una caja' in r.data


def test_sin_cajas_pesadas_a_mano_el_detalle_no_ofrece_vincular(app):
    with app.app_context():
        corrida = _corrida_con_cajas(1)
        corrida_id = corrida.id
    c = _login(app)
    r = c.get(f'/maquila/corridas/{corrida_id}')
    assert r.status_code == 200
    assert b'Vincular con cajas ya pesadas' not in r.data


def test_vincular_es_solo_de_super_admin(app):
    from app import Rol, Vendedor
    with app.app_context():
        rv = Rol(nombre='vendedor', descripcion='Vendedor')
        _db.session.add(rv)
        _db.session.flush()
        v = Vendedor(username='vend', email='v@t.com', nombre_completo='Vend',
                     rol_id=rv.id, territorio_id=1, activo=True)
        v.set_password('pw')
        _db.session.add(v)
        _db.session.commit()
        corrida = _corrida_con_cajas(1)
        corrida_id = corrida.id
    c = _login(app, 'vend')
    r = c.post(f'/maquila/corridas/{corrida_id}/vincular', data={},
               follow_redirects=False)
    assert r.status_code == 302
