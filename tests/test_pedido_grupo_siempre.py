# tests/test_pedido_grupo_siempre.py
"""El grupo de facturación se elige SIEMPRE, sea cual sea el historial.

Antes la pantalla de grupos aparecía solo si el cliente compraba de dos o más:
con uno solo (o sin historial) el sistema elegía por el vendedor, que es de
donde salió el bug de Luna Park —28 pedidos de importados y ninguna forma de
pedirle pesables—. Ahora las opciones salen del CATÁLOGO, en orden fijo, y el
historial del cliente decora cada tarjeta en vez de decidir cuáles se ven.

Diseño: docs/superpowers/specs/2026-08-19-grupo-siempre-elegido-design.md
"""
import os
import re
import pytest
from datetime import datetime, timedelta

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
        from app import Rol, Territorio, Vendedor, Cliente, Producto

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()

        vendedor = Vendedor(
            username='admin', email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)

        # Los tres perfiles de cliente que antes tomaban caminos distintos.
        for nombre in ('Multigrupo', 'Un Solo Grupo', 'Sin Historial'):
            _db.session.add(Cliente(nombre=nombre, territorio_id=territorio.id))

        # Los tres grupos de producción: `se_pesa` NO determina el impuesto.
        for nombre, se_pesa, tax in [
            ('Aceite vegetal 12 x 1 L', False, 10.0),        # imp:10, importado
            ('Atun en lata 24 x 170 g', False, 10.0),        # imp:10, importado
            ('Chuleta de cerdo ahumada 5 kg', True, 10.0),   # imp:10, pesable
            ('Salchicha Frankfurter 2.5 kg', True, 10.0),    # imp:10, pesable
            ('Ham di Pasku 4 kg', True, 14.0),               # imp:14, pesable
        ]:
            _db.session.add(Producto(
                nombre=nombre, descripcion='x', temperatura='Congelado',
                se_pesa=se_pesa, tax_rate=tax,
            ))
        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin', 'password': 'testpass',
    }, follow_redirects=True)
    return client


def _cliente(nombre):
    from app import Cliente
    return Cliente.query.filter_by(nombre=nombre).first()


def _producto(nombre):
    from app import Producto
    return Producto.query.filter_by(nombre=nombre).first()


def _crear_pedido(cliente_id, producto_nombre, cajas=3, dias_atras=0):
    from app import Pedido, DetallePedido
    pedido = Pedido(
        cliente_id=cliente_id,
        fecha_pedido=datetime.utcnow() - timedelta(days=dias_atras),
    )
    _db.session.add(pedido)
    _db.session.flush()
    _db.session.add(DetallePedido(
        pedido_id=pedido.id, producto_id=_producto(producto_nombre).id,
        cajas=cajas, cajas_pedidas=cajas,
        precio_unitario=10, subtotal=10 * cajas, es_linea_pedido=True,
    ))
    _db.session.commit()
    return pedido


def _sembrar_historial():
    """Cada cliente con el historial que antes lo mandaba por otro camino."""
    multi = _cliente('Multigrupo')
    _crear_pedido(multi.id, 'Chuleta de cerdo ahumada 5 kg', dias_atras=9)
    _crear_pedido(multi.id, 'Ham di Pasku 4 kg', dias_atras=4)

    uno = _cliente('Un Solo Grupo')
    _crear_pedido(uno.id, 'Aceite vegetal 12 x 1 L', dias_atras=7)
    _crear_pedido(uno.id, 'Aceite vegetal 12 x 1 L', dias_atras=2)


def _claves_en_orden(html):
    """Las claves de grupo tal como salen enlazadas en la pantalla."""
    return re.findall(r'grupo=([a-z]+(?::|%3A)\d+)', html.replace('&amp;', '&'))


# ── La pantalla aparece para todos ─────────────────────────────────────────

@pytest.mark.parametrize('nombre', ['Multigrupo', 'Un Solo Grupo', 'Sin Historial'])
def test_todo_cliente_pasa_por_la_pantalla_de_grupos(app, logged_client, nombre):
    _sembrar_historial()
    cliente = _cliente(nombre)

    html = logged_client.get(f'/pedidos/nuevo?cliente={cliente.id}').get_data(as_text=True)

    assert 'data-paso="cliente"' in html
    assert 'Qué pedido vas a tomar' in html
    # Y NO el paso de armar el pedido: nada se precarga antes de elegir.
    assert 'id="form-nuevo-pedido"' not in html


@pytest.mark.parametrize('nombre', ['Multigrupo', 'Un Solo Grupo', 'Sin Historial'])
def test_las_opciones_son_las_mismas_para_todos(app, logged_client, nombre):
    """Salen del catálogo, no del historial: mismas tres, siempre."""
    _sembrar_historial()
    cliente = _cliente(nombre)

    html = logged_client.get(f'/pedidos/nuevo?cliente={cliente.id}').get_data(as_text=True)

    assert _claves_en_orden(html) == ['imp:10', 'imp:14']


