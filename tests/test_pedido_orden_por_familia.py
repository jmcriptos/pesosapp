"""Los productos de un pedido salen agrupados por familia, no en alfabético.

El formato de pedidos en papel de Jomar (Formato_Pedidos_Julio2026) agrupa por
marca —Underwood, Mantova, Van Camps, Mr. Raucher— y dentro de cada marca lista
los productos seguidos: los nueve atunes de Van Camps van juntos.

La app los sacaba alfabéticos por nombre, así que «Lomitos de Atún Claro en
Agua» quedaba a nueve renglones de «Lomitos … en Aceite de Oliva», con jamones
ahumados en el medio. La clase de QuickBooks (`Producto.clase_qbo`) ya era esa
familia; faltaba usarla para ordenar el catálogo, las líneas y el detalle.
"""
import os
import re

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

RAIZ = os.path.join(os.path.dirname(__file__), '..')

# Ids reales de las clases en QuickBooks (ver `CLASES_QBO` en app.py).
UNDERWOOD = '600000000005391660'
MANTOVA = '529395'
VAN_CAMPS = '600000000005391641'
AHUMADOS = '600000000005541105'


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


def _producto(nombre, clase=None, se_pesa=False, tax=10.0):
    from app import Producto
    producto = Producto(nombre=nombre, temperatura='4°C', se_pesa=se_pesa,
                        tax_rate=tax, clase_qbo=clase,
                        qbo_id=f'QBO-{nombre[:8]}')
    _db.session.add(producto)
    _db.session.commit()
    return producto


# === La clave de orden ===

def test_las_familias_salen_en_el_orden_del_formato_de_pedidos(app):
    """Underwood, Mantova, Van Camps, Mr. Raucher — el del papel, no el alfabético."""
    with app.app_context():
        from app import _orden_producto

        productos = [
            _producto('Cooked Chicken Ham', AHUMADOS),
            _producto('Lomitos de Atún Claro en Agua', VAN_CAMPS),
            _producto('Avocado Oil', MANTOVA),
            _producto('Diablitos Underwood Gde.', UNDERWOOD),
        ]

        orden = [p.nombre for p in sorted(productos, key=_orden_producto)]
        assert orden == [
            'Diablitos Underwood Gde.',
            'Avocado Oil',
            'Lomitos de Atún Claro en Agua',
            'Cooked Chicken Ham',
        ]


def test_los_atunes_quedan_juntos(app):
    """El caso que motivó el cambio, tal como lo pidió el pedido en papel."""
    with app.app_context():
        from app import _orden_producto

        productos = [
            _producto('Lomitos de Atún Claro en Agua', VAN_CAMPS),
            _producto('Cooked Shoulder', AHUMADOS),
            _producto('Lomitos de Atún Claro en Aceite de Oliva', VAN_CAMPS),
            _producto('Chicken Ham Underwood Gde.', UNDERWOOD),
            # Alfabéticamente caería entre los dos atunes y los partiría.
            _producto('Ham di Pasku Mr Raucher', AHUMADOS),
        ]

        orden = [p.nombre for p in sorted(productos, key=_orden_producto)]
        atunes = [i for i, n in enumerate(orden) if 'Atún' in n]
        assert atunes == list(range(atunes[0], atunes[0] + len(atunes))), (
            f'Los atunes quedaron partidos: {orden}'
        )


def test_dentro_de_la_familia_el_orden_es_alfabetico(app):
    """Alfabético y no una secuencia a mano: un producto nuevo entra solo."""
    with app.app_context():
        from app import _orden_producto

        productos = [
            _producto('Smoked Bacon Mr Raucher', AHUMADOS),
            _producto('Cooked Chicken Ham', AHUMADOS),
            _producto('Ham di Pasku Mr Raucher', AHUMADOS),
        ]

        orden = [p.nombre for p in sorted(productos, key=_orden_producto)]
        assert orden == [
            'Cooked Chicken Ham',
            'Ham di Pasku Mr Raucher',
            'Smoked Bacon Mr Raucher',
        ]


def test_un_producto_sin_clase_va_al_final_y_no_desaparece(app):
    """No todos los productos están clasificados en QBO; el pedido igual se arma."""
    with app.app_context():
        from app import _orden_producto, CLASE_SIN_CLASIFICAR, _etiqueta_clase

        sin_clase = _producto('Aceituna sin clasificar', None)
        con_clase = _producto('Zucchini Mantova', MANTOVA)

        orden = [p.nombre for p in sorted([sin_clase, con_clase], key=_orden_producto)]
        assert orden == ['Zucchini Mantova', 'Aceituna sin clasificar']
        assert _etiqueta_clase(sin_clase) == CLASE_SIN_CLASIFICAR


