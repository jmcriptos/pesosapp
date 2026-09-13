"""FIFO: se consume primero lo que entró primero, y si no alcanza se avisa."""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


def _recibir(cliente_id, ingrediente_id, vendedor_id, codigo, dia, kg):
    """Crea una recepción de una línea y su movimiento de entrada."""
    from maquila import servicios
    from maquila.models import RecepcionIngrediente, RecepcionLinea
    rec = RecepcionIngrediente(codigo=codigo, cliente_id=cliente_id,
                               recibido_en=date(2026, 9, dia),
                               registrado_por=vendedor_id)
    _db.session.add(rec)
    _db.session.flush()
    linea = RecepcionLinea(recepcion_id=rec.id, ingrediente_id=ingrediente_id,
                           peso_total=Decimal(str(kg)))
    _db.session.add(linea)
    _db.session.flush()
    servicios.registrar_movimiento(
        cliente_id=cliente_id, ingrediente_id=ingrediente_id, tipo='entrada',
        cantidad=Decimal(str(kg)), origen_tipo='recepcion', origen_id=rec.id,
        vendedor_id=vendedor_id, recepcion_linea_id=linea.id)
    _db.session.commit()
    return linea.id


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
        _db.session.add_all([v, cli, ing])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, ingrediente=ing.id)
        yield flask_app
        _db.drop_all()


def test_consume_de_la_recepcion_mas_antigua(app):
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 100)
        _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                 'R-2026-0002', 5, 100)
        reparto = servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                          Decimal('60'))
        assert reparto == [(vieja, Decimal('60'))]


def test_reparte_entre_varias_cuando_una_no_alcanza(app):
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 100)
        nueva = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0002', 5, 100)
        reparto = servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                          Decimal('150'))
        assert reparto == [(vieja, Decimal('100')), (nueva, Decimal('50'))]


def test_salta_las_recepciones_agotadas(app):
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 100)
        nueva = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0002', 5, 100)
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('100'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=vieja)
        _db.session.commit()
        reparto = servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                          Decimal('30'))
        assert reparto == [(nueva, Decimal('30'))]


def test_sin_saldo_suficiente_lanza_y_no_escribe_nada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                 'R-2026-0001', 1, 50)
        antes = MovimientoIngrediente.query.count()
        with pytest.raises(servicios.SaldoInsuficiente) as exc:
            servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                    Decimal('80'))
        assert exc.value.faltante == Decimal('30')
        assert exc.value.disponible == Decimal('50')
        assert MovimientoIngrediente.query.count() == antes


def test_cantidad_cero_o_negativa_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        with pytest.raises(ValueError):
            servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'], Decimal('0'))


# ---------------------------------------------------------------------------
# Ajustes manuales anclados a líneas: el FIFO tiene que verlos
# ---------------------------------------------------------------------------


def _ajustar(sentido, kg, linea_id=None, motivo='Merma por descongelación'):
    from maquila import servicios
    movs = servicios.registrar_ajuste_manual(
        cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
        sentido=sentido, cantidad=Decimal(str(kg)), vendedor_id=IDS['vendedor'],
        motivo=motivo, recepcion_linea_id=linea_id)
    _db.session.commit()
    return movs


def test_la_salida_manual_baja_la_linea_mas_antigua_y_el_fifo_no_la_vuelve_a_dar(app):
    """Antes del anclaje, un ajuste de salida bajaba el saldo del cliente pero
    ninguna línea: la siguiente corrida podía volver a consumir esos kilos."""
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 100)
        nueva = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0002', 5, 50)
        movs = _ajustar('salida', 30)
        assert [(m.recepcion_linea_id, m.cantidad) for m in movs] == \
            [(vieja, Decimal('-30'))]
        assert all(m.tipo == 'ajuste' and m.origen_tipo == 'manual' for m in movs)
        assert servicios.saldo_de_linea(vieja) == Decimal('70')
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('120')
        # Hay 120 en total: pedir 121 se bloquea, igual que en el cierre.
        with pytest.raises(servicios.SaldoInsuficiente) as exc:
            servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'], Decimal('121'))
        assert exc.value.disponible == Decimal('120')
        assert servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                       Decimal('120')) == \
            [(vieja, Decimal('70')), (nueva, Decimal('50'))]


def test_la_salida_manual_se_reparte_entre_lineas_si_la_primera_no_alcanza(app):
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 20)
        nueva = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0002', 5, 50)
        movs = _ajustar('salida', 35)
        assert [(m.recepcion_linea_id, m.cantidad) for m in movs] == \
            [(vieja, Decimal('-20')), (nueva, Decimal('-15'))]
        assert servicios.saldo_de_linea(vieja) == Decimal('0')
        assert servicios.saldo_de_linea(nueva) == Decimal('35')


def test_la_salida_manual_sin_saldo_lanza_y_no_escribe_nada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                 'R-2026-0001', 1, 20)
        antes = MovimientoIngrediente.query.count()
        with pytest.raises(servicios.SaldoInsuficiente):
            _ajustar('salida', 25)
        _db.session.rollback()
        assert MovimientoIngrediente.query.count() == antes


def test_la_entrada_manual_se_ancla_a_la_linea_mas_reciente_y_destraba_el_fifo(app):
    """Es la escotilla de `corrida_cerrar`: el consumo supera lo recibido, se
    registra la diferencia como entrada y el reparto la tiene que ver."""
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 100)
        nueva = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0002', 5, 50)
        with pytest.raises(servicios.SaldoInsuficiente):
            servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'], Decimal('160'))
        movs = _ajustar('entrada', 10, motivo='Conteo físico: sobraban 10 kg')
        assert [(m.recepcion_linea_id, m.cantidad) for m in movs] == \
            [(nueva, Decimal('10'))]
        assert servicios.saldo_de_linea(nueva) == Decimal('60')
        assert servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                       Decimal('160')) == \
            [(vieja, Decimal('100')), (nueva, Decimal('60'))]


def test_la_entrada_manual_sin_ninguna_recepcion_se_rechaza(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        with pytest.raises(servicios.SinRecepcion):
            _ajustar('entrada', 10)
        _db.session.rollback()
        assert MovimientoIngrediente.query.count() == 0


def test_el_ajuste_contra_una_linea_elegida_respeta_esa_linea(app):
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 100)
        nueva = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0002', 5, 50)
        _ajustar('salida', 8, linea_id=nueva)
        _ajustar('entrada', 3, linea_id=vieja)
        assert servicios.saldo_de_linea(vieja) == Decimal('103')
        assert servicios.saldo_de_linea(nueva) == Decimal('42')
        # Una salida por encima del saldo de ESA línea se bloquea aunque
        # otra línea tenga de sobra.
        with pytest.raises(servicios.SaldoInsuficiente) as exc:
            _ajustar('salida', 43, linea_id=nueva)
        _db.session.rollback()
        assert exc.value.disponible == Decimal('42')


def test_el_ajuste_manual_sin_motivo_o_con_cantidad_invalida_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                 'R-2026-0001', 1, 100)
        with pytest.raises(servicios.MotivoRequerido):
            _ajustar('salida', 5, motivo='   ')
        with pytest.raises(ValueError):
            _ajustar('salida', 0)
        with pytest.raises(ValueError):
            _ajustar('lateral', 5)
