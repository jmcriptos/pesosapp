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
