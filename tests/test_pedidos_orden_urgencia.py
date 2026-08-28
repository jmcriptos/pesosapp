"""El listado abre en lo que necesita trabajo, ordenado por urgencia.

Antes abría en «Todos» —26 pedidos incluyendo los ya facturados— ordenados por
grupo de estado y después `id DESC`. El trabajo declarado de la pantalla es
«ver qué necesita acción», y su clave de orden era el orden de inserción: los
vencidos quedaban desparramados por la lista.

Critique: .impeccable/critique/2026-08-28T08-22-35Z__templates-pedidos-html.md (P1)
"""
import os
import re
from datetime import datetime, timedelta

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
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


def _hoy_local():
    from app import DASHBOARD_TIMEZONE
    return datetime.now(DASHBOARD_TIMEZONE).date()


def _pedido(estado, dias_entrega=None):
    from app import Pedido, Cliente
    p = Pedido(cliente_id=Cliente.query.first().id, estado=estado)
    if dias_entrega is not None:
        p.fecha_entrega = _hoy_local() + timedelta(days=dias_entrega)
    _db.session.add(p)
    _db.session.commit()
    return p


def _ids_listados(logged_client, query=''):
    """Ids de pedido en el orden en que salen, sin acoplarse al markup exacto."""
    html = logged_client.get(f'/pedidos{query}').get_data(as_text=True)
    vistos, orden = set(), []
    for pid in re.findall(r'PED[-–—]\s*(\d+)', html):
        if pid not in vistos:
            vistos.add(pid)
            orden.append(int(pid))
    return orden


# === Qué se ve al abrir ===

def test_al_abrir_muestra_lo_que_necesita_trabajo(app, logged_client):
    """Sin parámetros: pendientes y preparados, no los ya facturados."""
    with app.app_context():
        pendiente = _pedido('pendiente', dias_entrega=1)
        preparado = _pedido('preparado', dias_entrega=2)
        facturado = _pedido('facturado', dias_entrega=3)

        ids = _ids_listados(logged_client)

        assert pendiente.id in ids
        assert preparado.id in ids
        assert facturado.id not in ids, 'lo facturado ya no necesita trabajo'


def test_el_filtro_explicito_todos_sigue_mostrando_todo(app, logged_client):
    """El default cambia; la salida a la vista completa se conserva."""
    with app.app_context():
        pendiente = _pedido('pendiente', dias_entrega=1)
        facturado = _pedido('facturado', dias_entrega=3)

        ids = _ids_listados(logged_client, '?estado=todos')

        assert pendiente.id in ids and facturado.id in ids


def test_el_filtro_de_facturados_sigue_funcionando(app, logged_client):
    with app.app_context():
        _pedido('pendiente', dias_entrega=1)
        facturado = _pedido('facturado', dias_entrega=3)

        assert _ids_listados(logged_client, '?estado=facturado') == [facturado.id]


# === En qué orden ===

def test_lo_mas_vencido_va_primero(app, logged_client):
    """El de 5 días de atraso antes que el de 1, y ambos antes que los futuros."""
    with app.app_context():
        futuro = _pedido('pendiente', dias_entrega=3)
        tarde_1 = _pedido('pendiente', dias_entrega=-1)
        tarde_5 = _pedido('pendiente', dias_entrega=-5)
        hoy = _pedido('pendiente', dias_entrega=0)

        assert _ids_listados(logged_client) == [tarde_5.id, tarde_1.id, hoy.id, futuro.id]


def test_la_urgencia_manda_por_encima_del_estado(app, logged_client):
    """Un preparado con 4 días de atraso va antes que un pendiente de la semana que viene.

    Es el punto del cambio: el vendedor quiere lo más urgente arriba, no todos
    los pendientes arriba.
    """
    with app.app_context():
        pendiente_futuro = _pedido('pendiente', dias_entrega=7)
        preparado_tarde = _pedido('preparado', dias_entrega=-4)

        assert _ids_listados(logged_client) == [preparado_tarde.id, pendiente_futuro.id]


def test_los_pedidos_sin_fecha_de_entrega_van_al_final(app, logged_client):
    """Los históricos tienen `fecha_entrega` NULL: no son urgentes ni deben
    encabezar la lista, pero tampoco desaparecer."""
    with app.app_context():
        sin_fecha = _pedido('pendiente', dias_entrega=None)
        con_fecha = _pedido('pendiente', dias_entrega=9)

        assert _ids_listados(logged_client) == [con_fecha.id, sin_fecha.id]


