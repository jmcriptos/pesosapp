"""El ledger: un movimiento sube o baja el saldo, y nada más lo toca."""
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
        from maquila.models import Ingrediente, RecepcionIngrediente, RecepcionLinea
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
        _db.session.flush()
        rec = RecepcionIngrediente(codigo='R-2026-0001', cliente_id=cli.id,
                                   recibido_en=date(2026, 9, 1), registrado_por=v.id)
        _db.session.add(rec)
        _db.session.flush()
        linea = RecepcionLinea(recepcion_id=rec.id, ingrediente_id=ing.id,
                               peso_total=Decimal('100.000'))
        _db.session.add(linea)
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, ingrediente=ing.id, linea=linea.id)
        yield flask_app
        _db.drop_all()


def test_una_entrada_sube_el_saldo(app):
    from maquila import servicios
    with app.app_context():
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='entrada', cantidad=Decimal('100'), origen_tipo='recepcion',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        _db.session.commit()
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('100')


def test_una_salida_baja_el_saldo(app):
    from maquila import servicios
    with app.app_context():
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='entrada', cantidad=Decimal('100'), origen_tipo='recepcion',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('-30'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        _db.session.commit()
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('70')
        assert servicios.saldo_de_linea(IDS['linea']) == Decimal('70')


def test_la_salida_se_normaliza_a_negativo(app):
    """Pasar 30 en una salida debe guardarse como -30: el signo es del tipo,
    no de quien llama. Es el error más fácil de cometer desde una ruta."""
    from maquila import servicios
    with app.app_context():
        mov = servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('30'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        _db.session.commit()
        assert mov.cantidad == Decimal('-30')


def test_un_ajuste_sin_motivo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        with pytest.raises(servicios.MotivoRequerido):
            servicios.registrar_movimiento(
                cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
                tipo='ajuste', cantidad=Decimal('5'), origen_tipo='manual',
                vendedor_id=IDS['vendedor'])


def test_saldos_de_cliente_desglosa_recibido_y_consumido(app):
    from maquila import servicios
    with app.app_context():
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='entrada', cantidad=Decimal('100'), origen_tipo='recepcion',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('40'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        _db.session.commit()
        filas = servicios.saldos_de_cliente(IDS['cliente'])
        assert len(filas) == 1
        fila = filas[0]
        assert fila['recibido'] == Decimal('100')
        assert fila['consumido'] == Decimal('40')
        assert fila['saldo'] == Decimal('60')
        assert fila['ingrediente'] == 'Carne de res'