def test_agrupar_por_familia_no_reordena_alfabeticamente(app):
    """`groupby` de Jinja sí lo haría; por eso la agrupación se arma en Python."""
    with app.app_context():
        from app import _agrupar_por_familia

        productos = [
            _producto('Cooked Shoulder', AHUMADOS),
            _producto('Diablitos Underwood Gde.', UNDERWOOD),
            _producto('Lomitos de Atún Claro en Agua', VAN_CAMPS),
            _producto('Roast Beef Underwood Gde.', UNDERWOOD),
        ]

        grupos = _agrupar_por_familia(productos)
        assert [etiqueta for etiqueta, _ in grupos] == [
            'Untables Underwood', 'Atún Van Camps', 'Cocidos y Ahumados',
        ]
        assert [p.nombre for p in grupos[0][1]] == [
            'Diablitos Underwood Gde.', 'Roast Beef Underwood Gde.',
        ]


# === El catálogo que ve el vendedor ===

def test_el_catalogo_del_buscador_sale_ordenado_y_con_la_familia(app):
    """`clase` viaja al form: el desplegable pinta un encabezado por familia."""
    with app.app_context():
        from app import Cliente, _productos_dicts_para_cliente

        _producto('Cooked Chicken Ham', AHUMADOS)
        _producto('Diablitos Underwood Gde.', UNDERWOOD)
        _producto('Lomitos de Atún Claro en Agua', VAN_CAMPS)

        cliente = Cliente(nombre='Cliente Orden', moneda='XCG')
        _db.session.add(cliente)
        _db.session.commit()

        catalogo = _productos_dicts_para_cliente(cliente.id)

        assert [p['nombre'] for p in catalogo] == [
            'Diablitos Underwood Gde.',
            'Lomitos de Atún Claro en Agua',
            'Cooked Chicken Ham',
        ]
        assert [p['clase'] for p in catalogo] == [
            'Untables Underwood', 'Atún Van Camps', 'Cocidos y Ahumados',
        ]
        # El grupo de FACTURACIÓN es otra cosa y sigue viajando aparte.
        assert all('grupo' in p for p in catalogo)


# === Las líneas de un pedido ya cargado ===

def _pedido_con_lineas(nombres_y_clases, se_pesa=False):
    from app import Cliente, Pedido, DetallePedido
    from datetime import date

    cliente = Cliente(nombre='Cliente Pedido', moneda='XCG')
    _db.session.add(cliente)
    _db.session.commit()

    pedido = Pedido(cliente_id=cliente.id, fecha_pedido=date.today(), estado='pendiente')
    _db.session.add(pedido)
    _db.session.commit()

    for nombre, clase in nombres_y_clases:
        producto = _producto(nombre, clase, se_pesa=se_pesa)
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=producto.id,
            cajas=1, peso=0, precio_unitario=10, subtotal=10,
            es_linea_pedido=True,
        ))
    _db.session.commit()
    return pedido


def test_las_lineas_pesables_salen_agrupadas(app):
    """La pantalla de pesar recorre los ahumados de corrido, no salta de familia."""
    with app.app_context():
        from app import _pedido_detalles_pesables

        pedido = _pedido_con_lineas([
            ('Lomitos de Atún Claro en Agua', VAN_CAMPS),
            ('Cooked Shoulder', AHUMADOS),
            ('Diablitos Underwood Gde.', UNDERWOOD),
        ], se_pesa=True)

        orden = [d.producto.nombre for d in _pedido_detalles_pesables(pedido)]
        assert orden == [
            'Diablitos Underwood Gde.',
            'Lomitos de Atún Claro en Agua',
            'Cooked Shoulder',
        ]


def test_dos_lineas_del_mismo_producto_conservan_su_orden_de_carga(app):
    """El id desempata: un pesable con varias preparaciones no se baraja."""
    with app.app_context():
        from app import _orden_detalle, DetallePedido

        pedido = _pedido_con_lineas([('Cooked Shoulder', AHUMADOS)], se_pesa=True)
        primera = DetallePedido.query.filter_by(pedido_id=pedido.id).one()
        segunda = DetallePedido(
            pedido_id=pedido.id, producto_id=primera.producto_id,
            cajas=1, peso=0, precio_unitario=10, subtotal=10, es_linea_pedido=True,
        )
        _db.session.add(segunda)
        _db.session.commit()

        assert _orden_detalle(primera) < _orden_detalle(segunda)


# === Lo que la pantalla tiene que hacer con eso ===

def _leer(*partes):
    with open(os.path.join(RAIZ, *partes), encoding='utf-8') as fh:
        return fh.read()


