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
