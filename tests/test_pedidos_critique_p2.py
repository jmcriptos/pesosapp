"""P2 del critique del listado: las acciones no pueden moverse bajo el dedo.

En escritorio un `pendiente` mostraba [Pesar][Editar][Borrar] y un `preparado`
[Editar][Facturar][Borrar]: la acción principal se corría al medio y el editar
saltaba al primer puesto, con 100px de deriva entre filas adyacentes de 63px.
Quien baja por la columna haciendo clic sin releer toca otro control — y uno de
los candidatos es Facturar.

Además la tarjeta móvil nunca decía CUÁNTO se pasó un pedido: el escritorio
renderiza «3 d tarde» y el móvil solo la fecha, en el mismo gris que uno a
tiempo. La magnitud de la urgencia existía solo en el dispositivo que estos
usuarios no llevan.

Critique: .impeccable/critique/2026-08-28T08-22-35Z__templates-pedidos-html.md
"""
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal

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
        from app import Rol, Territorio, Vendedor, Cliente, Producto

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
        _db.session.add(Cliente(nombre='Distribuidora Norte', territorio_id=territorio.id,
                                moneda='XCG', qbo_id='C1'))
        _db.session.add(Producto(nombre='Producto', temperatura='4°C', se_pesa=False,
                                 tax_rate=10.0, qbo_id='P1'))
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


def _pedido(estado='pendiente', dias=1):
    from app import Pedido, Cliente, Producto, DetallePedido
    p = Pedido(cliente_id=Cliente.query.first().id, estado=estado, tipo_cambio=1.0)
    p.fecha_entrega = _hoy_local() + timedelta(days=dias)
    _db.session.add(p)
    _db.session.flush()
    _db.session.add(DetallePedido(
        pedido_id=p.id, producto_id=Producto.query.first().id,
        cajas=1, cajas_pedidas=1, peso=0,
        precio_unitario=Decimal('10'), subtotal=Decimal('10'), es_linea_pedido=True,
    ))
    _db.session.commit()
    return p


def _bloque_acciones_escritorio(html, pedido_id):
    """El grupo de acciones del <tr> de ese pedido."""
    for tr in re.findall(r'<tr[^>]*>.*?</tr>', html, re.S):
        if f'PED-{pedido_id}<' in tr:
            m = re.search(r'<div class="pedido-row-actions.*?</div>\s*</td>', tr, re.S)
            return m.group(0) if m else ''
    return ''


def _orden_de_acciones(bloque):
    """Los roles de acción en el orden en que aparecen en el markup."""
    orden = []
    for m in re.finditer(r'class="([^"]*(?:row-action|action)[^"]*)"', bloque):
        clases = m.group(1)
        if 'row-action-main' in clases:
            orden.append('principal')
        elif 'row-action-edit' in clases:
            orden.append('editar')
        elif 'row-action-danger' in clases:
            orden.append('borrar')
    return orden


# === Las acciones ocupan siempre el mismo puesto ===

def test_pendiente_y_preparado_ordenan_igual_sus_acciones(app, logged_client):
    """Principal, editar, borrar. En las dos filas, en el mismo orden.

    El pendiente lleva un producto que SÍ se pesa: es el caso donde las dos
    filas tienen acción principal («Pesar» y «Facturar») y por tanto donde se
    veía la deriva. El pendiente sin nada que pesar no tiene principal y su
    alineación la cubre `test_sin_accion_principal_la_ranura_queda_reservada`.
    """
    with app.app_context():
        pendiente = _pedido_con(se_pesa=True, estado='pendiente')
        preparado = _pedido('preparado')

        # `/pedidos` sin parámetros es el TABLERO desde el 2026-08-28; el
        # markup de fila/tarjeta que este archivo verifica vive en `?estado=todos`.
        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        esperado = ['principal', 'editar', 'borrar']
        assert _orden_de_acciones(_bloque_acciones_escritorio(html, pendiente.id)) == esperado
        assert _orden_de_acciones(_bloque_acciones_escritorio(html, preparado.id)) == esperado


def test_la_accion_principal_no_cambia_de_ancho_entre_filas(app, logged_client):
    """«Pesar» y «Facturar» tienen largos distintos: sin un ancho mínimo común,
    editar y borrar se corren de fila a fila aunque el orden sea el mismo."""
    with app.app_context():
        _pedido('pendiente')

        css = open('static/css/pedidos_list.css', encoding='utf-8').read()
        bloque = re.search(
            r'\.pedido-row-actions \.row-action-main \{[^}]*\}', css, re.S)

        assert bloque, 'no encontré la regla de la acción principal'
        assert 'min-width' in bloque.group(0), (
            'la acción principal necesita un ancho mínimo para no mover a las otras'
        )


# === La urgencia se ve en el teléfono ===

def test_la_tarjeta_movil_dice_cuantos_dias_de_atraso(app, logged_client):
    """El escritorio ya mostraba «3 d tarde»; el móvil, solo la fecha."""
    with app.app_context():
        _pedido('pendiente', dias=-3)

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
        tarjeta = re.search(r'<div class="pedido-card".*?<!-- /pedido-card -->|<div class="pedido-card".*?</div>\s*</div>\s*</div>', html, re.S)

        assert tarjeta, 'no encontré la tarjeta móvil'
        assert '3 d tarde' in tarjeta.group(0)