def test_el_orden_no_depende_del_historial(app, logged_client):
    """Importados primero, después pesables por impuesto ascendente.

    La posición fija es lo que deja aprender el gesto: ordenar por «lo último
    que compró» movía las opciones de sitio entre un cliente y otro.
    """
    _sembrar_historial()
    # El multigrupo compró imp:14 lo último; el otro solo del imp:10.
    a = _claves_en_orden(logged_client.get(
        f"/pedidos/nuevo?cliente={_cliente('Multigrupo').id}").get_data(as_text=True))
    b = _claves_en_orden(logged_client.get(
        f"/pedidos/nuevo?cliente={_cliente('Un Solo Grupo').id}").get_data(as_text=True))

    assert a == b == ['imp:10', 'imp:14']


def test_un_grupo_nuevo_del_catalogo_entra_en_su_posicion(app, logged_client):
    """La lista se deriva del catálogo: un impuesto nuevo no necesita código."""
    from app import Producto
    _db.session.add(Producto(
        nombre='Producto exótico', descripcion='x', temperatura='Congelado',
        se_pesa=False, tax_rate=5.0,
    ))
    _db.session.commit()

    html = logged_client.get(
        f"/pedidos/nuevo?cliente={_cliente('Sin Historial').id}").get_data(as_text=True)

    assert _claves_en_orden(html) == ['imp:5', 'imp:10', 'imp:14']


# ── El historial decora, no filtra ─────────────────────────────────────────

def test_cada_tarjeta_trae_el_historial_de_ese_cliente(app, logged_client):
    _sembrar_historial()
    html = logged_client.get(
        f"/pedidos/nuevo?cliente={_cliente('Un Solo Grupo').id}").get_data(as_text=True)

    # Compró del imp:10 dos veces; del imp:14, nunca.
    assert '2 pedidos' in html
    assert 'Sin pedidos' in html


def test_cliente_sin_historial_no_muestra_conteos_inventados(app, logged_client):
    """Contaba «Sin pedidos» en TODA la página y esperaba 2, uno por tarjeta.

    Desde 2026-08-30 el historial del cliente se muestra también en la cabecera
    de este paso —se mudó acá desde la pantalla de líneas, que necesitaba el
    espacio—, y para un cliente sin historial dice «Sin pedidos anteriores».
    Eso hacía tres coincidencias y ponía el test en rojo sin que nada estuviera
    mal.

    Se cuenta donde el test quería contar: en las tarjetas de grupo. Lo que
    cuida —que no se inventen conteos ni fechas— queda igual de firme.
    """
    html = logged_client.get(
        f"/pedidos/nuevo?cliente={_cliente('Sin Historial').id}").get_data(as_text=True)

    metas = re.findall(r'<span class="pn-grupo-meta">(.*?)</span>', html, re.S)
    assert len(metas) == 2, f'se esperaban 2 tarjetas de grupo, hay {len(metas)}'
    assert all('Sin pedidos' in m for m in metas)
    assert 'última vez' not in html


def test_las_tarjetas_muestran_productos_de_ejemplo_del_catalogo(app, logged_client):
    """`tax_rate` es un código de QuickBooks, no un porcentaje: sin ejemplos el
    vendedor no distingue «Impuesto 10» de «Impuesto 14». Y los ejemplos salen
    del catálogo, así que un grupo que nunca compró también los tiene."""
    html = logged_client.get(
        f"/pedidos/nuevo?cliente={_cliente('Sin Historial').id}").get_data(as_text=True)

    # Dentro de las tarjetas: buscar los nombres en el HTML entero no probaría
    # nada, porque el catálogo completo viaja embebido en el paso siguiente.
    ejemplos = ' | '.join(re.findall(
        r'class="pn-grupo-ejemplos">([^<]*)<', html))
    assert 'Aceite vegetal 12 x 1 L' in ejemplos
    assert 'Ham di Pasku 4 kg' in ejemplos


# ── Salidas viejas y claves inválidas ──────────────────────────────────────

@pytest.mark.parametrize('clave', ['nuevo', 'pesable:99', 'basura'])
def test_clave_de_grupo_no_valida_vuelve_a_preguntar(app, logged_client, clave):
    """`grupo=nuevo` era la salida del candado y ya no existe: los tres grupos
    están listados, así que ninguno es inalcanzable. Una URL vieja guardada no
    puede reventar ni colarse al paso siguiente."""
    _sembrar_historial()
    cliente = _cliente('Multigrupo')

    resp = logged_client.get(f'/pedidos/nuevo?cliente={cliente.id}&grupo={clave}')

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-paso="cliente"' in html
    assert 'id="form-nuevo-pedido"' not in html


