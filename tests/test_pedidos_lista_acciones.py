# tests/test_pedidos_lista_acciones.py
"""Las acciones del listado: la confirmación de facturar y el contexto de vuelta.

Los dos bugs que estas pruebas fijan son de la misma familia —la protección
existía, pero no en el lugar donde el código la busca— y ninguno se veía leyendo
la plantilla, porque el atributo estaba escrito y hasta comentado:

1. `data-confirm` de facturar vivía en el `<button>`. `base.js` delega sobre
   `submit`, y ahí `e.target` YA ES el formulario, así que `.closest('form[...]')`
   nunca miraba el botón: la única acción irreversible de la pantalla —crear una
   factura real en QuickBooks, a 8px del tacho de basura— salía sin preguntar,
   mientras que eliminar (recuperable, y con el atributo en el `<form>`) sí
   confirmaba.

2. Facturar y eliminar redirigían SIEMPRE a `/pedidos` pelado en todos sus
   caminos. Como el listado abre por defecto en «Por preparar», quien facturaba
   desde «Facturados», página 3, con una búsqueda puesta, aterrizaba en la
   página 1 sin filtro y sin búsqueda — cuatro veces seguidas si estaba
   facturando los cuatro pedidos listos del día.
"""
import os
import re
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


def _pedido(estado):
    from app import Pedido, Cliente
    p = Pedido(cliente_id=Cliente.query.first().id, estado=estado)
    _db.session.add(p)
    _db.session.commit()
    return p


def _forms(html, accion):
    """Devuelve las etiquetas <form> completas cuyo action contiene `accion`."""
    return [t for t in re.findall(r'<form\b[^>]*>', html, re.S) if accion in t]


# ── 1. La confirmación de facturar ────────────────────────────────────────────

def test_facturar_confirma_en_el_form_no_en_el_boton(logged_client):
    """El guard tiene que estar donde base.js lo busca: en el <form>.

    Si vuelve a mudarse al <button>, la app compila, la plantilla se lee bien y
    facturar deja de preguntar en silencio. Por eso se afirma el elemento y no
    solo la presencia del texto.
    """
    _pedido('preparado')
    html = logged_client.get('/pedidos?estado=preparado').get_data(as_text=True)

    forms = _forms(html, '/facturar')
    assert forms, 'no se renderizó ningún formulario de facturar'
    for f in forms:
        assert 'data-confirm=' in f, (
            'facturar sin confirmación en el <form>: base.js delega sobre '
            '`submit`, donde e.target es el formulario, así que un data-confirm '
            'en el <button> no se lee NUNCA'
        )
        assert 'No se puede deshacer' in f

    # Y que no haya quedado también en el botón, que es de donde vino el bug.
    botones = re.findall(r'<button\b[^>]*>', html, re.S)
    assert not [b for b in botones if 'data-confirm' in b], (
        'quedó un data-confirm en un <button>: no lo lee nadie'
    )


def test_facturar_avisa_que_esta_trabajando(logged_client):
    """El webhook a N8N es síncrono; sin candado el doble toque factura dos veces."""
    _pedido('preparado')
    html = logged_client.get('/pedidos?estado=preparado').get_data(as_text=True)
    assert 'data-submit-label="Facturando' in html


def test_eliminar_sigue_confirmando_y_escala_si_esta_preparado(logged_client):
    _pedido('preparado')
    html = logged_client.get('/pedidos?estado=preparado').get_data(as_text=True)
    forms = _forms(html, '/eliminar')
    assert forms
    assert any('puede tener pesos registrados' in f for f in forms)


# ── 2. El contexto de vuelta ──────────────────────────────────────────────────

def test_los_forms_llevan_a_donde_volver(logged_client):
    _pedido('preparado')
    html = logged_client.get('/pedidos?estado=preparado').get_data(as_text=True)
    destinos = set(re.findall(r'name="next" value="([^"]*)"', html))
    assert destinos, 'los formularios no dicen a dónde volver'
    for d in destinos:
        assert d.startswith('/pedidos'), d
        assert 'estado=preparado' in d, 'el filtro puesto no viaja en el next'


def test_el_next_del_parcial_no_arrastra_partial(logged_client):
    """La búsqueda re-renderiza el parcial; su `next` no puede llevar partial=1.

    Si lo llevara, el redirect después de facturar devolvería el fragmento de
    resultados como si fuera la página entera: sin barra superior, sin pestañas
    y sin estilos de la pantalla.
    """
    _pedido('preparado')
    html = logged_client.get(
        '/pedidos?estado=preparado&partial=1',
        headers={'X-Requested-With': 'fetch'},
    ).get_data(as_text=True)
    destinos = set(re.findall(r'name="next" value="([^"]*)"', html))
    assert destinos
    for d in destinos:
        assert 'partial' not in d, f'el next del parcial arrastra partial=1: {d}'


def test_eliminar_vuelve_al_next(logged_client):
    p = _pedido('pendiente')
    r = logged_client.post(
        f'/pedidos/{p.id}/eliminar',
        data={'next': '/pedidos?estado=facturado&page=3'},
    )
    assert r.status_code == 302
    assert r.headers['Location'] == '/pedidos?estado=facturado&page=3'


