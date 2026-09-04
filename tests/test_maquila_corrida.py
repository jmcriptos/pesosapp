"""La corrida: se pesan las cajas, se declara el consumo y se cierra."""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


def _recibir(codigo, dia, kg, ingrediente_id=None):
    from maquila import servicios
    return servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, dia),
        vendedor_id=IDS['vendedor'],
        lineas=[{'ingrediente_id': ingrediente_id or IDS['ingrediente'],
                 'peso_total': Decimal(str(kg))}])


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([v, cli, prod, ing])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id,
                   ingrediente=ing.id)
        yield flask_app
        _db.drop_all()


def _corrida_con_cajas(pesos):
    from maquila import servicios
    c = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-0903',
        fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['vendedor'])
    for p in pesos:
        servicios.agregar_caja_producida(c, Decimal(str(p)))
    _db.session.commit()
    return c


def test_el_peso_producido_es_la_suma_de_las_cajas(app):
    with app.app_context():
        c = _corrida_con_cajas([10, 10.5, 9.5])
        assert c.peso_producido == Decimal('30.000')


def test_dos_corridas_del_mismo_cliente_no_repiten_lote(app):
    from maquila import servicios
    with app.app_context():
        _corrida_con_cajas([10])
        with pytest.raises(servicios.CorridaInvalida):
            servicios.abrir_corrida(
                cliente_id=IDS['cliente'], producto_id=IDS['producto'],
                lote='L-0903', fecha_produccion=date(2026, 9, 4),
                vendedor_id=IDS['vendedor'])


def test_cerrar_descuenta_del_saldo_por_fifo(app):
    from maquila import servicios
    from maquila.models import CorridaConsumoOrigen
    with app.app_context():
        r1 = _recibir('R1', 1, 30)
        r2 = _recibir('R2', 5, 100)
        c = _corrida_con_cajas([40])
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                 IDS['vendedor'])
        assert c.estado == 'cerrada'
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('80')
        origenes = CorridaConsumoOrigen.query.order_by(
            CorridaConsumoOrigen.id).all()
        assert len(origenes) == 2
        assert origenes[0].recepcion_linea_id == r1.lineas[0].id
        assert origenes[0].cantidad == Decimal('30.000')
        assert origenes[1].recepcion_linea_id == r2.lineas[0].id
        assert origenes[1].cantidad == Decimal('20.000')


def test_cerrar_sin_saldo_suficiente_no_escribe_nada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente, CorridaConsumo
    with app.app_context():
        _recibir('R1', 1, 20)
        c = _corrida_con_cajas([40])
        antes = MovimientoIngrediente.query.count()
        with pytest.raises(servicios.SaldoInsuficiente):
            servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                     IDS['vendedor'])
        _db.session.rollback()
        assert MovimientoIngrediente.query.count() == antes
        assert CorridaConsumo.query.count() == 0
        assert _db.session.get(type(c), c.id).estado == 'abierta'


def test_cerrar_guarda_el_teorico_como_snapshot(app):
    from maquila import servicios
    from maquila.models import Receta, RecetaIngrediente, CorridaConsumo
    with app.app_context():
        _recibir('R1', 1, 200)
        rec = Receta(producto_id=IDS['producto'], cliente_id=IDS['cliente'],
                     nombre='R', base_kg=Decimal('100'), activa=True)
        _db.session.add(rec)
        _db.session.flush()
        _db.session.add(RecetaIngrediente(receta_id=rec.id,
                                          ingrediente_id=IDS['ingrediente'],
                                          cantidad=Decimal('120')))
        _db.session.commit()
        c = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-1',
            fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['vendedor'],
            receta_id=rec.id)
        servicios.agregar_caja_producida(c, Decimal('50'))
        _db.session.commit()
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('55')},
                                 IDS['vendedor'])
        consumo = CorridaConsumo.query.one()
        assert consumo.cantidad_teorica == Decimal('60.000')  # 120 * 50/100
        assert consumo.cantidad_real == Decimal('55.000')


def test_la_merma_es_consumido_menos_producido(app):
    from maquila import servicios
    with app.app_context():
        _recibir('R1', 1, 200)
        c = _corrida_con_cajas([40])
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                 IDS['vendedor'])
        assert servicios.merma_de_corrida(c) == Decimal('10.000')


def test_una_corrida_cerrada_no_se_puede_cerrar_dos_veces(app):
    from maquila import servicios
    with app.app_context():
        _recibir('R1', 1, 200)
        c = _corrida_con_cajas([40])
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                 IDS['vendedor'])
        with pytest.raises(servicios.CorridaInvalida):
            servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('10')},
                                     IDS['vendedor'])


def test_cerrar_sin_cajas_producidas_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        _recibir('R1', 1, 200)
        c = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-9',
            fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['vendedor'])
        with pytest.raises(servicios.CorridaInvalida):
            servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('10')},
                                     IDS['vendedor'])


def test_anular_una_corrida_devuelve_el_ingrediente_al_saldo(app):
    from maquila import servicios
    with app.app_context():
        _recibir('R1', 1, 200)
        c = _corrida_con_cajas([40])
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                 IDS['vendedor'])
        servicios.anular_corrida(c, IDS['vendedor'], 'Se contaminó el lote')
        _db.session.commit()
        assert c.estado == 'anulada'
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('200')
