"""FEFO: sale primero lo que vence antes, y el peso viaja con su lote."""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


def _corrida(lote, vence_dia, pesos):
    from maquila import servicios
    c = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote=lote,
        fecha_produccion=date(2026, 9, 1), vendedor_id=IDS['vendedor'],
        fecha_vencimiento=date(2026, 12, vence_dia))
    for p in pesos:
        servicios.agregar_caja_producida(c, Decimal(str(p)))
    _db.session.commit()
    return c


def _pedido_con_linea(cajas_pedidas):
    from app import Pedido, DetallePedido
    p = Pedido(cliente_id=IDS['cliente'], estado='pendiente')
    _db.session.add(p)
    _db.session.flush()
    d = DetallePedido(pedido_id=p.id, producto_id=IDS['producto'],
                      cajas=cajas_pedidas, cajas_pedidas=cajas_pedidas,
                      peso=0, precio_unitario=0, subtotal=0,
                      es_linea_pedido=True)
    _db.session.add(d)
    _db.session.commit()
    return p, d


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        _db.session.add_all([v, cli, prod])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id)
        yield flask_app
        _db.drop_all()


def test_ofrece_primero_la_caja_que_vence_antes(app):
    from maquila import servicios
    with app.app_context():
        tarde = _corrida('L-TARDE', 31, [10])
        pronto = _corrida('L-PRONTO', 5, [10])
        disponibles = servicios.cajas_disponibles(IDS['cliente'], IDS['producto'])
        assert [c.corrida_id for c in disponibles] == [pronto.id, tarde.id]


def test_propone_solo_las_cajas_que_faltan(app):
    from maquila import servicios
    with app.app_context():
        _corrida('L-1', 5, [10, 10, 10, 10])
        _pedido, detalle = _pedido_con_linea(2)
        propuesta = servicios.proponer_fefo(detalle)
        assert len(propuesta) == 2


def test_asignar_copia_peso_lote_y_fechas_a_la_caja_pesada(app):
    from maquila import servicios
    with app.app_context():
        c = _corrida('L-0903', 20, [12.345])
        _pedido, detalle = _pedido_con_linea(1)
        creadas = servicios.asignar_cajas(detalle, [c.cajas[0]], IDS['vendedor'])
        assert len(creadas) == 1
        cp = creadas[0]
        assert cp.peso == Decimal('12.345')
        assert cp.lote == 'L-0903'
        assert cp.fecha_elaboracion == date(2026, 9, 1)
        assert cp.fecha_vencimiento == date(2026, 12, 20)
        assert c.cajas[0].caja_pesada_id == cp.id
        assert c.cajas[0].disponible is False


def test_una_caja_asignada_ya_no_se_ofrece(app):
    from maquila import servicios
    with app.app_context():
        c = _corrida('L-1', 5, [10, 10])
        _pedido, detalle = _pedido_con_linea(1)
        servicios.asignar_cajas(detalle, [c.cajas[0]], IDS['vendedor'])
        disponibles = servicios.cajas_disponibles(IDS['cliente'], IDS['producto'])
        assert len(disponibles) == 1
        assert disponibles[0].numero == 2


def test_no_se_puede_asignar_la_misma_caja_dos_veces(app):
    from maquila import servicios
    with app.app_context():
        c = _corrida('L-1', 5, [10])
        _p1, d1 = _pedido_con_linea(1)
        _p2, d2 = _pedido_con_linea(1)
        servicios.asignar_cajas(d1, [c.cajas[0]], IDS['vendedor'])
        with pytest.raises(servicios.CajaNoDisponible):
            servicios.asignar_cajas(d2, [c.cajas[0]], IDS['vendedor'])


def test_borrar_la_linea_del_pedido_devuelve_la_caja_al_stock(app):
    """ON DELETE SET NULL: nadie tiene que acordarse de liberar la caja."""
    from maquila import servicios
    from maquila.models import CorridaCaja
    with app.app_context():
        c = _corrida('L-1', 5, [10])
        _pedido, detalle = _pedido_con_linea(1)
        servicios.asignar_cajas(detalle, [c.cajas[0]], IDS['vendedor'])
        caja_id = c.cajas[0].id
        _db.session.delete(detalle)
        _db.session.commit()
        assert _db.session.get(CorridaCaja, caja_id).caja_pesada_id is None
        assert len(servicios.cajas_disponibles(IDS['cliente'], IDS['producto'])) == 1


def test_asignar_es_todo_o_nada_si_una_caja_del_medio_ya_no_esta(app):
    """Tres cajas, la del medio ya fue tomada por otro pedido: nada queda a medias."""
    from maquila import servicios
    from app import CajaPesada
    with app.app_context():
        c = _corrida('L-1', 5, [10, 10, 10])
        _otro_pedido, otro_detalle = _pedido_con_linea(1)
        servicios.asignar_cajas(otro_detalle, [c.cajas[1]], IDS['vendedor'])

        _pedido, detalle = _pedido_con_linea(3)
        with pytest.raises(servicios.CajaNoDisponible):
            servicios.asignar_cajas(detalle, [c.cajas[0], c.cajas[1], c.cajas[2]],
                                    IDS['vendedor'])

        assert CajaPesada.query.filter_by(detalle_pedido_id=detalle.id).count() == 0

        disponibles = servicios.cajas_disponibles(IDS['cliente'], IDS['producto'])
        assert {caja.numero for caja in disponibles} == {1, 3}


def test_llamar_asignar_cajas_dos_veces_no_repite_numero(app):
    """La numeración no puede depender de una relación cacheada."""
    from maquila import servicios
    from app import CajaPesada
    with app.app_context():
        c = _corrida('L-1', 5, [10, 10, 10, 10])
        _pedido, detalle = _pedido_con_linea(4)

        servicios.asignar_cajas(detalle, [c.cajas[0], c.cajas[1]], IDS['vendedor'])
        servicios.asignar_cajas(detalle, [c.cajas[2], c.cajas[3]], IDS['vendedor'])

        numeros = sorted(
            cp.numero for cp in
            CajaPesada.query.filter_by(detalle_pedido_id=detalle.id).all())
        assert numeros == [1, 2, 3, 4]