def test_sin_next_vuelve_al_listado(logged_client):
    p = _pedido('pendiente')
    r = logged_client.post(f'/pedidos/{p.id}/eliminar', data={})
    assert r.status_code == 302
    assert r.headers['Location'] == '/pedidos'


@pytest.mark.parametrize('malicioso', [
    'https://evil.example.com/x',
    '//evil.example.com/x',
    r'/\evil.example.com',
    'javascript:alert(1)',
])
def test_el_next_no_es_un_open_redirect(logged_client, malicioso):
    p = _pedido('pendiente')
    r = logged_client.post(f'/pedidos/{p.id}/eliminar', data={'next': malicioso})
    assert r.status_code == 302
    assert r.headers['Location'] == '/pedidos', (
        f'«{malicioso}» se aceptó como destino de vuelta'
    )


# ── 3. El orden lo hace el servidor ───────────────────────────────────────────

def test_orden_por_id_lo_resuelve_el_servidor(logged_client):
    """Ordenaba el navegador sobre las 20 filas cargadas de 910: «Total
    descendente» daba el mayor DE ESA PÁGINA, no el mayor."""
    for _ in range(3):
        _pedido('pendiente')

    def ids(url):
        html = logged_client.get(url).get_data(as_text=True)
        return re.findall(r'pedido-id-cell">PED-(\d+)', html)

    asc = ids('/pedidos?estado=todos&orden=id')
    desc = ids('/pedidos?estado=todos&orden=-id')
    assert asc, 'no se renderizó la tabla de escritorio'
    assert asc == sorted(asc, key=int)
    assert desc == sorted(desc, key=int, reverse=True)


def test_orden_desconocido_no_llega_al_order_by(logged_client):
    """El valor entra en un order_by: fuera de la whitelist se ignora."""
    _pedido('pendiente')
    r = logged_client.get('/pedidos?estado=todos&orden=cliente);DROP+TABLE+pedido--')
    assert r.status_code == 200
    from app import Pedido
    assert Pedido.query.count() == 1


def test_total_no_se_ofrece_ordenable(logged_client):
    """Deliberado: el importe que se ve lo calcula Python con peso_real y el SQL
    no lo reproduce, así que cualquier orden de la base se contradiría con la
    columna. Mejor no ofrecerlo que ofrecer uno que miente."""
    _pedido('pendiente')
    html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
    assert 'data-orden="total"' not in html
    assert 'data-orden="id"' in html, 'las columnas que SÍ ordenan bien siguen'


# ── Facturar desde el DETALLE del pedido ──────────────────────────────────────

def test_facturar_desde_el_detalle_tambien_confirma(logged_client):
    """La otra pantalla desde la que se factura, y la que más se usa para eso.

    Tenía el guard invertido: el form de `facturar_pedido` llevaba solo el token
    CSRF, mientras el de «Marcar como preparado» —que es REVERSIBLE— sí
    confirmaba. Y en el listado, un toque atrás, Facturar sí preguntaba con
    estos mismos datos: el vendedor ya había aprendido que pregunta.

    Es la misma clase de fallo que `test_facturar_confirma_en_el_form_no_en_el_boton`
    cuida en el listado, en un archivo distinto que nadie había abierto.
    """
    p = _pedido('preparado')
    html = logged_client.get(f'/pedidos/{p.id}/detalles').get_data(as_text=True)

    forms = _forms(html, '/facturar')
    assert forms, 'el detalle de un pedido preparado no ofrece facturar'
    for f in forms:
        assert 'data-confirm=' in f, (
            'facturar sin confirmación en el <form> del detalle: base.js delega '
            'sobre `submit`, donde e.target es el formulario'
        )
        assert 'No se puede deshacer' in f

    assert 'data-submit-label="Facturando' in html, (
        'falta el candado contra el doble toque'
    )


def test_en_el_detalle_lo_irreversible_avisa_mas_que_lo_reversible(logged_client):
    """La jerarquía de seguridad, afirmada como invariante.

    Marcar como preparado se puede deshacer; facturar escribe en QuickBooks y
    no. El aviso del segundo tiene que ser al menos tan explícito como el del
    primero — estaba al revés.
    """
    p = _pedido('pendiente')
    html = logged_client.get(f'/pedidos/{p.id}/detalles').get_data(as_text=True)
    preparado = _forms(html, '/marcar_preparado')
    assert preparado and 'data-confirm=' in preparado[0], (
        'cambió el aviso de marcar preparado; revisar el invariante'
    )

    p2 = _pedido('preparado')
    html2 = logged_client.get(f'/pedidos/{p2.id}/detalles').get_data(as_text=True)
    facturar = _forms(html2, '/facturar')
    import re
    aviso_facturar = re.search(r'data-confirm="([^"]*)"', facturar[0]).group(1)
    aviso_preparado = re.search(r'data-confirm="([^"]*)"', preparado[0]).group(1)
    assert len(aviso_facturar) > len(aviso_preparado), (
        'el aviso de facturar (irreversible) es más corto que el de preparar '
        '(reversible): la jerarquía de seguridad está invertida'
    )