def test_la_pantalla_de_grupos_ya_no_ofrece_catalogo_completo(app, logged_client):
    """La tarjeta «Otro grupo» existía porque el historial filtraba las
    opciones; con las tres siempre presentes sobra, y un pedido sin grupo
    fijado permitiría mezclar."""
    _sembrar_historial()
    html = logged_client.get(
        f"/pedidos/nuevo?cliente={_cliente('Multigrupo').id}").get_data(as_text=True)

    assert 'grupo=nuevo' not in html
    assert 'Otro grupo' not in html


# ── Con el grupo elegido, el pedido ────────────────────────────────────────

def test_elegir_grupo_lleva_al_pedido_con_su_habitual(app, logged_client):
    _sembrar_historial()
    cliente = _cliente('Un Solo Grupo')

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    assert 'id="form-nuevo-pedido"' in html
    assert 'name="grupo" value="imp:10"' in html


def test_grupo_sin_historial_abre_el_pedido_vacio(app, logged_client):
    """Elegir un grupo que nunca compró es el caso de Luna Park: tiene que
    poder tomarse el pedido igual, solo que sin nada precargado."""
    _sembrar_historial()
    cliente = _cliente('Un Solo Grupo')

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:14').get_data(as_text=True)

    assert 'id="form-nuevo-pedido"' in html
    assert 'name="grupo" value="imp:14"' in html
    # El panel de añadir arranca abierto porque no hay líneas sembradas.
    panel = re.search(r'<div[^>]*id="ph-add-panel"[^>]*>', html).group(0)
    assert 'hidden' not in panel


# ── El paso del pedido, con el grupo ya elegido ────────────────────────────

def test_el_pedido_muestra_el_grupo_como_boton_que_vuelve_a_elegir(app, logged_client):
    """El vendedor tiene que ver en qué grupo está —el buscador solo ofrece
    ese— y poder cambiarlo sin rehacer el pedido desde el cliente.

    Desde Task 1 (2026-08-30) el chip ya no muestra el código de QBO crudo
    («Impuesto 10»): `_etiqueta_grupo` lo traduce a OB, que es lo que de
    verdad le dice algo al vendedor (ver tests/test_pedido_impuesto.py)."""
    _sembrar_historial()
    cliente = _cliente('Un Solo Grupo')

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    boton = re.search(r'<a[^>]*id="ph-grupo-actual"[^>]*>.*?</a>', html, re.S)
    assert boton, 'falta el botón de grupo en el paso del pedido'
    assert 'OB 6%' in boton.group(0)
    assert 'Impuesto' not in boton.group(0)
    # Vuelve a la pantalla de grupos: `?cliente=` sin grupo.
    destino = re.search(r'href="([^"]*)"', boton.group(0)).group(1)
    assert destino.endswith(f'/pedidos/nuevo?cliente={cliente.id}')


def test_el_pedido_ya_no_trae_el_parrafo_de_la_salida_vieja(app, logged_client):
    """Lo reemplaza el botón: dos formas de decir lo mismo en la misma
    pantalla, y una de ellas apuntaba a `grupo=nuevo`, que ya no existe."""
    _sembrar_historial()
    html = logged_client.get(
        f"/pedidos/nuevo?cliente={_cliente('Un Solo Grupo').id}&grupo=imp:10"
    ).get_data(as_text=True)

    assert 'pn-otro-grupo' not in html
    assert 'grupo=nuevo' not in html


def test_la_flecha_de_volver_del_pedido_lleva_a_los_grupos(app, logged_client):
    """Volver es deshacer el último paso —el grupo—, no saltar dos atrás al
    cliente y perder la elección."""
    _sembrar_historial()
    cliente = _cliente('Multigrupo')

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    volver = re.search(r'<a[^>]*id="ph-cambiar-cliente"[^>]*>', html).group(0)
    href = re.search(r'href="([^"]*)"', volver).group(1)
    assert href.endswith(f'/pedidos/nuevo?cliente={cliente.id}')


def test_los_contadores_cuentan_cuatro_pasos(app, logged_client):
    _sembrar_historial()
    cliente = _cliente('Multigrupo')

    grupos = logged_client.get(f'/pedidos/nuevo?cliente={cliente.id}').get_data(as_text=True)
    pedido = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)
    clientes = logged_client.get('/pedidos/nuevo').get_data(as_text=True)

    assert '01 / 04' in clientes
    assert '02 / 04' in grupos
    assert '03 / 04' in pedido
    assert '04 / 04' in pedido   # la revisión vive en la misma página


