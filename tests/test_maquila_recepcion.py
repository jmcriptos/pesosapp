"""Alta y anulación de recepciones de ingredientes."""
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
        from app import Rol, Territorio, Vendedor, Cliente
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        ing = Ingrediente(nombre='Carne de res')
        ing2 = Ingrediente(nombre='Grasa')
        _db.session.add_all([v, cli, ing, ing2])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id,
                   ingrediente=ing.id, ingrediente2=ing2.id)
        yield flask_app
        _db.drop_all()


def test_el_codigo_es_correlativo_por_anio(app):
    from maquila import servicios
    with app.app_context():
        assert servicios.siguiente_codigo('R', 2026) == 'R-2026-0001'
        servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'],
                     'cantidad_bultos': 1, 'peso_total': Decimal('10')}])
        assert servicios.siguiente_codigo('R', 2026) == 'R-2026-0002'


def test_a_granel_se_acepta_el_peso_total_sin_bultos(app):
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'],
                     'peso_total': Decimal('75.5')}])
        assert rec.lineas[0].peso_total == Decimal('75.500')
        assert rec.lineas[0].bultos == []


def test_sin_documento_del_cliente_es_valido(app):
    """El cliente a veces manda la carne sin ningún papel."""
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'], documento_cliente=None,
            lineas=[{'ingrediente_id': IDS['ingrediente'],
                     'cantidad_bultos': 1, 'peso_total': Decimal('10')}])
        assert rec.documento_cliente is None
        assert rec.codigo.startswith('R-')


def test_el_alta_escribe_un_movimiento_de_entrada_por_linea(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'cantidad_bultos': 1, 'peso_total': Decimal('10')},
                    {'ingrediente_id': IDS['ingrediente2'], 'cantidad_bultos': 1, 'peso_total': Decimal('4')}])
        movs = MovimientoIngrediente.query.all()
        assert len(movs) == 2
        assert all(m.tipo == 'entrada' and m.origen_tipo == 'recepcion' for m in movs)
        assert sorted(m.cantidad for m in movs) == [Decimal('4.000'), Decimal('10.000')]


def test_una_recepcion_sin_lineas_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        with pytest.raises(servicios.RecepcionInvalida):
            servicios.crear_recepcion(
                cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
                vendedor_id=IDS['vendedor'], lineas=[])


def test_anular_una_recepcion_intacta_escribe_los_inversos(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'cantidad_bultos': 1, 'peso_total': Decimal('10')}])
        servicios.anular_recepcion(rec, IDS['vendedor'], 'Llegó en mal estado')
        _db.session.commit()
        assert rec.anulada is True
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('0')
        # No se borró nada: quedan los dos movimientos.
        assert MovimientoIngrediente.query.count() == 2


def test_anular_una_recepcion_ya_consumida_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'cantidad_bultos': 1, 'peso_total': Decimal('10')}])
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('4'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'],
            recepcion_linea_id=rec.lineas[0].id)
        _db.session.commit()
        with pytest.raises(servicios.RecepcionConsumida):
            servicios.anular_recepcion(rec, IDS['vendedor'], 'Error de captura')


def test_anular_sin_motivo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'cantidad_bultos': 1, 'peso_total': Decimal('10')}])
        with pytest.raises(servicios.MotivoRequerido):
            servicios.anular_recepcion(rec, IDS['vendedor'], '   ')


