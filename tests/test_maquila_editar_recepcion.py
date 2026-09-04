"""Editar una recepción sin que el saldo y la pantalla dejen de coincidir."""
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
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        rv = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, rv, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        vend = Vendedor(username='vend', email='v@t.com', nombre_completo='Vend',
                        rol_id=rv.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        otro = Cliente(nombre='Otro cliente')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        carne = Ingrediente(nombre='Carne de res', unidad='kg')
        grasa = Ingrediente(nombre='Grasa', unidad='kg')
        _db.session.add_all([v, vend, cli, otro, prod, carne, grasa])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, otro_cliente=otro.id,
                   producto=prod.id, carne=carne.id, grasa=grasa.id)
        yield flask_app
        _db.drop_all()


def _recepcion(kg=100, ingrediente=None, dia=1):
    """Una recepción de una línea, a granel."""
    from maquila import servicios
    return servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, dia),
        vendedor_id=IDS['vendedor'],
        lineas=[{'ingrediente_id': ingrediente or IDS['carne'],
                 'peso_total': Decimal(str(kg))}])


def test_una_linea_nueva_no_nace_anulada(app):
    with app.app_context():
        rec = _recepcion()
        linea = rec.lineas[0]
        assert linea.anulada_en is None
        assert linea.anulada is False


def _consumir(linea_id, ingrediente_id, kg):
    """Simula que una corrida tomó material de esa línea."""
    from maquila import servicios
    servicios.registrar_movimiento(
        cliente_id=IDS['cliente'], ingrediente_id=ingrediente_id,
        tipo='salida', cantidad=Decimal(str(kg)), origen_tipo='corrida',
        origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=linea_id)
    _db.session.commit()


def _cabecera(rec, **cambios):
    base = {'cliente_id': rec.cliente_id, 'recibido_en': rec.recibido_en,
            'documento_cliente': rec.documento_cliente,
            'temperatura': rec.temperatura, 'transportista': rec.transportista,
            'notas': rec.notas}
    base.update(cambios)
    return base


def _linea_dict(linea, **cambios):
    base = {'id': linea.id, 'ingrediente_id': linea.ingrediente_id,
            'lote_cliente': linea.lote_cliente,
            'fecha_vencimiento': linea.fecha_vencimiento,
            'bultos': [], 'peso_total': Decimal(str(linea.peso_total)),
            'quitar': False}
    base.update(cambios)
    return base


def test_corregir_escribe_exactamente_un_movimiento_por_la_diferencia(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal')

        movs = MovimientoIngrediente.query.order_by(
            MovimientoIngrediente.id).all()
        assert len(movs) == antes + 1
        assert movs[-1].tipo == 'ajuste'
        assert movs[-1].cantidad == Decimal('-10.000')
        assert movs[-1].recepcion_linea_id == linea.id
        assert 'tecleó mal' in movs[-1].motivo
        assert linea.peso_total == Decimal('90.000')


def test_tras_corregir_se_mantiene_la_identidad_del_fifo(app):
    """peso_total − consumido == saldo_de_linea. De ahí cuelga el reparto."""
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal')

        consumido = servicios.consumido_de_linea(linea)
        assert consumido == Decimal('40.000')
        assert (Decimal(str(linea.peso_total)) - consumido
                == servicios.saldo_de_linea(linea.id))


def test_editar_solo_la_cabecera_no_toca_el_ledger(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(rec, transportista='Rudsel Martina',
                               documento_cliente='GD-999'),
            lineas=[_linea_dict(linea)])

        assert MovimientoIngrediente.query.count() == antes
        assert rec.transportista == 'Rudsel Martina'
        assert rec.documento_cliente == 'GD-999'


def test_guardar_sin_cambiar_nada_no_escribe_nada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea)])
        assert MovimientoIngrediente.query.count() == antes


