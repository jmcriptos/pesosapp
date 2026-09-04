"""Qué receta aplica y cuánto propone consumir."""
import os
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


def _receta(producto_id, cliente_id, base_kg, items, activa=True):
    """items: [(ingrediente_id, cantidad_por_base)]"""
    from maquila.models import Receta, RecetaIngrediente
    r = Receta(producto_id=producto_id, cliente_id=cliente_id, nombre='R',
               base_kg=Decimal(str(base_kg)), activa=activa)
    _db.session.add(r)
    _db.session.flush()
    for ingrediente_id, cantidad in items:
        _db.session.add(RecetaIngrediente(receta_id=r.id,
                                          ingrediente_id=ingrediente_id,
                                          cantidad=Decimal(str(cantidad))))
    _db.session.commit()
    return r


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
        ing2 = Ingrediente(nombre='Grasa')
        _db.session.add_all([v, cli, prod, ing, ing2])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id,
                   ingrediente=ing.id, ingrediente2=ing2.id)
        yield flask_app
        _db.drop_all()


def test_la_receta_del_cliente_le_gana_a_la_generica(app):
    from maquila import servicios
    with app.app_context():
        _receta(IDS['producto'], None, 100, [(IDS['ingrediente'], 90)])
        propia = _receta(IDS['producto'], IDS['cliente'], 100,
                         [(IDS['ingrediente'], 80)])
        elegida = servicios.receta_activa(IDS['producto'], IDS['cliente'])
        assert elegida.id == propia.id


def test_sin_receta_propia_cae_a_la_generica(app):
    from maquila import servicios
    with app.app_context():
        generica = _receta(IDS['producto'], None, 100, [(IDS['ingrediente'], 90)])
        elegida = servicios.receta_activa(IDS['producto'], IDS['cliente'])
        assert elegida.id == generica.id


def test_una_receta_inactiva_no_se_elige(app):
    from maquila import servicios
    with app.app_context():
        _receta(IDS['producto'], IDS['cliente'], 100,
                [(IDS['ingrediente'], 80)], activa=False)
        assert servicios.receta_activa(IDS['producto'], IDS['cliente']) is None


def test_el_consumo_teorico_escala_con_lo_producido(app):
    from maquila import servicios
    with app.app_context():
        r = _receta(IDS['producto'], IDS['cliente'], 100,
                    [(IDS['ingrediente'], 80), (IDS['ingrediente2'], 25)])
        teorico = servicios.consumo_teorico(r, Decimal('250'))
        assert teorico[IDS['ingrediente']] == Decimal('200.000')
        assert teorico[IDS['ingrediente2']] == Decimal('62.500')


def test_dos_recetas_activas_iguales_se_rechazan_al_guardar(app):
    from maquila import servicios
    with app.app_context():
        _receta(IDS['producto'], IDS['cliente'], 100, [(IDS['ingrediente'], 80)])
        with pytest.raises(servicios.RecetaDuplicada):
            servicios.validar_receta_unica(IDS['producto'], IDS['cliente'])