def test_anular_tras_quitar_una_linea(app):
    """Quitar una línea la marca `anulada_en` pero NO toca `peso_total`.
    `anular_recepcion` recorre `recepcion.lineas` sin filtrar anuladas y
    compara `saldo_de_linea(l) == l.peso_total`: para la línea quitada eso es
    `0 != 15` (su inverso ya la dejó en 0), así que revienta con
    `RecepcionConsumida` diciendo que se consumió algo que nunca se consumió,
    y la recepción queda imposible de anular para siempre."""
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'peso_total': Decimal('15')},
                    {'ingrediente_id': IDS['ingrediente2'], 'peso_total': Decimal('20')}])
        linea_quitada = rec.lineas[0]
        linea_intacta = rec.lineas[1]

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'],
            cabecera={'cliente_id': rec.cliente_id, 'recibido_en': rec.recibido_en,
                     'documento_cliente': None, 'temperatura': None,
                     'transportista': None, 'notas': None},
            lineas=[{'id': linea_quitada.id, 'ingrediente_id': linea_quitada.ingrediente_id,
                    'lote_cliente': None, 'fecha_vencimiento': None, 'cantidad_bultos': 0,
                    'peso_total': Decimal('15'), 'quitar': True},
                   {'id': linea_intacta.id, 'ingrediente_id': linea_intacta.ingrediente_id,
                    'lote_cliente': None, 'fecha_vencimiento': None, 'cantidad_bultos': 0,
                    'peso_total': Decimal('20'), 'quitar': False}],
            motivo='No vino')
        _db.session.commit()
        assert linea_quitada.anulada is True

        # Antes del arreglo, esto lanzaba RecepcionConsumida.
        servicios.anular_recepcion(rec, IDS['vendedor'], 'Ya no aplica')
        _db.session.commit()

        assert rec.anulada is True
        assert servicios.saldo_de_linea(linea_quitada.id) == Decimal('0')
        assert servicios.saldo_de_linea(linea_intacta.id) == Decimal('0')
        # Sin doble compensación: el saldo por cliente/ingrediente también
        # queda en cero, no en -15/-20.
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('0')
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente2']) == Decimal('0')


def test_una_linea_valida_seguida_de_invalida_no_deja_residuo(app):
    """Si la línea 2 es inválida, línea 1 y cabecera no quedan persistidas."""
    from maquila import servicios
    from maquila.models import RecepcionIngrediente, RecepcionLinea, MovimientoIngrediente
    with app.app_context():
        with pytest.raises(servicios.RecepcionInvalida):
            servicios.crear_recepcion(
                cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
                vendedor_id=IDS['vendedor'],
                lineas=[
                    {'ingrediente_id': IDS['ingrediente'], 'cantidad_bultos': 1, 'peso_total': Decimal('10')},
                    {'ingrediente_id': IDS['ingrediente2'], 'peso_total': Decimal('0')}
                ])
        # Sin residuo: no se cometió media recepción.
        assert RecepcionIngrediente.query.count() == 0
        assert RecepcionLinea.query.count() == 0
        assert MovimientoIngrediente.query.count() == 0


def test_excepcion_no_recepcion_invalida_tambien_rollback(app):
    """Si una línea revienta con una excepción que NO es RecepcionInvalida
    (acá `InvalidOperation`, por un peso ilegible), tampoco queda residuo.

    Antes el disparador era una línea sin `ingrediente_id` (KeyError); desde
    la revisión de 2026-09-04 eso es una `RecepcionInvalida` con mensaje, así
    que el test necesita otro error fuera del dominio para seguir probando
    el contrato de rollback."""
    from decimal import InvalidOperation
    from maquila import servicios
    from maquila.models import RecepcionIngrediente, RecepcionLinea, MovimientoIngrediente
    with app.app_context():
        with pytest.raises(InvalidOperation):
            servicios.crear_recepcion(
                cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
                vendedor_id=IDS['vendedor'],
                lineas=[
                    {'ingrediente_id': IDS['ingrediente'], 'cantidad_bultos': 1, 'peso_total': Decimal('10')},
                    {'ingrediente_id': IDS['ingrediente'], 'cantidad_bultos': 1, 'peso_total': 'diez'},
                ])
        # Sin residuo: no quedó media recepción aunque la excepción no fuera RecepcionInvalida.
        assert RecepcionIngrediente.query.count() == 0
        assert RecepcionLinea.query.count() == 0
        assert MovimientoIngrediente.query.count() == 0