def test_lo_facturado_va_al_final_en_la_vista_completa(app, logged_client):
    """En «Todos», el trabajo terminado no compite por el tope aunque sea viejo."""
    with app.app_context():
        facturado_viejo = _pedido('facturado', dias_entrega=-30)
        pendiente_futuro = _pedido('pendiente', dias_entrega=5)

        ids = _ids_listados(logged_client, '?estado=todos')

        assert ids == [pendiente_futuro.id, facturado_viejo.id]


# === La pantalla dice qué filtro tiene puesto ===

def _cifra_activa(html, estado):
    """¿La cifra de ese estado se anuncia como seleccionada?"""
    m = re.search(
        r'<button[^>]*data-estado="%s"[^>]*>' % estado, html
    ) or re.search(
        r'<button[^>]*aria-pressed="[^"]*"[^>]*data-estado="%s"[^>]*>' % estado, html
    )
    if not m:
        # el atributo puede venir antes que data-estado
        for tag in re.findall(r'<button[^>]*>', html):
            if f'data-estado="{estado}"' in tag:
                m = type('M', (), {'group': lambda self, n=0: tag})()
                break
    assert m, f'no encontré el botón de {estado}'
    tag = m.group(0)
    return 'aria-pressed="true"' in tag and 'is-active' in tag


def test_al_abrir_se_ve_que_el_filtro_por_preparar_esta_puesto(app, logged_client):
    """Regresión: la pantalla abre filtrada, así que tiene que mostrarlo.

    Ninguna píldora tiene `data-estado="por_preparar"`, de modo que sin marcar
    la cifra la fila de filtros se lee como «sin filtrar» en CADA carga.
    """
    with app.app_context():
        _pedido('pendiente', dias_entrega=1)

        html = logged_client.get('/pedidos').get_data(as_text=True)

        assert _cifra_activa(html, 'por_preparar')
        assert not _cifra_activa(html, 'vencido')


def test_filtrar_por_vencidos_marca_esa_cifra(app, logged_client):
    with app.app_context():
        _pedido('pendiente', dias_entrega=-2)

        html = logged_client.get('/pedidos?estado=vencido').get_data(as_text=True)

        assert _cifra_activa(html, 'vencido')
        assert not _cifra_activa(html, 'por_preparar')


def test_con_todos_ninguna_cifra_queda_marcada(app, logged_client):
    with app.app_context():
        _pedido('pendiente', dias_entrega=1)

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        assert not _cifra_activa(html, 'por_preparar')
        assert not _cifra_activa(html, 'vencido')


# === Regresión: el cliente y el servidor tienen que coincidir en el default ===

def test_el_js_manda_el_estado_explicito_siempre(app, logged_client):
    """El buscador arma su consulta parcial en JS y omitía `estado` cuando valía
    «todos», porque «todos» ERA el default del servidor: omitirlo daba lo mismo
    y dejaba la URL limpia.

    Al pasar el default a `por_preparar`, omitirlo pasó a significar lo
    contrario de lo que el vendedor pidió: tocar «Todos» traía los 16 por
    preparar con la píldora «Todos 26» marcada, y `history.replaceState`
    guardaba esa URL, así que recargar tampoco lo arreglaba.

    Se afirma sobre el template porque el bug vive en el JS embebido: los tests
    que pegaban a `?estado=todos` pasaban porque salteaban justamente esta capa.
    """
    with open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'templates/pedidos.html'), encoding='utf-8') as fh:
        tpl = fh.read()

    assert "!== 'todos'" not in tpl, (
        'el JS no puede omitir `estado` cuando vale «todos»: el default del '
        'servidor ya no es «todos»'
    )


def test_pedir_todos_por_la_ruta_parcial_devuelve_todo(app, logged_client):
    """El mismo camino que usa el buscador en vivo (`partial=1`)."""
    with app.app_context():
        pendiente = _pedido('pendiente', dias_entrega=1)
        facturado = _pedido('facturado', dias_entrega=2)

        html = logged_client.get(
            '/pedidos?estado=todos&partial=1',
            headers={'X-Requested-With': 'fetch'},
        ).get_data(as_text=True)

        assert f'PED-{pendiente.id}' in html
        assert f'PED-{facturado.id}' in html, 'el parcial debe respetar estado=todos'