def test_el_desplegable_del_pedido_pinta_un_optgroup_por_familia():
    form = _leer('templates', 'pedido_form.html')
    assert "createElement('optgroup')" in form, (
        'Sin <optgroup> el desplegable vuelve a ser una lista plana.'
    )
    assert 'lockOptgroupOrder: true' in form, (
        'Sin `lockOptgroupOrder` Tom Select reordena las familias por su '
        'cuenta y «Atún Van Camps» vuelve a caer primero.'
    )


def test_las_lineas_del_pedido_se_pintan_agrupadas_sin_perder_el_indice_real():
    """`data-idx` tiene que seguir apuntando a `productosAgregados`.

    Se pinta una copia ordenada; si se ordenara el arreglo, los botones +/− y
    «quitar» operarían sobre otra línea.
    """
    form = _leer('templates', 'pedido_form.html')
    assert 'pn-linea-familia' in form
    assert re.search(r'\.map\(\(p, idx\) => \(\{ p, idx \}\)\)\s*\n\s*\.sort\(', form), (
        'El orden de pintado tiene que salir de una COPIA con el índice '
        'original pegado, no de reordenar `productosAgregados`.'
    )


def test_el_encabezado_de_familia_esta_blindado_contra_el_tema_oscuro():
    """Mismo argumento que el resto de `.pn-shell`: `dark-theme.css` usa !important."""
    css = _leer('static', 'css', 'pedido_nuevo.css')
    assert '.pn-shell .pn-linea-familia' in css
    assert '.ts-dropdown.pn-dropdown .optgroup-header' in css


def test_el_selector_del_detalle_agrupa_por_familia():
    modal = _leer('templates', 'partials', '_detail_edit_modal.html')
    assert 'productos_por_familia' in modal
    assert '<optgroup' in modal
    assert "productos|sort(attribute='nombre')" not in modal, (
        'El orden lo decide el servidor; re-ordenar por nombre acá lo pisa.'
    )


# === La página de detalle, renderizada de verdad ===

@pytest.fixture
def cliente_logueado(app):
    """Admin logueado + un pedido con productos de tres familias."""
    from app import Rol, Territorio, Vendedor, Cliente, Pedido, DetallePedido
    from datetime import date

    with app.app_context():
        rol = Rol(nombre='super_admin', descripcion='Admin')
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add_all([rol, territorio])
        _db.session.flush()

        vendedor = Vendedor(username='admin', email='admin@test.com',
                            nombre_completo='Admin Test', rol_id=rol.id,
                            territorio_id=territorio.id, activo=True)
        vendedor.set_password('testpass')
        _db.session.add(vendedor)

        cliente = Cliente(nombre='Cliente Test', territorio_id=territorio.id,
                          moneda='XCG')
        _db.session.add(cliente)
        _db.session.flush()

        pedido = Pedido(cliente_id=cliente.id, fecha_pedido=date.today(),
                        estado='pendiente')
        _db.session.add(pedido)
        _db.session.flush()

        for nombre, clase in [
            ('Cooked Shoulder', AHUMADOS),
            ('Lomitos de Atún Claro en Agua', VAN_CAMPS),
            ('Diablitos Underwood Gde.', UNDERWOOD),
        ]:
            producto = _producto(nombre, clase)
            _db.session.add(DetallePedido(
                pedido_id=pedido.id, producto_id=producto.id,
                cajas=1, peso=0, precio_unitario=10, subtotal=10,
                es_linea_pedido=True,
            ))
        _db.session.commit()
        pedido_id = pedido.id

    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client, pedido_id


def test_el_detalle_lista_los_productos_agrupados_por_familia(cliente_logueado):
    """Lo que el preparador ve: las líneas en el orden del pedido en papel."""
    client, pedido_id = cliente_logueado
    html = client.get(f'/pedidos/{pedido_id}/detalles').get_data(as_text=True)

    posiciones = [html.index(n) for n in (
        'Diablitos Underwood Gde.',
        'Lomitos de Atún Claro en Agua',
        'Cooked Shoulder',
    )]
    assert posiciones == sorted(posiciones), (
        'Las líneas del detalle salieron fuera del orden por familia.'
    )


def test_el_selector_del_detalle_renderiza_los_optgroups_en_orden(cliente_logueado):
    """El <optgroup> no es solo una línea de plantilla: tiene que llegar al HTML."""
    client, pedido_id = cliente_logueado
    html = client.get(f'/pedidos/{pedido_id}/detalles').get_data(as_text=True)

    familias = re.findall(r'<optgroup label="([^"]+)"', html)
    assert familias == [
        'Untables Underwood', 'Atún Van Camps', 'Cocidos y Ahumados',
    ], familias
