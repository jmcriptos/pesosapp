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


def test_el_facturado_sin_entregar_con_fecha_vencida_NO_desaparece():
    """El agujero que motivó todo esto: se factura antes de que salga el
    camión, así que un facturado con la entrega vencida es trabajo que no se
    hizo. Hoy `_agrupar_tablero` lo saltea y nadie se entera."""
    grupos = _agrupar_tablero([_p('facturado', dias=-2)], HOY)
    assert _claves(grupos) == ['atrasados']


def test_el_facturado_de_hoy_es_trabajo_no_archivo():
    grupos = _agrupar_tablero([_p('facturado', dias=0)], HOY)
    assert _claves(grupos) == ['hoy']


def test_el_facturado_futuro_va_a_proximos():
    grupos = _agrupar_tablero([_p('facturado', dias=3)], HOY)
    assert _claves(grupos) == ['proximos']


def test_el_entregado_de_hoy_se_queda_en_hoy():
    """Decisión heredada del spec del tablero: lo hecho no desaparece, se
    marca. Si desapareciera, el tablero se vacía a media tarde y se pierde la
    otra mitad del trabajo, que es ver si el día cerró completo."""
    grupos = _agrupar_tablero([_p('entregado', dias=0)], HOY)
    assert _claves(grupos) == ['hoy']


def test_el_entregado_fuera_de_hoy_es_archivo():
    grupos = _agrupar_tablero(
        [_p('entregado', dias=-30, id=1),
         _p('entregado', dias=None, id=2),
         _p('entregado', dias=9, id=3)],
        HOY,
    )
    assert grupos == []


