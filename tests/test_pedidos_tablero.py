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


def test_al_borrar_la_busqueda_se_vuelve_al_tablero(logged_client):
    """Sin parámetros con valor, vuelve el tablero. Es el contrato que hace
    que borrar el buscador devuelva al trabajo del día."""
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos?q=').get_data(as_text=True)
    assert 'data-tablero="1"' in html


def test_el_tablero_incluye_la_rama_de_busqueda_del_js(logged_client):
    """Guarda de humo, no de comportamiento: este proyecto no tiene suite de
    JS, así que no se puede ejercitar acá el debounce, `enTablero` ni el
    submit nativo del form. Lo único que este test afirma es que la rama de
    JS que hace que buscar desde el tablero navegue a la lista (`var
    enTablero = ...`, en templates/pedidos.html) sigue presente en el HTML
    servido. Si alguien la borra en un refactor sin querer, este test avisa;
    si la rompe de otra forma (typo en el nombre del evento, url_for mal
    armado, etc.), este test NO lo detecta — para eso hace falta un navegador
    de verdad, como en la verificación manual de la Tarea 4."""
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'data-tablero="1"' in html, 'este test asume que /pedidos es tablero'
    assert 'enTablero' in html, 'se perdió la rama de búsqueda del tablero'


def test_un_parametro_reconocido_devuelve_la_lista(logged_client):
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
    assert 'data-tablero="1"' not in html
    # `filter-pill` a secas también aparece en el <script> inline (selectores
    # y comentarios de pedidos.html): `filter-pill-count` solo existe en el
    # markup real de cada píldora.
    assert 'filter-pill-count' in html, 'la lista conserva sus píldoras'


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
    pedido = _crear('facturado', dias=-40)
    html = logged_client.get('/pedidos?q=Cliente').get_data(as_text=True)
    # Presencia del pedido buscado, no ausencia de una clase: así el test
    # prueba lo que su nombre dice y no se muere si alguien renombra
    # `pedidos-empty`.
    assert f'PED-{pedido.id}' in html, (
        'la búsqueda sin `estado` explícito no alcanzó el archivo'
    )


# ── Consulta del tablero a nivel de ruta ────────────────────────────────────
#
# `_agrupar_tablero` (Tarea 1) ya está cubierta a nivel unitario: reparte una
# lista en memoria. Pero la ruta arma esa lista con SU PROPIA consulta SQL
# (`base_query_tablero.filter(or_(...))...order_by(...)`), que reimplementa
# dos reglas de negocio por su cuenta: qué facturados entran (mismo criterio
# que `_agrupar_tablero`, pero en SQL) y en qué orden. Ninguno de los tests
# de arriba —todos de selección de modo— toca esa consulta. Estos sí.

def test_facturado_viejo_no_aparece_pero_el_de_hoy_si(logged_client):
    """El `or_(Pedido.estado != 'facturado', Pedido.fecha_entrega == hoy_local)`
    de la consulta es una segunda implementación de la misma regla de
    archivo que `_agrupar_tablero` ya aplica sobre la lista en memoria. Si el
    SQL se desincroniza (por ejemplo, alguien lo cambia a `estado !=
    'facturado'` a secas y se olvida del `or_`), un facturado viejo dejaría
    de llegar al tablero directamente y `_agrupar_tablero` nunca tendría la
    oportunidad de descartarlo — el test unitario seguiría en verde.
    """
    viejo = _crear('facturado', dias=-40)
    de_hoy = _crear('facturado', dias=0)

    html = logged_client.get('/pedidos').get_data(as_text=True)

    assert f'PED-{de_hoy.id}' in html, (
        'un facturado de HOY debe verse: es el cierre del día'
    )
    assert f'PED-{viejo.id}' not in html, 'un facturado viejo es archivo, no tablero'


def test_el_orden_del_tablero_es_mas_atrasado_primero_y_sin_fecha_al_final(logged_client):
    """El orden es responsabilidad de la consulta
    (`.order_by(Pedido.fecha_entrega.asc().nullslast(), Pedido.id.desc())`),
    no de `_agrupar_tablero` —que reparte, no ordena—. Los tests unitarios de
    la Tarea 1 verifican el orden ENTRE grupos (atrasados antes que hoy,
    antes que próximos, antes que sin fecha); ninguno verifica el orden
    DENTRO de un grupo, porque reciben la lista ya armada a mano. Este test
    cubre lo que falta: que el SQL de verdad ordene por urgencia.
    """
    mas_atrasado = _crear('pendiente', dias=-10)
    menos_atrasado = _crear('pendiente', dias=-1)
    sin_fecha = _crear('pendiente', dias=None)

    html = logged_client.get('/pedidos').get_data(as_text=True)

    pos_mas = html.find(f'PED-{mas_atrasado.id}')
    pos_menos = html.find(f'PED-{menos_atrasado.id}')
    pos_sin_fecha = html.find(f'PED-{sin_fecha.id}')

    assert -1 not in (pos_mas, pos_menos, pos_sin_fecha), (
        'faltó algún pedido en el tablero'
    )
    assert pos_mas < pos_menos, (
        'dentro de "Atrasados", el más atrasado (dias=-10) debe ir primero'
    )
    assert pos_menos < pos_sin_fecha, (
        'los pedidos sin fecha van al final ("Sin fecha de entrega")'
    )


