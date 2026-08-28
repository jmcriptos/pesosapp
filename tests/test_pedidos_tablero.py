# tests/test_pedidos_tablero.py
"""El tablero de entregas: reparto en grupos y contrato de modos.

Spec: docs/superpowers/specs/2026-08-28-pedidos-tablero-design.md
"""
import os
from datetime import date, timedelta

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import _agrupar_tablero, Pedido


HOY = date(2026, 8, 28)


def _p(estado, dias=None, id=1):
    """Pedido suelto, sin sesión: `_agrupar_tablero` es pura."""
    return Pedido(
        id=id,
        estado=estado,
        fecha_entrega=None if dias is None else HOY + timedelta(days=dias),
    )


def _claves(grupos):
    return [clave for clave, _etiqueta, _pedidos in grupos]


def _pedidos_de(grupos, clave):
    for c, _etiqueta, pedidos in grupos:
        if c == clave:
            return pedidos
    return []


def test_atrasado_sin_facturar_va_a_atrasados():
    grupos = _agrupar_tablero([_p('pendiente', dias=-3)], HOY)
    assert _claves(grupos) == ['atrasados']


def test_entrega_hoy_va_a_hoy_en_cualquier_estado():
    grupos = _agrupar_tablero(
        [_p('pendiente', dias=0, id=1),
         _p('preparado', dias=0, id=2),
         _p('facturado', dias=0, id=3)],
        HOY,
    )
    assert _claves(grupos) == ['hoy']
    assert len(_pedidos_de(grupos, 'hoy')) == 3


def test_el_facturado_de_hoy_no_se_cuela_en_otro_grupo():
    """Decisión del spec: se queda en «Hoy», marcado hecho. En ningún otro."""
    grupos = _agrupar_tablero([_p('facturado', dias=0)], HOY)
    assert _claves(grupos) == ['hoy']


def test_entrega_futura_sin_facturar_va_a_proximos():
    grupos = _agrupar_tablero([_p('preparado', dias=5)], HOY)
    assert _claves(grupos) == ['proximos']


def test_sin_facturar_y_sin_fecha_nunca_es_invisible():
    """El test que más importa: si falla, la pantalla esconde trabajo."""
    grupos = _agrupar_tablero([_p('pendiente', dias=None)], HOY)
    assert _claves(grupos) == ['sin_fecha']
    assert len(_pedidos_de(grupos, 'sin_fecha')) == 1


def test_el_archivo_no_entra_al_tablero():
    """Facturado que no se entrega hoy: ni atrasados, ni próximos, ni sin fecha."""
    grupos = _agrupar_tablero(
        [_p('facturado', dias=-30, id=1),
         _p('facturado', dias=None, id=2),
         _p('facturado', dias=9, id=3)],
        HOY,
    )
    assert grupos == []


def test_los_grupos_vacios_no_se_dibujan():
    grupos = _agrupar_tablero([_p('pendiente', dias=0)], HOY)
    assert _claves(grupos) == ['hoy'], 'no debe aparecer ningún grupo vacío'


def test_los_grupos_van_en_orden_de_urgencia():
    grupos = _agrupar_tablero(
        [_p('pendiente', dias=4, id=1),
         _p('pendiente', dias=None, id=2),
         _p('pendiente', dias=0, id=3),
         _p('pendiente', dias=-2, id=4)],
        HOY,
    )
    assert _claves(grupos) == ['atrasados', 'hoy', 'proximos', 'sin_fecha']


def test_ningun_pedido_aparece_dos_veces():
    pedidos = [_p('pendiente', dias=-1, id=1), _p('facturado', dias=0, id=2),
               _p('preparado', dias=3, id=3), _p('pendiente', dias=None, id=4)]
    grupos = _agrupar_tablero(pedidos, HOY)
    vistos = [p.id for _c, _e, ps in grupos for p in ps]
    assert sorted(vistos) == [1, 2, 3, 4]
    assert len(vistos) == len(set(vistos)), 'un pedido cayó en dos grupos'


# ── Contrato de modos ────────────────────────────────────────────────────────

@pytest.fixture
def app():
    from app import app as flask_app, db as _db
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente
        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(
            username='admin', email='admin@test.com', nombre_completo='Admin',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.add(Cliente(nombre='Cliente Uno', territorio_id=territorio.id))
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def _crear(estado, dias=None):
    from app import Pedido, Cliente, db as _db, DASHBOARD_TIMEZONE
    from datetime import datetime
    hoy = datetime.now(DASHBOARD_TIMEZONE).date()
    p = Pedido(cliente_id=Cliente.query.first().id, estado=estado)
    if dias is not None:
        p.fecha_entrega = hoy + timedelta(days=dias)
    _db.session.add(p)
    _db.session.commit()
    return p


def _sin_scripts(html):
    """Quita los <script> antes de afirmar que algo NO se renderizó.

    El script inline del listado vive fuera del `{% if modo_tablero %}` porque
    sirve a los dos modos, y sus selectores mencionan las mismas clases que
    algunos tests afirman ausentes (`.pagination-info-mobile`, `.pedidos-empty`).
    Sin quitarlo, el test mide el código JS en vez del HTML renderizado.
    """
    import re
    return re.sub(r'<script\b.*?</script>', '', html, flags=re.S)


def test_pedidos_sin_parametros_es_tablero(logged_client):
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'data-tablero="1"' in html, 'no se renderizó el tablero'
    assert 'pagination-info-mobile' not in _sin_scripts(html), 'el tablero no debe paginar'


def test_un_parametro_reconocido_devuelve_la_lista(logged_client):
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
    assert 'data-tablero="1"' not in html
    assert 'filter-pill' in html, 'la lista conserva sus píldoras'


def test_el_enlace_del_dashboard_sigue_funcionando(logged_client):
    """`/pedidos?estado=pendiente` lo dispara el aviso del dashboard
    (app.py:1915). Si se rompe, se rompe en producción sin que nadie toque
    nada."""
    _crear('pendiente', dias=0)
    r = logged_client.get('/pedidos?estado=pendiente')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'data-tablero="1"' not in html, 'un enlace viejo cayó en el tablero'


def test_un_parametro_desconocido_no_cambia_el_modo(logged_client):
    """Un `?utm_source=` pegado por un cliente de correo no puede convertir
    el tablero en lista."""
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos?utm_source=whatsapp').get_data(as_text=True)
    assert 'data-tablero="1"' in html


def test_un_parametro_vacio_no_cambia_el_modo(logged_client):
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos?q=').get_data(as_text=True)
    assert 'data-tablero="1"' in html


def test_buscar_desde_el_tablero_busca_en_todo(logged_client):
    """Sin esto, buscar «Mangusa» desde el tablero saldría filtrado a lo no
    facturado y no encontraría NADA del archivo, que es justo lo que se
    estaba buscando."""
    _crear('facturado', dias=-40)
    html = logged_client.get('/pedidos?q=Cliente').get_data(as_text=True)
    assert 'pedidos-empty' not in _sin_scripts(html), (
        'la búsqueda sin `estado` explícito no alcanzó el archivo'
    )