def test_la_tarjeta_de_un_pedido_a_tiempo_no_habla_de_atraso(app, logged_client):
    with app.app_context():
        _pedido('pendiente', dias=4)

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
        # La sección móvil entera: si «tarde» no está en ningún lado, no está
        # en la tarjeta.
        movil = html.split('tabla-pedidos-card')[0]

        assert 'tarde' not in movil


# === Una sola fuente de iconos ===

def test_font_awesome_se_carga_una_sola_vez(app, logged_client):
    """Se cargaban 6.7.2 (base) y 6.4.2 (pedidos): dos fuentes de iconos
    completas en un teléfono de campo, para el mismo juego de glifos."""
    with app.app_context():
        html = logged_client.get('/pedidos').get_data(as_text=True)

        assert len(re.findall(r'font-awesome/[\d.]+/css/all\.min\.css', html)) == 1


# === «Pesar» solo donde hay algo que pesar ===

def _pedido_con(se_pesa, estado='pendiente'):
    """Pedido cuyo único producto se pesa o no."""
    from app import Pedido, Cliente, Producto, DetallePedido
    prod = Producto(nombre=f'Prod {se_pesa}', temperatura='4°C', se_pesa=se_pesa,
                    tax_rate=10.0, qbo_id=f'Q-{se_pesa}-{id(se_pesa)}')
    _db.session.add(prod)
    _db.session.flush()
    p = Pedido(cliente_id=Cliente.query.first().id, estado=estado, tipo_cambio=1.0)
    p.fecha_entrega = _hoy_local() + timedelta(days=1)
    _db.session.add(p)
    _db.session.flush()
    _db.session.add(DetallePedido(
        pedido_id=p.id, producto_id=prod.id, cajas=1, cajas_pedidas=1, peso=0,
        precio_unitario=Decimal('10'), subtotal=Decimal('10'), es_linea_pedido=True,
    ))
    _db.session.commit()
    return p


def _fila(html, pedido_id):
    for tr in re.findall(r'<tr[^>]*>.*?</tr>', html, re.S):
        if f'PED-{pedido_id}<' in tr:
            return tr
    return ''


def test_un_pedido_sin_productos_pesables_no_ofrece_pesar(app, logged_client):
    """El servidor ya rechaza pesar esos pedidos (app.py:6924) y devuelve al
    detalle con un flash. Ofrecer el botón igual es mandar al vendedor a un
    rebote: toca «Pesar» y no pasa nada útil."""
    with app.app_context():
        sin_pesar = _pedido_con(se_pesa=False)

        # `/pedidos` sin parámetros es el TABLERO desde el 2026-08-28; la
        # fila que este test verifica vive en `?estado=todos`.
        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        assert 'Pesar' not in _fila(html, sin_pesar.id)


def test_un_pedido_con_productos_pesables_sigue_ofreciendo_pesar(app, logged_client):
    with app.app_context():
        con_pesar = _pedido_con(se_pesa=True)

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        assert 'Pesar' in _fila(html, con_pesar.id)


def test_un_pedido_sin_pesables_ofrece_preparar(app, logged_client):
    """No hay nada que capturar en esos pedidos: las líneas de preparación se
    crean solas al alta/edición y la validación solo pide lote y fechas para
    productos pesables. Lo único que falta es marcarlo preparado, que vive en
    el detalle con su confirmación. El botón LLEVA ahí; no cambia el estado
    desde la lista."""
    with app.app_context():
        sin_pesar = _pedido_con(se_pesa=False)

        fila = _fila(logged_client.get('/pedidos?estado=todos').get_data(as_text=True), sin_pesar.id)

        assert 'Preparar' in fila
        # El botón es un enlace al detalle, no un submit: navega, no transiciona.
        boton = re.search(r'<a[^>]*row-action-main[^>]*>.*?</a>', fila, re.S)
        assert boton, 'la acción principal debe ser un enlace, no un formulario'
        assert f'/pedidos/{sin_pesar.id}' in boton.group(0)


def test_todo_pendiente_tiene_accion_principal(app, logged_client):
    """Con «Preparar» cubriendo el caso sin pesables, ya no queda ningún
    pendiente sin acción: la ranura vacía dejó de hacer falta."""
    with app.app_context():
        con = _pedido_con(se_pesa=True)
        sin = _pedido_con(se_pesa=False)

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        assert 'row-action-main' in _fila(html, con.id)
        assert 'row-action-main' in _fila(html, sin.id)
        assert 'row-action-slot' not in html, 'la ranura vacia quedo sin uso'


def test_la_tarjeta_movil_tampoco_ofrece_pesar_de_mas(app, logged_client):
    with app.app_context():
        sin_pesar = _pedido_con(se_pesa=False)

        # `/pedidos` sin parámetros es el TABLERO desde el 2026-08-28; la
        # tarjeta móvil que este test verifica vive en `?estado=todos`.
        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
        movil = html.split('tabla-pedidos-card')[0]
        tarjeta = [b for b in movil.split('pedido-card') if f'PED-{sin_pesar.id}' in b]

        assert tarjeta, 'no encontré la tarjeta'
        assert 'Pesar' not in tarjeta[0]


def test_la_tarjeta_movil_sin_pesables_ofrece_preparar(app, logged_client):
    with app.app_context():
        sin_pesar = _pedido_con(se_pesa=False)

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
        movil = html.split('tabla-pedidos-card')[0]
        tarjeta = [b for b in movil.split('pedido-card') if f'PED-{sin_pesar.id}' in b]

        assert tarjeta and 'Preparar' in tarjeta[0]
