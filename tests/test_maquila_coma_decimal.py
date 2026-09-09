"""La coma decimal en maquila: se teclea con guantes y teclado en español.

Medido en el navegador (2026-09-09) sobre `<input type="number">`: al teclear
«12,5» el navegador DESCARTA la coma y el campo queda en «125». No es solo
«no me deja poner la coma»: es una caja de 12,5 kg que entra al ledger como
125 kg, sin aviso y sin forma de notarlo después.

El resto de la app ya lo resolvió así (temperaturas de cámaras, pesaje de
pedidos): `type="text" inputmode="decimal"` + normalizador coma→punto en el
cliente. El servidor (`_decimal`) ya aceptaba la coma; lo que faltaba era que
el navegador la dejara llegar.
"""
import os
import pathlib
import re
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PLANTILLAS = sorted((_ROOT / 'templates' / 'maquila').glob('*.html'))
_INPUT = re.compile(r'<input\b[^>]*>', re.S)
# Un paso fraccionario es la marca de «acá va un decimal»: 0.001 para kilos,
# 0.1 para grados. `step="1"` (bultos, unidades) no necesita coma.
_PASO_DECIMAL = re.compile(r'step="(?:\{\{[^}]*\}\}|[^"]*0\.\d)')

IDS = {}


def _campos_decimales():
    """(archivo, tag) de cada input de la maquila que admite fracciones."""
    for plantilla in _PLANTILLAS:
        html = plantilla.read_text(encoding='utf-8')
        for tag in _INPUT.findall(html):
            if _PASO_DECIMAL.search(tag) or 'decimal' in tag:
                yield plantilla.name, ' '.join(tag.split())


def test_hay_campos_decimales_que_revisar():
    """Guarda del guarda: si el scan deja de encontrar campos, el resto de
    los tests pasarían en vacío."""
    assert len(list(_campos_decimales())) >= 8


def test_ningun_campo_decimal_es_input_number():
    """`type="number"` se come la coma: «12,5» → «125»."""
    malos = [f'{arch}: {tag}' for arch, tag in _campos_decimales()
             if 'type="number"' in tag]
    assert malos == [], 'Campos decimales que descartan la coma:\n' + '\n'.join(malos)


def test_cada_campo_decimal_lleva_su_normalizador():
    """Sin el hook, el valor viaja con coma y depende del servidor; con él,
    el operario ve el punto en el mismo campo mientras teclea."""
    malos = []
    for arch, tag in _campos_decimales():
        if 'inputmode="decimal"' not in tag:
            malos.append(f'{arch} (sin inputmode decimal): {tag}')
        elif not ('data-decimal' in tag or 'data-signed-decimal' in tag):
            malos.append(f'{arch} (sin normalizador): {tag}')
    assert malos == [], 'Campos decimales sin normalizar:\n' + '\n'.join(malos)


def test_la_maquila_carga_el_normalizador():
    base = (_ROOT / 'templates' / 'maquila' / 'base_maquila.html').read_text(encoding='utf-8')
    assert 'signed_decimal.js' in base


def test_el_normalizador_atiende_campos_sin_signo():
    js = (_ROOT / 'static' / 'js' / 'signed_decimal.js').read_text(encoding='utf-8')
    assert 'data-decimal' in js


# --- La otra mitad: que el valor con coma llegue entero a la base -----------

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


def _login(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'pw'},
           follow_redirects=True)
    return c


def test_una_caja_de_12_coma_5_pesa_12_coma_5(app):
    from maquila import servicios
    from maquila.models import CorridaProduccion
    with app.app_context():
        corrida = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'],
            lote='L-0909', fecha_produccion=date(2026, 9, 9),
            vendedor_id=IDS['vendedor'])
        _db.session.commit()
        corrida_id = corrida.id
    cliente = _login(app)
    cliente.post(f'/maquila/corridas/{corrida_id}/caja', data={'peso': '12,5'},
                 follow_redirects=True)
    with app.app_context():
        corrida = _db.session.get(CorridaProduccion, corrida_id)
        assert [c.peso for c in corrida.cajas] == [Decimal('12.500')]


def test_una_recepcion_con_coma_no_se_multiplica_por_diez(app):
    from maquila.models import RecepcionIngrediente
    cliente = _login(app)
    cliente.post('/maquila/recepciones/nueva', data={
        'cliente_id': IDS['cliente'], 'recibido_en': '2026-09-09',
        'temperatura': '-18,5',
        'linea_ingrediente_id': IDS['ingrediente'],
        'linea_lote_cliente': '', 'linea_fecha_vencimiento': '',
        'linea_cantidad_bultos': '2', 'linea_peso_total': '12,5',
    }, follow_redirects=True)
    with app.app_context():
        rec = RecepcionIngrediente.query.one()
        assert [l.peso_total for l in rec.lineas] == [Decimal('12.500')]
        assert rec.temperatura == Decimal('-18.5')