def test_editar_no_pregunta_el_grupo(app, logged_client):
    """Editando, el grupo lo determinan las líneas que el pedido ya tiene: no
    hay nada que elegir, y «Cambiar cliente» sigue yendo a la lista."""
    _sembrar_historial()
    from app import Pedido
    pedido = Pedido.query.first()

    html = logged_client.get(f'/pedidos/{pedido.id}/editar').get_data(as_text=True)

    assert 'id="form-nuevo-pedido"' in html
    assert 'id="ph-grupo-actual"' not in html
    volver = re.search(r'<a[^>]*id="ph-cambiar-cliente"[^>]*>', html).group(0)
    assert 'cambiar=1' in volver


# ── Los ejemplos de cada tarjeta son de ESTE cliente (Task 5) ─────────────

def test_los_ejemplos_salen_del_historial_de_este_cliente(app, logged_client):
    """El catálogo alfabético es el mismo para los 62 clientes; lo que
    compró ESTE cliente en el grupo sí lo distingue de otro. 'Salchicha
    Frankfurter…' no es el primero alfabético del imp:10 (lo es 'Aceite
    vegetal…'), así que si aparece es porque vino del historial, no del
    catálogo."""
    cliente = _cliente('Sin Historial')
    _crear_pedido(cliente.id, 'Salchicha Frankfurter 2.5 kg', dias_atras=3)

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}').get_data(as_text=True)

    ejemplos = re.findall(r'class="pn-grupo-ejemplos">([^<]*)<', html)
    assert len(ejemplos) == 2  # imp:10, imp:14, en ese orden
    assert 'Salchicha Frankfurter 2.5 kg' in ejemplos[0]
    assert 'Aceite vegetal' not in ejemplos[0]
    assert 'Atun en lata' not in ejemplos[0]


def test_grupo_sin_historial_de_este_cliente_sigue_usando_el_catalogo(app, logged_client):
    """Sin compras de ESTE cliente en el grupo, no hay nada propio que
    mostrar: recién ahí cae al catálogo, como antes."""
    cliente = _cliente('Sin Historial')
    # Compra en imp:10, nunca en imp:14.
    _crear_pedido(cliente.id, 'Salchicha Frankfurter 2.5 kg', dias_atras=3)

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}').get_data(as_text=True)

    ejemplos = re.findall(r'class="pn-grupo-ejemplos">([^<]*)<', html)
    assert 'Ham di Pasku 4 kg' in ejemplos[1]  # único producto del catálogo en imp:14


# ── El remedio vive en la confirmación, no en el banner (Task 5) ──────────

def test_el_banner_de_grupos_no_ofrece_el_remedio(app, logged_client):
    """La pantalla de grupos explica la restricción; el remedio (ofrecer el
    otro grupo) no vive ahí, sino en la confirmación al terminar."""
    _sembrar_historial()
    cliente = _cliente('Multigrupo')

    html = logged_client.get(f'/pedidos/nuevo?cliente={cliente.id}').get_data(as_text=True)

    assert 'Un pedido no puede mezclar grupos' in html
    assert 'pn-conf-otro-grupo' not in html


def test_confirmacion_ofrece_el_otro_grupo_si_el_cliente_compra_de_ambos(app, logged_client):
    """El banner de la pantalla de grupos solo explica la restricción; el
    remedio —ofrecer el otro grupo— aparece recién al terminar un pedido,
    y solo si ESTE cliente de verdad compra de los dos."""
    _sembrar_historial()
    cliente = _cliente('Multigrupo')  # compró imp:10 e imp:14

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    oferta = re.search(r'<a[^>]*id="pn-conf-otro-grupo"[^>]*>.*?</a>', html, re.S)
    assert oferta, 'falta el enlace al otro grupo en la confirmación'
    assert 'OB 0%' in oferta.group(0)
    href = re.search(r'href="([^"]*)"', oferta.group(0)).group(1).replace('&amp;', '&')
    assert href.endswith(f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:14')


def test_confirmacion_no_ofrece_otro_grupo_si_el_cliente_compra_de_uno_solo(app, logged_client):
    _sembrar_historial()
    cliente = _cliente('Un Solo Grupo')  # solo compró imp:10

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    assert 'id="pn-conf-otro-grupo"' not in html


def test_confirmacion_no_ofrece_otro_grupo_sin_historial(app, logged_client):
    """Grupo elegido por primera vez (caso Luna Park): nada que ofrecer."""
    cliente = _cliente('Sin Historial')

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente.id}&grupo=imp:10').get_data(as_text=True)

    assert 'id="pn-conf-otro-grupo"' not in html


def test_editar_no_ofrece_otro_grupo(app, logged_client):
    """Editando no hay grupo elegido (lo determinan las líneas): tampoco hay
    'otro grupo' que ofrecer."""
    _sembrar_historial()
    from app import Pedido
    pedido = Pedido.query.first()

    html = logged_client.get(f'/pedidos/{pedido.id}/editar').get_data(as_text=True)

    assert 'id="pn-conf-otro-grupo"' not in html