def test_el_tablero_respeta_los_clientes_visibles_del_vendedor(app):
    """El filtro de permisos que blinda la lista tiene que blindar también
    la consulta propia del tablero.

    `base_query_tablero = base_query` es un alias POSICIONAL: se copia
    después del filtro `Pedido.cliente_id.in_(clientes_ids)` (aplicado más
    arriba, para vendedores no super_admin) pero antes de los filtros de
    bandeja. Hoy el código está bien — pero si un refactor mueve esa línea
    por encima del filtro de clientes visibles, el tablero de un vendedor
    empezaría a mostrar pedidos de territorio ajeno EN SILENCIO, con la
    suite en verde salvo por este test.
    """
    from datetime import datetime
    from app import (Rol, Vendedor, Cliente, ClienteVendedor, Pedido,
                      Territorio, db as _db, DASHBOARD_TIMEZONE)

    territorio = Territorio.query.first()
    cliente_visible = Cliente.query.filter_by(nombre='Cliente Uno').first()
    cliente_ajeno = Cliente(nombre='Cliente Ajeno', territorio_id=territorio.id)
    _db.session.add(cliente_ajeno)

    rol_vendedor = Rol(nombre='vendedor', descripcion='Vendedor')
    _db.session.add(rol_vendedor)
    _db.session.flush()

    vendedor = Vendedor(
        username='vend_limitado', email='vend_limitado@test.com',
        nombre_completo='Vendedor Limitado', rol_id=rol_vendedor.id,
        territorio_id=territorio.id, activo=True,
    )
    vendedor.set_password('testpass')
    _db.session.add(vendedor)
    _db.session.flush()

    # Solo asignado al cliente visible; el ajeno queda fuera a propósito.
    _db.session.add(ClienteVendedor(
        cliente_id=cliente_visible.id, vendedor_id=vendedor.id, activo=True,
    ))
    _db.session.commit()

    hoy = datetime.now(DASHBOARD_TIMEZONE).date()
    p_visible = Pedido(cliente_id=cliente_visible.id, estado='pendiente',
                       fecha_entrega=hoy)
    p_ajeno = Pedido(cliente_id=cliente_ajeno.id, estado='pendiente',
                     fecha_entrega=hoy)
    _db.session.add_all([p_visible, p_ajeno])
    _db.session.commit()

    cliente_test = app.test_client()
    cliente_test.post('/login', data={'username': 'vend_limitado',
                                      'password': 'testpass'},
                      follow_redirects=True)
    html = cliente_test.get('/pedidos').get_data(as_text=True)

    assert f'PED-{p_visible.id}' in html, (
        'el pedido de un cliente asignado debe verse en el tablero'
    )
    assert f'PED-{p_ajeno.id}' not in html, (
        'el tablero mostró un pedido de un cliente que este vendedor no '
        'tiene asignado — fuga de datos entre territorios'
    )


# ── El tablero de verdad (Tarea 3) ──────────────────────────────────────────

def test_el_facturado_de_hoy_se_ve_marcado_como_hecho(logged_client):
    _crear('facturado', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'tablero-hecho' in html, 'el facturado de hoy no se marca como hecho'


def test_el_tablero_vacio_no_alarma(logged_client):
    """Un día sin entregas pendientes es un día bien cerrado, no un error.

    Se afirma sobre el bloque del vacío y NO sobre la página entera: el aviso
    de red (`#pedidos-error`) vive fuera del tablero y está en el HTML siempre,
    escondido. Buscar «error» en toda la página lo encontraría y el test
    fallaría sin que nada esté mal.
    """
    import re
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'Nada para entregar hoy' in html
    bloque = re.search(r'tablero-vacio.*?</div>', html, re.S)
    assert bloque, 'no se renderizó el bloque de vacío'
    texto = bloque.group(0).lower()
    for palabra in ('error', 'falló', 'no se pudo', 'problema'):
        assert palabra not in texto, f'el vacío del tablero alarma: «{palabra}»'


def test_el_tablero_ofrece_la_salida_al_archivo(logged_client):
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'estado=todos' in html, 'falta el enlace de escape al archivo'


def test_el_tablero_corta_en_50_por_grupo(logged_client):
    for i in range(55):
        _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert html.count('tablero-fila') <= 50
    assert 'y 5 más' in html
    # El corte de filas no debe descuadrar el encabezado: dice cuántos hay
    # de verdad (55), no cuántos se dibujaron (50).
    assert '<span class="tablero-cuenta">55</span>' in html, (
        'el encabezado del grupo miente sobre cuántos pedidos hay'
    )