def test_corregir_por_debajo_de_lo_consumido_se_rechaza(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 64)
        antes = MovimientoIngrediente.query.count()

        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, peso_total=Decimal('59'))],
                motivo='Imposible')

        _db.session.rollback()
        assert MovimientoIngrediente.query.count() == antes
        assert Decimal(str(rec.lineas[0].peso_total)) == Decimal('100.000')


def test_corregir_a_cero_o_negativo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        for valor in (Decimal('0'), Decimal('-5')):
            with pytest.raises(servicios.RecepcionInvalida):
                servicios.editar_recepcion(
                    rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                    lineas=[_linea_dict(linea, peso_total=valor)],
                    motivo='x')
            _db.session.rollback()


def test_corregir_sin_motivo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        with pytest.raises(servicios.MotivoRequerido):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, peso_total=Decimal('90'))])


def test_quitar_una_linea_intacta_escribe_su_inverso_y_la_marca(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, quitar=True)],
            motivo='No vino')
        assert linea.anulada is True
        assert servicios.saldo_de_linea(linea.id) == Decimal('0')


def test_quitar_una_linea_consumida_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)
        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, quitar=True)],
                motivo='No vino')
        _db.session.rollback()
        assert rec.lineas[0].anulada is False


def test_agregar_una_linea_escribe_su_entrada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea),
                    {'id': None, 'ingrediente_id': IDS['grasa'],
                     'lote_cliente': None, 'fecha_vencimiento': None,
                     'bultos': [Decimal('12'), Decimal('8')],
                     'peso_total': None, 'quitar': False}])
        entradas = MovimientoIngrediente.query.filter_by(
            ingrediente_id=IDS['grasa'], tipo='entrada').all()
        assert len(entradas) == 1
        assert entradas[0].cantidad == Decimal('20.000')


def test_cambiar_el_cliente_con_material_consumido_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)
        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'],
                cabecera=_cabecera(rec, cliente_id=IDS['otro_cliente']),
                lineas=[_linea_dict(linea)])
        _db.session.rollback()


def test_cambiar_el_cliente_con_todo_intacto_se_acepta(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(rec, cliente_id=IDS['otro_cliente']),
            lineas=[_linea_dict(linea)])
        assert rec.cliente_id == IDS['otro_cliente']


def test_editar_una_recepcion_anulada_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.anular_recepcion(rec, IDS['vendedor'], 'Llegó mal')
        _db.session.commit()
        with pytest.raises(servicios.RecepcionNoEditable):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
                motivo='x')


def test_corregir_la_fecha_reordena_el_fifo_siguiente(app):
    """El FIFO ordena por recibido_en: corregir la fecha cambia contra qué
    línea consumirán las corridas FUTURAS, y no toca ningún reparto ya hecho."""
    from maquila import servicios
    from maquila.models import CorridaConsumoOrigen
    with app.app_context():
        vieja = _recepcion(50, dia=1)
        nueva = _recepcion(50, dia=20)
        origenes_antes = CorridaConsumoOrigen.query.count()

        # Antes de corregir, el FIFO toma de la del día 1.
        assert servicios.repartir_fifo(
            IDS['cliente'], IDS['carne'], Decimal('10')
        )[0][0] == vieja.lineas[0].id

        # Se corrige la fecha de la vieja: ahora es la MÁS reciente.
        servicios.editar_recepcion(
            vieja, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(vieja, recibido_en=date(2026, 9, 25)),
            lineas=[_linea_dict(vieja.lineas[0])])

        assert servicios.repartir_fifo(
            IDS['cliente'], IDS['carne'], Decimal('10')
        )[0][0] == nueva.lineas[0].id
        # Nada del pasado se reescribió.
        assert CorridaConsumoOrigen.query.count() == origenes_antes


def test_el_fifo_reparte_bien_contra_una_linea_corregida(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal')
        reparto = servicios.repartir_fifo(IDS['cliente'], IDS['carne'],
                                          Decimal('90'))
        assert reparto == [(linea.id, Decimal('90'))]
        with pytest.raises(servicios.SaldoInsuficiente):
            servicios.repartir_fifo(IDS['cliente'], IDS['carne'],
                                    Decimal('91'))