def test_el_archivo_no_entra_al_tablero():
    """El archivo ahora es `entregado`, no `facturado`: un facturado sin
    entregar es trabajo pendiente, no archivo."""
    grupos = _agrupar_tablero(
        [_p('entregado', dias=-30, id=1),
         _p('entregado', dias=None, id=2),
         _p('entregado', dias=9, id=3)],
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


def test_el_tablero_ofrece_pesar_y_facturar(logged_client):
    """La tarjeta del tablero es la MISMA que la de la lista
    (`_pedido_card_cuerpo.html` es compartido), pero eso nunca se probó
    contra el tablero: los tests de acciones existentes (p.ej.
    `test_pendiente_ofrece_pesar_y_preparado_facturar` en
    test_pedidos_lista_entrega.py) siempre fuerzan modo lista con
    `?estado=todos`. Un pendiente con un producto que SE PESA ofrece
    «Pesar»; un preparado ofrece el formulario de «Facturar»."""
    from app import Producto, DetallePedido, db as _db
    from decimal import Decimal

    p_pend = _crear('pendiente', dias=0)
    prod = Producto(nombre='Pesable', temperatura='-18°C', se_pesa=True,
                     tax_rate=10.0, qbo_id='Q-PESA-TABLERO')
    _db.session.add(prod)
    _db.session.flush()
    _db.session.add(DetallePedido(
        pedido_id=p_pend.id, producto_id=prod.id, cajas=1, cajas_pedidas=1,
        peso=0, precio_unitario=Decimal('10'), subtotal=Decimal('10'),
        es_linea_pedido=True,
    ))
    _db.session.commit()

    p_prep = _crear('preparado', dias=0)

    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'data-tablero="1"' in html, 'este test asume que /pedidos sin parámetros es tablero'

    assert f'/pedidos/{p_pend.id}/pesar' in html
    assert '> Pesar' in html

    assert f'/pedidos/{p_prep.id}/facturar' in html
    assert '> Facturar' in html


def test_el_next_de_facturar_en_el_tablero_es_el_tablero(logged_client):
    """La diferencia de comportamiento más visible entre modos: facturar (o
    eliminar) desde el tablero tiene que volver al tablero, no a una lista
    con `?estado=...` colgando. Hoy eso descansa entera en que
    `request.args` esté vacío en `/pedidos` (ver `url_actual` en
    `lista_pedidos`, app.py) — nada lo fuerza explícitamente, así que un
    cambio ahí podría romperlo sin que ningún otro test lo note."""
    _crear('preparado', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'data-tablero="1"' in html, 'este test asume que /pedidos sin parámetros es tablero'
    assert 'name="next" value="/pedidos"' in html


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
# dos reglas de negocio por su cuenta: qué entregados entran (mismo criterio
# que `_agrupar_tablero`, pero en SQL) y en qué orden. Ninguno de los tests
# de arriba —todos de selección de modo— toca esa consulta. Estos sí.

def test_entregado_viejo_no_aparece_pero_el_facturado_atrasado_si(logged_client):
    """El `or_(Pedido.estado != 'entregado', Pedido.fecha_entrega == hoy_local)`
    de la consulta es una segunda implementación de la misma regla de
    archivo que `_agrupar_tablero` ya aplica sobre la lista en memoria. Si el
    SQL se desincroniza (por ejemplo, alguien lo cambia a `estado !=
    'entregado'` a secas y se olvida del `or_`), un entregado viejo dejaría
    de llegar al tablero directamente y `_agrupar_tablero` nunca tendría la
    oportunidad de descartarlo — el test unitario seguiría en verde.

    Y al revés: un `facturado` viejo (Tarea 3, el agujero que motivó todo
    esto) tiene que SEGUIR llegando —se factura antes de que salga el
    camión, así que un facturado atrasado es trabajo pendiente, no archivo—
    y aparecer en Atrasados.
    """
    entregado_viejo = _crear('entregado', dias=-40)
    facturado_atrasado = _crear('facturado', dias=-40)
    de_hoy = _crear('facturado', dias=0)

    html = logged_client.get('/pedidos').get_data(as_text=True)

    assert f'PED-{de_hoy.id}' in html, (
        'un facturado de HOY debe verse: es el cierre del día'
    )
    assert f'PED-{facturado_atrasado.id}' in html, (
        'un facturado sin entregar es trabajo pendiente, no archivo: debe '
        'verse en Atrasados'
    )
    assert f'PED-{entregado_viejo.id}' not in html, (
        'un entregado viejo es archivo, no tablero'
    )


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

def test_el_entregado_de_hoy_se_ve_marcado_como_hecho(logged_client):
    _crear('entregado', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'tablero-hecho' in html, 'el entregado de hoy no se marca como hecho'


def test_el_facturado_de_hoy_no_se_ve_marcado_como_hecho(logged_client):
    """Test rot legítimo (Tarea 5): este test afirmaba `facturado` marcado
    hecho, que era justamente el agujero que sobrevivió a la Tarea 3 —
    `_agrupar_tablero` ya manda el facturado atrasado a «Atrasados», pero la
    tarjeta seguía decidiendo con su propio `estado == 'facturado'` si iba
    atenuada como «esto ya está». Ahora `entregado` es el único terminal:
    facturar no es entregar, el camión puede seguir sin salir."""
    _crear('facturado', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'tablero-hecho' not in html, 'un facturado sin entregar no está "hecho"'


def test_el_tablero_vacio_no_alarma(logged_client):
    """Un día sin entregas pendientes es un día bien cerrado, no un error.

    Se afirma sobre el bloque del vacío y NO sobre la página entera: el aviso
    de red (`#pedidos-error`) vive fuera del tablero y está en el HTML siempre,
    escondido. Buscar «error» en toda la página lo encontraría y el test
    fallaría sin que nada esté mal.

    El texto pasó por dos vueltas. Primero decía «Nada para entregar hoy»;
    después «No hay entregas pendientes / El día está cerrado», para no hablar
    solo del día cuando `grupos` vacío significa más que eso. La cuarta crítica
    señaló que esa segunda versión afirma algo que la pantalla no puede saber:
    a las 7 de la mañana el día no cerró, todavía no se cargó nada. Ahora dice
    lo único que es cierto a cualquier hora.

    Y el botón de «cargar un pedido» se fue: duplicaba el «+ Nuevo» del hero a
    250px de distancia, con el mismo verde. Queda la puerta al archivo, que con
    942 pedidos facturados es a lo que la gente viene cuando el tablero está
    vacío.
    """
    import re
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'Nada que entregar hoy' in html
    assert 'Los pedidos con fecha de entrega aparecen acá' in html

    bloque = re.search(r'tablero-vacio.*?(?=</div>\s*(?:<a|\{|</div>))', html, re.S)
    assert bloque, 'no se renderizó el bloque de vacío'
    texto = bloque.group(0).lower()
    for palabra in ('error', 'falló', 'no se pudo', 'problema'):
        assert palabra not in texto, f'el vacío del tablero alarma: «{palabra}»'

    # Y ofrece la salida al archivo, que es lo que hace falta un día vacío.
    # NO ofrece «cargar un pedido»: eso duplicaba el «+ Nuevo» del hero.
    assert 'estado=todos' in texto, 'el vacío no ofrece la puerta al archivo'
    assert 'cargar un pedido' not in texto.lower(), (
        'volvió el botón que duplica el «+ Nuevo» del hero'
    )


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


# ── Orden dentro del grupo y avance del día ──────────────────────────────────

def test_dentro_de_hoy_lo_pendiente_va_arriba_y_lo_entregado_al_final():
    """La consulta ordena por fecha y después por id descendente, y el id no
    dice nada del trabajo: en «Hoy» —todos con la misma fecha— el orden
    quedaba al azar del alta y en producción favorecía a lo terminado. Quien
    abre el tablero busca qué toca ahora, no qué ya salió."""
    grupos = _agrupar_tablero(
        [_p('entregado', dias=0, id=9),
         _p('facturado', dias=0, id=8),
         _p('preparado', dias=0, id=7),
         _p('pendiente', dias=0, id=6)],
        HOY,
    )
    assert [p.estado for p in _pedidos_de(grupos, 'hoy')] == [
        'pendiente', 'preparado', 'facturado', 'entregado',
    ]


def test_la_fecha_sigue_mandando_sobre_la_etapa():
    """En Atrasados el más atrasado va primero sea cual sea su estado: un
    facturado de hace una semana es más urgente que un pendiente de ayer."""
    grupos = _agrupar_tablero(
        [_p('pendiente', dias=-1, id=1),
         _p('facturado', dias=-7, id=2)],
        HOY,
    )
    assert [p.id for p in _pedidos_de(grupos, 'atrasados')] == [2, 1]


def test_a_fecha_y_etapa_iguales_se_conserva_el_orden_de_la_consulta():
    """El sort es estable: dos pendientes de hoy quedan como llegaron
    (id descendente, que es lo que trae el SQL)."""
    grupos = _agrupar_tablero(
        [_p('pendiente', dias=0, id=5), _p('pendiente', dias=0, id=3)],
        HOY,
    )
    assert [p.id for p in _pedidos_de(grupos, 'hoy')] == [5, 3]


def test_un_estado_desconocido_no_se_hunde():
    """Ante la duda, arriba, donde se ve: un estado que la tabla no conoce
    ordena como pendiente, no como entregado."""
    grupos = _agrupar_tablero(
        [_p('entregado', dias=0, id=2), _p('raro', dias=0, id=1)],
        HOY,
    )
    assert [p.id for p in _pedidos_de(grupos, 'hoy')] == [1, 2]


def test_el_titulo_de_hoy_dice_cuantos_salieron(logged_client):
    _crear('entregado', dias=0)
    _crear('pendiente', dias=0)
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert '1 de 3 entregados' in html, 'el título de «Hoy» no muestra el avance'


def test_el_titulo_de_hoy_no_afirma_un_cero(logged_client):
    """«0 de 2 entregados» pone un cero donde todavía no pasó nada."""
    _crear('pendiente', dias=0)
    _crear('preparado', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'tablero-avance' not in _sin_scripts(html)


def test_el_titulo_de_hoy_celebra_el_dia_cerrado(logged_client):
    _crear('entregado', dias=0)
    _crear('entregado', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'todo entregado' in html
    assert 'tablero-avance-completo' in html


def test_el_avance_es_solo_de_hoy(logged_client):
    """Atrasados y Próximos no llevan entregados (son archivo fuera de hoy),
    así que un avance ahí sería siempre «0 de N»: no se dibuja."""
    _crear('pendiente', dias=-1)
    _crear('pendiente', dias=3)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'tablero-avance' not in _sin_scripts(html)


def test_el_titulo_pegajoso_asoma_debajo_de_la_barra_superior():
    """`.app-topbar` también es sticky, con 48px (+safe-area) en el teléfono
    y 78px en escritorio, y un z-index mayor. Con `top: 0` el título se
    pegaba detrás de la barra y nunca se veía. Se afirma sobre el CSS servido
    porque no hay navegador en la suite; la medida real (elementFromPoint
    sobre el título a mitad de scroll) se hizo a mano en los dos tamaños."""
    import re
    css = open('static/css/pedidos_list.css', encoding='utf-8').read()
    bloque = re.search(
        r'\.tablero-titulo\s*\{[^}]*position:\s*sticky;[^}]*\}', css, re.S
    )
    assert bloque, 'el título del grupo ya no es sticky'
    assert 'top: calc(48px + env(safe-area-inset-top, 0px))' in bloque.group(0)
    assert re.search(
        r'@media \(min-width: 1024px\)\s*\{\s*body\[data-pedidos-list-screen\] '
        r'\.tablero-titulo\s*\{\s*top: 78px;', css
    ), 'falta el desplazamiento de escritorio bajo la barra de 78px'


# ── Pasada de UI (2026-10-13) ────────────────────────────────────────────────

def _css_pedidos():
    return open('static/css/pedidos_list.css', encoding='utf-8').read()


def test_la_tarjeta_tiene_una_sola_columna_de_texto():
    """`pedidos_inline.css` (la piel oscura vieja) le deja a `.pc-top` y a
    `.pc-meta` un padding horizontal de 16px que se sumaba al de la tarjeta:
    el cliente arrancaba en x=46 y las acciones en x=30. Se anulan."""
    import re
    css = _css_pedidos()
    assert re.search(r'\.pc-top\s*\{\s*padding:\s*0\s*!important;', css)
    assert re.search(r'\.pc-meta\s*\{\s*padding:\s*0\s*!important;', css)


def test_la_tarjeta_hecha_del_tablero_es_compacta():
    """Un entregado no necesita «entrega hoy», «2 líneas» ni la nota: ya
    salió. Se esconden solo bajo `.tablero-hecho`, o sea solo en el tablero;
    en el archivo la tarjeta sigue entera."""
    import re
    css = _css_pedidos()
    assert re.search(
        r'\.tablero-hecho \.pc-nota,\s*body\[data-pedidos-list-screen\] '
        r'\.tablero-hecho \.pc-meta\s*\{\s*display:\s*none\s*!important;', css
    )


def test_las_formas_de_accion_no_se_estiran():
    """El <form> hereda un `width: 100%` global y como ítem flex se quedaba
    con todo el sobrante: «Facturar» a la izquierda con un hueco, y Deshacer
    solo en la punta. La acción principal va a la izquierda a propósito, con
    `margin-right: auto`; el resto se agrupa a la derecha."""
    import re
    css = _css_pedidos()
    assert re.search(
        r'\.pc-actions \.pc-action-form\s*\{\s*width:\s*auto\s*!important;\s*'
        r'flex:\s*0 0 auto\s*!important;', css
    )
    assert '.pc-actions > .pc-action-form-main' in css
    assert 'margin-right: auto !important' in css


def test_facturar_y_entregar_llevan_la_clase_de_accion_principal(logged_client):
    """Sin la clase, el <form> de «Facturar» o «Entregado» no recibe el
    `margin-right: auto` y la fila vuelve a depender de la etiqueta HTML."""
    from app import Producto, DetallePedido, db as _db
    from decimal import Decimal
    p = _crear('preparado', dias=0)
    f = _crear('facturado', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert html.count('pc-action-form pc-action-form-main') == 2, (
        'Facturar (preparado) y Entregado (facturado) deben ser la acción '
        'principal de su fila'
    )


# ── Crítica de diseño del 2026-10-13 ─────────────────────────────────────────

def test_la_fila_entregar_llega_al_piso_de_toque():
    """«Hoy», «Mañana» y el selector de fecha medían 34px: los únicos
    controles de la tarjeta por debajo de los 48px que DESIGN.md fija como
    mínimo. Medido en el render a 390px tras el cambio: 48px los tres y la
    fila sigue en una sola línea (57px con padding y borde)."""
    import re
    css = _css_pedidos()
    assert re.search(
        r'\.pc-entrega-btn\s*\{\s*min-height:\s*var\(--touch-min, 48px\);', css
    ), 'los botones Hoy/Mañana volvieron a estar por debajo de 48px'
    assert re.search(
        r'input\.pc-entrega-fecha\s*\{\s*min-height:\s*var\(--touch-min, 48px\);\s*'
        r'height:\s*var\(--touch-min, 48px\);', css
    ), 'el selector de fecha volvió a estar por debajo de 48px'


def test_el_nombre_del_cliente_se_lee_en_dos_lineas():
    """4 de 10 nombres de la muestra se cortaban con elipsis a 390px. Es el
    dato que el chofer busca; dos líneas antes que un `title` que en táctil
    no existe."""
    import re
    css = _css_pedidos()
    bloque = re.search(
        r'\.pc-client\s*\{\s*white-space:\s*normal;[^}]*-webkit-line-clamp:\s*2;[^}]*\}',
        css, re.S,
    )
    assert bloque, 'el nombre del cliente volvió a una sola línea con elipsis'
    # La regla nueva tiene que ir DESPUÉS de la vieja (nowrap + ellipsis) para
    # ganarle a igual especificidad.
    assert css.find('text-overflow: ellipsis') < bloque.start()


def test_el_buscador_comparte_fila_con_el_titulo(logged_client):
    """Título, buscador y «Nuevo» van en un solo `<header class="hero">`:
    medido a 390px, el hero de 68px más el buscador de 52px debajo dejaban
    el primer grupo en y=244 y solo dos tarjetas en la primera pantalla.
    Ahora el primer grupo arranca en y=140 y entran tres."""
    import re
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    hero = re.search(r'<header class="hero">(.*?)</header>', html, re.S)
    assert hero, 'falta el hero'
    assert 'class="filter-bar"' in hero.group(1), 'el buscador salió del hero'
    assert 'btn-nuevo-pedido' in hero.group(1), 'escritorio no tiene barra inferior: «Nuevo» tiene que seguir en el hero'
    css = _css_pedidos()
    assert re.search(
        r'@media \(max-width: 1023px\)\s*\{\s*body\[data-pedidos-list-screen\] '
        r'\.hero \.btn-nuevo-pedido\s*\{\s*display:\s*none\s*!important;', css
    ), 'bajo 1024px la barra inferior ya tiene «Nuevo»: el del hero se esconde'


# ── Lo que toca ahora pesa más ───────────────────────────────────────────────

def test_atrasados_y_hoy_sin_entregar_son_ahora(logged_client):
    """Tres niveles: «ahora» (Atrasados y Hoy sin entregar) lleva la acción
    principal en sólido; Próximos y Sin fecha no; un entregado de Hoy es
    «hecho», nunca «ahora»."""
    import re
    atrasado = _crear('pendiente', dias=-2)
    hoy = _crear('preparado', dias=0)
    hoy_hecho = _crear('entregado', dias=0)
    proximo = _crear('pendiente', dias=3)
    sin_fecha = _crear('pendiente', dias=None)
    html = logged_client.get('/pedidos').get_data(as_text=True)

    def clases_de(p):
        # La tarjeta es el <div class="pedido-card …"> cuyo data-href termina
        # en el id del pedido; la forma exacta de la ruta no importa acá.
        m = re.search(r'<div class="(pedido-card[^"]*)"\s+data-href="/pedidos/%d/detalles"' % p.id, html)
        assert m, f'no se encontró la tarjeta de PED-{p.id}'
        return m.group(1).split()

    assert 'tablero-ahora' in clases_de(atrasado)
    assert 'tablero-ahora' in clases_de(hoy)
    assert 'tablero-ahora' not in clases_de(hoy_hecho)
    assert 'tablero-hecho' in clases_de(hoy_hecho)
    assert 'tablero-ahora' not in clases_de(proximo)
    assert 'tablero-ahora' not in clases_de(sin_fecha)


def test_el_solido_de_ahora_pasa_aa():
    """El botón sólido lleva texto de 13px/700 en blanco: necesita 4,5:1.
    Índigo de Lectura nominal (#6366f1) da 4,07; Honda (#4f46e5) da 5,9.
    Medido en el render: 6,29:1."""
    import re
    css = _css_pedidos()
    assert re.search(
        r'\.tablero-ahora \.pc-actions \.pc-action-main\s*\{\s*background:\s*#4f46e5;\s*color:\s*#ffffff;',
        css,
    ), 'el sólido de «ahora» tiene que ir en #4f46e5 con texto blanco'
    assert '#6366f1;\n  color: #ffffff' not in css


# ── Reestructura de la tarjeta: el cliente primero ───────────────────────────

def test_la_tarjeta_abre_con_el_cliente_y_el_id_va_a_la_derecha(logged_client):
    """Antes la primera fila era «PED-1» más la píldora y el cliente iba
    segundo. Ahora `.pc-top` lleva el cliente a la izquierda y el id a la
    derecha, y la píldora baja a la línea de contexto."""
    import re
    p = _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    top = re.search(r'<div class="pc-top">(.*?)</div>\s*<div class="pc-contexto">', html, re.S)
    assert top, 'falta la cabecera o la línea de contexto'
    assert 'pc-client' in top.group(1)
    assert f'<span class="pc-id">PED-{p.id}</span>' in top.group(1)
    assert 'status-pill' not in top.group(1), 'la píldora ya no va en la cabecera'
    assert 'pc-amt' not in top.group(1), 'el importe ya no va en la esquina'


def test_la_linea_de_contexto_lleva_estado_fecha_e_importe(logged_client):
    import re
    _crear('pendiente', dias=-2)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    ctx = re.search(r'<div class="pc-contexto">(.*?)</div>\s*(?:<p class="pc-nota"|<div class="pc-foot">)', html, re.S)
    assert ctx, 'falta la línea de contexto'
    c = ctx.group(1)
    assert 'status-pill pendiente' in c
    assert 'pc-fecha' in c and 'd tarde' in c
    assert 'pc-amt' in c


def test_en_el_telefono_las_lineas_no_se_dibujan_y_las_tarjetas_miden_igual():
    """«N líneas» no decide nada en ruta y le quitaba sitio a la fecha y al
    importe; se esconde bajo 480px CON `.pc-contexto` en el selector, porque
    un `.pc-lineas` suelto perdía contra la regla que lo pone inline-flex.
    Y la lista deja de traer un padding de 16px que hacía su tarjeta 34px más
    angosta que la del tablero: medido, 364px en los dos modos."""
    import re
    css = _css_pedidos()
    assert re.search(
        r'@media \(max-width: 479px\)\s*\{\s*body\[data-pedidos-list-screen\] '
        r'\.pc-contexto \.pc-lineas\s*\{\s*display:\s*none;', css
    )
    assert re.search(r'\.pedidos-list\s*\{\s*padding:\s*0\s*!important;', css)


# ── La tarjeta es el botón (variante C) ──────────────────────────────────────

def test_la_tarjeta_ofrece_una_sola_accion_a_lo_ancho(logged_client):
    """Una acción visible por tarjeta, con verbo y objeto. Lo demás va
    detrás del «⋯» (un <details>, sin JS)."""
    import re
    from app import Producto, DetallePedido, db as _db
    from decimal import Decimal
    p = _crear('pendiente', dias=0)
    prod = Producto(nombre='Pesable', temperatura='-18°C', se_pesa=True,
                    tax_rate=10.0, qbo_id='Q-C')
    _db.session.add(prod); _db.session.flush()
    _db.session.add(DetallePedido(pedido_id=p.id, producto_id=prod.id, cajas=1,
                                  cajas_pedidas=1, peso=0, precio_unitario=Decimal('10'),
                                  subtotal=Decimal('10'), es_linea_pedido=True))
    _db.session.commit()
    _crear('preparado', dias=0)
    _crear('facturado', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert '> Pesar este pedido' in html
    assert '> Facturar en QuickBooks' in html
    assert '> Marcar entregado' in html
    # Cada etapa con su clase (y su color): pesar/preparar ámbar, facturar
    # índigo, entregar verde. Eran los tres el mismo índigo y se confundían.
    assert 'class="pc-action-main pc-go pc-go-pesar"' in html
    assert 'class="pc-action-main pc-go pc-go-facturar"' in html
    assert 'class="pc-action-main pc-go pc-go-entregar"' in html
    assert html.count('class="pc-action-main pc-go pc-go-') == 3
    # Nada más a la vista: editar, eliminar y mover la entrega viven en el panel.
    assert 'pc-action-btn' not in html
    for tarjeta in re.findall(r'<details class="pc-mas">(.*?)</details>', html, re.S):
        assert 'pc-menu' in tarjeta


def test_el_panel_de_mas_lleva_lo_que_salio_de_la_tarjeta(logged_client):
    import re
    p = _crear('pendiente', dias=0)
    f = _crear('entregado', dias=0)
    f.invoice_id_qbo = '77'; f.doc_number_qbo = '1077'
    from app import db as _db
    _db.session.commit()
    html = logged_client.get('/pedidos').get_data(as_text=True)
    paneles = re.findall(r'<details class="pc-mas">(.*?)</details>', html, re.S)
    assert len(paneles) == 2
    pendiente = next(x for x in paneles if f'/pedidos/{p.id}/' in x or f'PED-{p.id}' in x)
    assert 'pc-entrega' in pendiente and 'name="atajo"' in pendiente
    assert '> Editar' in pendiente and '> Eliminar' in pendiente
    entregado = next(x for x in paneles if x is not pendiente)
    assert 'Factura PDF' in entregado and 'Revisar precios' in entregado
    assert 'Deshacer entrega' in entregado and 'fa-rotate-left' in entregado
    assert 'pc-entrega' not in entregado, 'un entregado no se mueve de día'
    assert 'Fact. 1077' in html, 'el número de factura va con palabra en la línea de contexto'


def test_el_toque_sobre_el_menu_no_abre_el_pedido():
    """La tarjeta entera navega al detalle, salvo lo que se toca dentro del
    <details>. Y el cierre del «⋯» anterior tiene que estar ANTES del
    `return` del tablero, si no solo valdría en el modo lista."""
    html = open('templates/pedidos.html', encoding='utf-8').read()
    assert html.count("if (event.target.closest('details')) return;") == 2
    assert html.index("addEventListener('toggle'") < html.index('var enTablero')


def test_cada_etapa_tiene_su_color_y_pasa_aa():
    """Medido en el render a 390px: pesar/preparar ámbar con tinta oscura
    8,3:1, facturar índigo 6,3:1, entregar verde 5,5:1; las versiones suaves
    de «luego» 6,4:1. El ámbar con texto blanco daría 2,3:1: por eso lleva
    texto oscuro, y este test lo vigila."""
    import re
    css = _css_pedidos()
    assert re.search(r'\.tablero-ahora \.pc-actions \.pc-go-pesar,\s*body\[data-pedidos-list-screen\] '
                     r'\.tablero-ahora \.pc-actions \.pc-go-preparar\s*\{\s*background:\s*#f59e0b;\s*color:\s*#0f172a;', css)
    assert re.search(r'\.tablero-ahora \.pc-actions \.pc-go-entregar\s*\{\s*background:\s*#047857;\s*color:\s*#ffffff;', css)
